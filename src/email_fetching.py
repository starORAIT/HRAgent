import logging
from email_fetcher import MailFetcher
from db_manager import DBManager
from utils.log_utils import setup_logger
import time

def run_email_fetching(config):
    """运行邮件获取流程"""
    logger = setup_logger('EmailFetching')
    logger.info("======= 邮件获取服务启动 =======")
    
    while True:  # 添加外层循环使服务持续运行
        try:
            # 初始化数据库
            db_manager = DBManager(config)
            db_manager.create_database_if_not_exists()
            db_manager.init_engine_and_session()
            
            mail_fetcher = MailFetcher(config)
            cycle_start = time.time()
            total_processed = 0
            total_failed = 0
            start_time = time.time()
            
            # 保持原有的邮件处理逻辑
            for emails_batch in mail_fetcher.fetch_emails_from_all(False):  # 改为增量模式
                if not emails_batch:
                    continue
                
                batch_size = len(emails_batch)
                total_processed += batch_size
                
                # 每处理10个批次或处理超过100封邮件才显示一次进度
                if (total_processed % (batch_size * 10) == 0) or (total_processed >= 100):
                    elapsed_time = time.time() - start_time
                    avg_speed = total_processed / elapsed_time if elapsed_time > 0 else 0
                    
                    logger.info(f"处理进度: {total_processed}封邮件, "
                               f"速度: {avg_speed:.1f}封/秒")
                
                # 统计详细信息
                types_count = {}
                for email in emails_batch:
                    resume_type = email.get('resume_type', 'unknown')
                    types_count[resume_type] = types_count.get(resume_type, 0) + 1
                
                # 显示批次统计
                elapsed_time = time.time() - start_time
                avg_speed = total_processed / elapsed_time if elapsed_time > 0 else 0
                
                logger.info(f"批次处理统计:\n"
                           f"- 批次大小: {batch_size}封\n"
                           f"- 累计处理: {total_processed}封\n"
                           f"- 处理速度: {avg_speed:.1f}封/秒\n"
                           f"- 简历类型分布:\n" + 
                           "\n".join(f"  * {t}: {c}封" for t, c in types_count.items()))
                
                if total_processed > 0:
                    time.sleep(config.BATCH_SLEEP)
            
            # 本轮处理完成，等待下一轮
            logger.info(f"本轮邮件处理完成，等待{config.EMAIL_CHECK_INTERVAL}秒后开始下一轮检查...")
            time.sleep(config.EMAIL_CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"邮件获取异常: {e}", exc_info=True)
            time.sleep(300)  # 错误恢复等待
        finally:
            total_time = time.time() - start_time
            logger.info(f"======= 邮件获取任务完成 =======")
            logger.info(f"总计处理: {total_processed}封邮件")
            logger.info(f"总耗时: {total_time:.1f}秒"
                        f"(平均速度: {total_processed/total_time:.1f}封/秒)")

if __name__ == "__main__":
    from config import Config
    config = Config("config/.env")
    setup_logger('EmailFetching')
    run_email_fetching(config)
