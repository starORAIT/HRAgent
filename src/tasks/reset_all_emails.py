import os
import sys
import logging
import getpass
from sqlalchemy import and_

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from db_manager import Email, get_db, beijing_now, DBManager
from config import Config
from log_manager import LogManager

def reset_all_emails():
    """重置所有邮件状态为 NEW"""
    config = Config(os.path.join(project_root, "..", "config/.env"))
    
    # 初始化日志系统
    LogManager.setup_logging(config)
    
    print("警告：此操作将重置所有邮件状态为 NEW。")
    print("请输入 'YES' 确认操作：")
    confirmation = input().strip()
    
    if confirmation != "YES":
        print("操作已取消")
        return
    
    try:
        # 初始化数据库连接
        db_manager = DBManager(config)
        db_manager.init_engine_and_session()
        
        db = next(get_db())
        
        # 获取当前各状态的邮件数量
        status_counts = {}
        for status in ["NEW", "FAILED", "PROCESSING", "COMPLETED", "SKIPPED"]:
            count = db.query(Email).filter(Email.process_status == status).count()
            status_counts[status] = count
        
        logging.info("当前邮件状态统计：")
        for status, count in status_counts.items():
            logging.info(f"{status}: {count} 封")
        
        total = sum(status_counts.values())
        logging.info(f"总计: {total} 封邮件")
        
        # 执行重置
        if total > 0:
            updated = db.query(Email).filter(
                Email.process_status.in_(["FAILED", "PROCESSING", "COMPLETED", "SKIPPED"])
            ).update({
                "process_status": "NEW",
                "error_message": None,
                "update_time": beijing_now()
            })
            
            db.commit()
            logging.info(f"成功重置 {updated} 封邮件状态为 NEW")
            
            # 验证结果
            new_count = db.query(Email).filter(Email.process_status == "NEW").count()
            logging.info(f"重置后状态为 NEW 的邮件数量: {new_count}")
            
        else:
            logging.info("没有需要重置的邮件")
            
    except Exception as e:
        logging.error(f"重置邮件状态失败: {e}")
        if 'db' in locals():
            db.rollback()
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    reset_all_emails()
