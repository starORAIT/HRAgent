import os
import sys
import logging
from datetime import datetime, timedelta
from sqlalchemy import and_

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from db_manager import Email, get_db, beijing_now, DBManager
from config import Config

def reset_stuck_emails():
    """重置处理时间超过30分钟的PROCESSING状态邮件"""
    # 加载配置
    config = Config(os.path.join(project_root, "..", "config/.env"))
    
    # 确保日志目录存在
    log_dir = os.path.join(project_root, "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 设置日志
    log_file = os.path.join(log_dir, "reset_stuck_emails.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file)
        ]
    )
    
    try:
        # 初始化数据库连接
        db_manager = DBManager(config)
        db_manager.create_database_if_not_exists()
        db_manager.init_engine_and_session()
        
        db = next(get_db())
        stuck_time = beijing_now() - timedelta(minutes=30)
        
        # 查找所有卡在PROCESSING状态的邮件
        stuck_emails = db.query(Email).filter(
            and_(
                Email.process_status == "PROCESSING",
                Email.update_time < stuck_time
            )
        ).all()
        
        if stuck_emails:
            logging.warning(f"发现 {len(stuck_emails)} 封处理卡住的邮件")
            for email in stuck_emails:
                email.process_status = "FAILED"
                email.error_message = "处理超时，系统自动重置"
                logging.info(f"重置邮件状态: ID={email.id}, 主题={email.subject[:50]}")
            
            db.commit()
            logging.info("完成卡住邮件状态重置")
        else:
            logging.info("没有发现卡住的邮件")
            
    except Exception as e:
        logging.error(f"重置卡住邮件状态失败: {e}")
        if 'db' in locals():
            db.rollback()
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    reset_stuck_emails()
