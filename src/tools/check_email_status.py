import sys
import os
import logging
from sqlalchemy import text

# 添加父目录到系统路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from db_manager import get_db

def check_email_status():
    """检查邮件处理状态"""
    config = Config("../config/.env")
    db = next(get_db())
    
    try:
        # 获取各状态邮件数量
        sql = """
        SELECT process_status, COUNT(*) as count 
        FROM emails 
        GROUP BY process_status;
        """
        result = db.execute(text(sql)).fetchall()
        
        print("\n=== 邮件处理状态统计 ===")
        total = 0
        for status, count in result:
            print(f"{status}: {count}")
            total += count
        print(f"总计: {total}")
        
        # 检查可能的问题邮件
        print("\n=== 检查问题邮件 ===")
        
        # 1. 检查长时间处于PROCESSING状态的邮件
        sql = """
        SELECT id, subject, update_time 
        FROM emails 
        WHERE process_status = 'PROCESSING'
        AND update_time < DATE_SUB(NOW(), INTERVAL 30 MINUTE);
        """
        stuck_emails = db.execute(text(sql)).fetchall()
        if stuck_emails:
            print(f"\n发现 {len(stuck_emails)} 封卡住的邮件:")
            for id, subject, update_time in stuck_emails:
                print(f"ID: {id}, 主题: {subject[:50]}..., 最后更新: {update_time}")
                
        # 2. 检查缺少必要字段的邮件
        sql = """
        SELECT id, subject 
        FROM emails 
        WHERE process_status IN ('NEW', 'FAILED')
        AND (content_text IS NULL OR content_text = '');
        """
        invalid_emails = db.execute(text(sql)).fetchall()
        if invalid_emails:
            print(f"\n发现 {len(invalid_emails)} 封缺少内容的邮件:")
            for id, subject in invalid_emails:
                print(f"ID: {id}, 主题: {subject[:50]}...")
                
    except Exception as e:
        print(f"检查过程中发生错误: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_email_status()
