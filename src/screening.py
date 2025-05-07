import logging
import json  # 添加这行
from concurrent.futures import ThreadPoolExecutor  # 改用ThreadPoolExecutor
import multiprocessing
import time
from config import Config
from db_manager import (
    DBManager, get_db, Email,
    get_unprocessed_emails
)
from ai_screener import AIScreener
from recruit_service import RecruitService
from log_manager import LogManager
from batch_processor import create_batch_record, update_batch_status
from concurrent_utils import process_email_chunk
from datetime import datetime, timedelta
from utils.log_utils import setup_logger
from utils import create_db_session  # 添加这行
from sqlalchemy import text  # Add this import at the top of your file

class ResumeCache:
    def __init__(self):
        self._cache = {}

    def get(self, email_hash):
        return self._cache.get(email_hash)

    def set(self, email_hash, result):
        self._cache[email_hash] = result

def serialize_email(email):
    """Convert Email object to dictionary for cross-process transfer"""
    return {
        'id': email.id,
        'message_id': email.message_id,
        'subject': email.subject,
        'from_address': email.from_address,
        'content_text': email.content_text,
        'content_html': email.content_html,
        'attachments_info': email.attachments_info,
        'received_date': email.received_date.isoformat() if email.received_date else None,
        'resume_hash': email.resume_hash,
        'attachment_url': email.attachment_url,
        'inbox_account': email.inbox_account,
    }

def cleanup_stuck_locks(config):
    """检查并清理可能存在的卡住的锁"""
    logger = setup_logger('LockCleaner')
    logger.info("开始检查并清理卡住的数据库锁...")
    
    session = None
    try:
        session = create_db_session(config)
        
        # 检查MySQL版本
        version_result = session.execute(text("SELECT VERSION()")).scalar()
        logger.info(f"数据库版本: {version_result}")
        is_mysql8_plus = version_result and version_result.startswith(('8.', '9.'))
        
        # 查询运行时间超过5分钟的事务
        stuck_trx_result = session.execute(text("""
            SELECT trx_id, trx_mysql_thread_id, trx_started, trx_query 
            FROM information_schema.innodb_trx 
            WHERE trx_started < NOW() - INTERVAL 5 MINUTE
        """))
        
        stuck_transactions = stuck_trx_result.fetchall()
        if stuck_transactions:
            logger.warning(f"发现 {len(stuck_transactions)} 个可能卡住的事务")
            
            # 查询卡住的锁 - 注意MySQL 8.0+和旧版本使用不同的表
            try:
                if is_mysql8_plus:
                    # MySQL 8.0+ 使用 performance_schema
                    stuck_locks_result = session.execute(text("""
                        SELECT * FROM performance_schema.data_locks 
                        WHERE thread_id IN (
                            SELECT trx_mysql_thread_id FROM information_schema.innodb_trx 
                            WHERE trx_started < NOW() - INTERVAL 5 MINUTE
                        )
                    """))
                else:
                    # 旧版MySQL使用 information_schema
                    stuck_locks_result = session.execute(text("""
                        SELECT * FROM information_schema.innodb_locks 
                        WHERE lock_trx_id IN (
                            SELECT trx_id FROM information_schema.innodb_trx 
                            WHERE trx_started < NOW() - INTERVAL 5 MINUTE
                        )
                    """))
                
                stuck_locks = stuck_locks_result.fetchall()
                if stuck_locks:
                    logger.warning(f"发现 {len(stuck_locks)} 个可能卡住的锁")
            except Exception as e:
                logger.warning(f"查询锁信息失败 (可以忽略): {e}")
            
            # 终止这些事务
            for trx in stuck_transactions:
                thread_id = trx.trx_mysql_thread_id
                try:
                    logger.warning(f"正在终止事务 ID: {thread_id}, 开始于: {trx.trx_started}")
                    session.execute(text(f"KILL {thread_id}"))
                except Exception as e:
                    logger.error(f"终止事务 {thread_id} 失败: {e}")
            
            logger.info("锁清理完成")
        else:
            logger.info("未发现卡住的事务")
            
        # 重置所有处理中但已过期的邮件状态
        reset_stalled_emails(session)
        
    except Exception as e:
        logger.error(f"清理卡住锁失败: {e}", exc_info=True)
    finally:
        if session:
            session.close()

def reset_stalled_emails(session, timeout_minutes=30):
    """重置长时间处于PROCESSING状态的邮件"""
    logger = setup_logger('LockCleaner')
    stalled_time = datetime.now() - timedelta(minutes=timeout_minutes)
    
    try:
        # 仅使用SQL更新而非ORM，避免获取锁
        result = session.execute(text("""
            UPDATE emails 
            SET process_status = 'FAILED', 
                error_message = '处理超时，状态已重置', 
                update_time = NOW() 
            WHERE process_status = 'PROCESSING' 
            AND update_time < :stalled_time
        """), {"stalled_time": stalled_time})
        
        session.commit()
        count = result.rowcount
        if count > 0:
            logger.info(f"已重置 {count} 个停滞的邮件状态")
        
    except Exception as e:
        logger.error(f"重置停滞邮件状态失败: {e}")
        session.rollback()


def run_screening(config):
    """运行简历筛选服务"""
    logger = setup_logger('Screening')
    logger.info("======= 简历筛选服务启动 =======")
    
    # 首先清理可能卡住的数据库锁
    cleanup_stuck_locks(config)

    # 加载岗位和公司信息
    job_info = load_job_info()
    company_info = load_company_info()
            
    if not job_info:
        logger.error("未能加载岗位信息，请检查 config/job_desc.xlsx 文件")
        
    if not company_info:
        logger.error("未能加载公司信息，请检查 config/company_info.txt 文件")

    while True:  # 服务持续运行
        session = None
        try:
            # 创建共享服务实例
            session = create_db_session(config)
            ai_screener = AIScreener(config, job_info, company_info)
            recruit_service = RecruitService(config)
            cycle_start = time.time()
            
            # 获取待处理邮件
            unprocessed = get_unprocessed_emails(session, config.SCREENING_BATCH_SIZE)
            stalled = get_stalled_emails(session, timeout_minutes=30)
            emails_to_process = unprocessed + stalled
            
            if emails_to_process:
                logger.info(f"发现待处理邮件: 新邮件={len(unprocessed)}, "
                          f"重试邮件={len(stalled)}")
                
                # 使用线程池处理邮件
                processed = 0
                failed = 0
                
                # 使用线程池而不是进程池
                with ThreadPoolExecutor(max_workers=config.SCREENING_WORKERS) as executor:
                    # 提交所有任务
                    futures = []
                    for email in emails_to_process:
                        future = executor.submit(
                            process_single_email,
                            email,
                            ai_screener,
                            recruit_service,
                            config
                        )
                        futures.append((email.id, future))
                    
                    # 收集结果
                    for email_id, future in futures:
                        try:
                            result = future.result(timeout=300)  # 5分钟超时
                            if result:
                                processed += 1
                                logger.info(f"邮件 {email_id} 处理成功")
                            else:
                                failed += 1
                                logger.error(f"邮件 {email_id} 处理失败")
                        except Exception as e:
                            failed += 1
                            logger.error(f"邮件 {email_id} 处理异常: {e}")
                
                # 显示处理统计
                cycle_time = time.time() - cycle_start
                logger.info(f"本轮处理完成:\n"
                          f"- 处理总数: {len(emails_to_process)}封\n"
                          f"- 成功数: {processed}封\n"
                          f"- 失败数: {failed}封\n"
                          f"- 成功率: {(processed/len(emails_to_process)*100):.1f}%\n"
                          f"- 耗时: {cycle_time:.1f}秒")
            else:
                logger.info("当前没有待处理的邮件")
            
            # 清理资源
            session.close()
            
            # 等待下一轮
            logger.info(f"等待{config.SCREENING_CHECK_INTERVAL}秒后开始下一轮检查...")
            time.sleep(config.SCREENING_CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"简历筛选异常: {e}", exc_info=True)
            time.sleep(300)
        finally:
            if session:
                session.close()

def process_single_email(email, ai_screener, recruit_service, config):
    """处理单封邮件"""
    logger = setup_logger(f'Screener-{email.id}')
    session = None
    
    try:
        # 创建新会话并设置短超时
        session = create_db_session(config)
        session.execute(text("SET innodb_lock_wait_timeout = 5"))  # 5秒超时，快速失败
        session.execute(text("SET SESSION transaction_isolation = 'READ-COMMITTED'"))
        
        try:
            # 使用直接SQL更新来避开ORM锁争用
            update_result = session.execute(text("""
                UPDATE emails 
                SET process_status = 'PROCESSING', update_time = NOW() 
                WHERE id = :email_id 
                AND process_status IN ('NEW', 'FAILED')
            """), {"email_id": email.id})
                    
            if update_result.rowcount == 0:
                logger.info(f"邮件 {email.id} 已被处理或状态已改变")
                return True
                
            session.commit()
            
            # 重新加载邮件进行处理
            db_email = session.query(Email).filter_by(id=email.id).first()
            
        except Exception as e:
            session.rollback()  # 添加显式回滚以释放锁
            if "deadlock" in str(e).lower() or "lock" in str(e).lower():
                logger.warning(f"邮件 {email.id} 获取锁失败，跳过处理: {e}")
                return False  # 返回false以重试
            raise  # 其他错误重新抛出

        # 处理附件信息
        try:
            attachments_info = json.loads(db_email.attachments_info) if db_email.attachments_info else []
            attach_filenames = [att.get('name', '') for att in attachments_info if isinstance(att, dict)]
        except Exception as e:
            logger.warning(f"解析附件信息失败: {str(e)}")
            attach_filenames = []
        
        # 识别邮件类型和岗位
        try:
            is_resume, position_name, channel = ai_screener.identify_mail_type(
                subject=db_email.subject,
                resume_text=db_email.content_text,
                attach_filenames=attach_filenames,
                from_domain=db_email.from_address.split('@')[-1] if db_email.from_address else ""
            )
            if not is_resume:
                db_email.process_status = "NOT_RESUME"
                db_email.error_message = "非简历邮件"
                session.commit()
                logger.info(f"邮件 {db_email.id} 不是简历邮件")
                return True
                
        except Exception as e:
            db_email.process_status = "FAILED"
            db_email.error_message = f"邮件类型识别失败: {str(e)}"
            session.commit()
            return False

        # 简历分析
        try:
            parsed_info, analysis = ai_screener.screen_resume(
                resume_text=db_email.content_text,
                position_name=position_name
            )
            if not parsed_info or not analysis:
                db_email.process_status = "FAILED"
                db_email.error_message = "AI分析返回空结果"
                session.commit()
                return False
                
            # 保存候选人信息
            candidate_id = recruit_service.store_candidate(
                session=session,
                parsed_info=parsed_info,
                analysis=analysis,
                resume_source=channel or db_email.from_address,
                resume_full_text=db_email.content_text,
                resume_hash=db_email.resume_hash,
                email_subject=str(db_email.subject),
                inbox_account=str(db_email.inbox_account),
                resume_file_url=str(db_email.attachment_url) if db_email.attachment_url else "",
                mail_sent_time=db_email.received_date
            )

            # 更新邮件状态 - 修改这里的状态为 COMPLETED
            db_email.process_status = "COMPLETED"  # 将 DONE 改为 COMPLETED
            db_email.candidate_id = candidate_id
            db_email.error_message = ""
            db_email.update_time = datetime.now()
            session.commit()
            
            logger.info(f"简历处理成功: id={db_email.id}, candidate_id={candidate_id}, position={position_name}")
            return True
            
        except Exception as e:
            logger.error(f"简历分析失败: {str(e)}")
            db_email.process_status = "FAILED"
            db_email.error_message = f"简历分析失败: {str(e)[:500]}"
            db_email.update_time = datetime.now()
            session.commit()
            return False
            
    except Exception as e:
        logger.error(f"处理邮件失败: {str(e)}", exc_info=True)
        try:
            if 'db_email' in locals():
                db_email.process_status = "FAILED"
                db_email.error_message = str(e)[:500]
                db_email.update_time = datetime.now()
                session.commit()
        except:
            pass
        return False
    finally:
        if session:
            session.close()

def get_unprocessed_emails(session, limit=None):
    """
    获取未处理的邮件，包括新建和失败状态的邮件
    
    Args:
        session: 数据库会话
        limit: 限制返回数量
        
    Returns:
        list: 未处理的邮件列表
    """
    query = session.query(Email).filter(
        Email.process_status.in_(["NEW", "FAILED"])
    ).order_by(Email.received_date.desc())
    
    if limit:
        query = query.limit(limit)
    
    return query.all()

def get_stalled_emails(session, timeout_minutes=30):
    """
    获取处理停滞的邮件，将它们标记为FAILED并返回
    
    Args:
        session: 数据库会话
        timeout_minutes: 停滞超时时间(分钟)
        
    Returns:
        list: 停滞的邮件列表，状态已重置为FAILED
    """
    stalled_time = datetime.now() - timedelta(minutes=timeout_minutes)
    
    # 获取停滞的邮件
    stalled_emails = session.query(Email).filter(
        Email.process_status == 'PROCESSING',
        Email.update_time < stalled_time
    ).all()  
    
    if stalled_emails:
        try:
            # 更新这些邮件的状态为FAILED
            stalled_ids = [email.id for email in stalled_emails]
            session.bulk_update_mappings(Email, [
                {
                    'id': email.id,
                    'process_status': "FAILED",
                    'error_message': f"处理超时（超过{timeout_minutes}分钟）",
                    'update_time': datetime.now()
                }
                for email in stalled_emails
            ])
            session.commit()
            logging.info(f"重置 {len(stalled_emails)} 个停滞邮件状态为FAILED")
            
            # 重新查询这些邮件以获取最新状态
            return session.query(Email).filter(
                Email.id.in_(stalled_ids)
            ).all()
            
        except Exception as e:
            logging.error(f"更新停滞邮件状态失败: {e}")
            session.rollback()
            return []
    
    return []

def _process_email_batches(**kwargs):
    """处理邮件批次的核心逻辑"""
    db = next(get_db())
    total_emails_count = db.query(Email).filter(
        Email.process_status.in_(["NEW", "FAILED"])
    ).count()
    
    if total_emails_count == 0:
        logging.info("没有待处理的邮件")
        return
        
    processed_count = 0
    batch_number = 0
    
    while True:
        try:
            emails = get_unprocessed_emails(db, kwargs['config'].BATCH_SIZE)
            if not emails:
                break
            
            batch_number += 1
            batch = create_batch_record(db, len(emails))
            
            # 处理当前批次
            results = _process_batch(emails, **kwargs)
            
            # 更新进度
            processed_count += len(results)
            update_batch_status(db, batch, results)
            
            # 显示进度并休息
            _log_batch_progress(batch_number, processed_count, total_emails_count)
            time.sleep(kwargs['config'].BATCH_SLEEP)
            
        except Exception as e:
            logging.error(f"处理批次失败: {e}")
            if 'batch' in locals():
                batch.status = "FAILED"
                db.commit()
                
    db.close()
    
    # 最终统计
    if total_emails_count > 0:
        progress_pct = (processed_count/total_emails_count*100)
        logging.info(f"【简历初筛】任务完成，共处理 {processed_count}/{total_emails_count} "
                    f"封邮件 ({progress_pct:.1f}%)")

def _process_batch(emails, executor, config, config_dict, ai_screener_data, 
                  service_data, chunk_size):
    """处理单个批次"""
    serialized_emails = [serialize_email(email) for email in emails]
    chunks = [serialized_emails[i:i + chunk_size] 
             for i in range(0, len(serialized_emails), chunk_size)]
    
    chunk_data = [(chunk, ai_screener_data, service_data) for chunk in chunks]
    
    results = []
    for i, data in enumerate(chunk_data):
        try:
            future = executor.submit(process_email_chunk, data, config_dict)
            chunk_results = future.result(timeout=300)
            results.extend(chunk_results)
        except Exception as e:
            logging.error(f"处理任务 {i+1} 失败: {e}")
            
    return results

def _log_batch_progress(batch_number, processed_count, total_emails_count):
    """记录批次处理进度"""
    progress_pct = processed_count/total_emails_count*100
    logging.info(f"\n{'='*50}")
    logging.info(f"已处理批次数: {batch_number}")
    logging.info(f"总进度: {processed_count}/{total_emails_count} ({progress_pct:.1f}%)")
    logging.info(f"{'='*50}\n")

def load_job_info():
    """加载岗位信息，并转换字段名称为指定格式"""
    try:
        import pandas as pd
        with open("config/job_desc.xlsx", "rb") as f:
            df = pd.read_excel(f)
            
            # 定义字段名映射关系
            field_mapping = {
                "岗位": "position_name",
                "岗位别称": "alias",
                "职责描述": "duties",
                "任职要求": "requirements",
                "学历要求": "education_req",
                "资历要求": "exp_req",
                "工作地点": "location",
                "绩效考核目标": "perf_goals"
            }
            
            # 重命名列
            df = df.rename(columns=field_mapping)
            
            # 转换为字典，使用position_name作为key
            job_dict = {}
            for _, row in df.iterrows():
                position_name = row.get('position_name')
                if (position_name):
                    job_dict[position_name] = row.to_dict()
            
            logging.info(f"成功加载 {len(job_dict)} 个岗位配置")
            return job_dict
            
    except Exception as e:
        logging.warning(f"未能加载岗位信息: {e}")
        return {}

def load_company_info():
    """加载公司信息"""
    try:
        with open("config/company_info.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        logging.warning(f"未加载到公司信息: {e}")
        return ""

if __name__ == "__main__":
    config = Config("config/.env")
    LogManager.setup_logging(config)
    logging.info("=== 简历初筛系统启动 ===")
    run_screening(config)
