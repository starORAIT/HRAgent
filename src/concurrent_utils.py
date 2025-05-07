import logging
import time
import multiprocessing  # Add this import
from concurrent.futures import ProcessPoolExecutor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import Config

def create_worker_session(config_dict):
    """为工作进程创建数据库会话"""
    config = Config.__new__(Config)
    for k, v in config_dict.items():
        setattr(config, k, v)
        
    db_url = (
        f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}?charset=utf8mb4"
    )
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_timeout=30,
        pool_size=5,
        max_overflow=5
    )
    Session = sessionmaker(bind=engine)
    return Session()

def process_email_chunk(chunk_data, config_dict):
    """并行处理邮件块"""
    from resume_processor import process_single_email
    from ai_screener import AIScreener
    from recruit_service import RecruitService
    
    emails, ai_screener_data, service_data = chunk_data
    chunk_size = len(emails)
    worker_id = multiprocessing.current_process().name
    start_time = time.time()
    last_progress_time = start_time
    results = []
    processed = 0
    
    try:
        # Create proper Config object instead of using dict directly
        config = Config.__new__(Config)
        for k, v in config_dict.items():
            setattr(config, k, v)
        
        session = create_worker_session(config_dict)
        ai_screener = AIScreener(config, ai_screener_data["job_info"], 
                               ai_screener_data["company_info"])
        service = RecruitService(config)
        
        # Add debug logging
        logging.info(f"[Worker {worker_id}] Initialized with OPENAI_API_KEY: {config.OPENAI_API_KEY[:8]}...")
        
        for i, email_dict in enumerate(emails, 1):
            try:
                result = process_single_email(
                    email_dict, session, config, ai_screener, service
                )
                if result:
                    results.append(result)
                    processed += 1
                
                # 显示进度
                if time.time() - last_progress_time >= 10:
                    _log_progress(worker_id, i, chunk_size, processed, start_time)
                    last_progress_time = time.time()
                    
            except Exception as e:
                logging.error(f"[Worker {worker_id}] 处理邮件失败 {email_dict['id']}: {e}")
                continue

        _log_final_stats(worker_id, chunk_size, processed, start_time)
        return results
        
    except Exception as e:
        logging.error(f"[Worker {worker_id}] 处理邮件块失败: {e}", exc_info=True)
        return []
    finally:
        if 'session' in locals():
            session.close()

def _log_progress(worker_id, current, total, processed, start_time):
    """记录处理进度"""
    elapsed = time.time() - start_time
    remaining = (elapsed / current) * (total - current)
    avg_time = elapsed / current
    success_rate = (processed / current) * 100
    
    logging.info(
        f"\n[Worker {worker_id}] 处理进度统计:\n"
        f"总数: {total} 封\n"
        f"当前: {current} 封 ({current/total*100:.1f}%)\n"
        f"成功: {processed} 封 ({success_rate:.1f}%)\n"
        f"平均耗时: {avg_time:.1f}秒/封\n"
        f"预计剩余: {remaining/60:.1f}分钟"
    )

def _log_final_stats(worker_id, total, processed, start_time):
    """记录最终统计信息"""
    total_time = time.time() - start_time
    logging.info(
        f"\n[Worker {worker_id}] <<<<<<< 邮件块处理完成 >>>>>>>\n"
        f"总数: {total} 封\n"
        f"成功: {processed} 封 ({(processed/total*100):.1f}%)\n"
        f"失败: {total-processed} 封\n"
        f"总耗时: {total_time/60:.1f}分钟\n"
        f"平均速度: {total_time/total:.1f}秒/封"
    )
