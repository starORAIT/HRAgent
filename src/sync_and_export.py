"""
数据同步与导出模块

负责将候选人数据同步到飞书等外部系统：
1. 初始化数据库连接
2. 执行定期同步
3. 处理同步错误
"""

import logging
import time
from config import Config
from db_manager import DBManager, get_db, Candidate
from log_manager import LogManager
from utils.log_utils import setup_logger
from feishu_sync import sync_candidates_to_feishu

def run_sync_and_export(config):
    """
    运行同步导出服务
    
    定期将数据库中的候选人数据同步到飞书表格
    
    Args:
        config: 配置对象
    """
    logger = setup_logger('SyncExport')
    logger.info("======= 同步导出服务启动 =======")
    
    while True:  # 添加外层循环使服务持续运行
        try:
            logger.info("【数据导出】任务开始")
            
            # 初始化数据库
            db_manager = DBManager(config)
            db_manager.create_database_if_not_exists()
            db_manager.init_engine_and_session()
            
            # 使用get_db()创建会话
            try:
                db = next(get_db())
                logger.info("开始同步数据到飞书...")
                
                # 直接调用已有的飞书同步函数
                sync_candidates_to_feishu(config, db)
                
            except Exception as e:
                logger.error(f"数据导出失败: {e}")
                if 'db' in locals():
                    db.rollback()
            finally:
                if 'db' in locals():
                    db.close()
            
            logger.info("【数据导出】任务完成")
            
            # 等待下一轮导出
            logger.info(f"本轮导出完成，等待{config.EXPORT_INTERVAL}秒后开始下一轮...")
            time.sleep(config.EXPORT_INTERVAL)
            
        except Exception as e:
            logger.error(f"同步导出异常: {e}", exc_info=True)
            time.sleep(300)  # 错误恢复等待5分钟

if __name__ == "__main__":
    config = Config("config/.env")
    LogManager.setup_logging(config)
    run_sync_and_export(config)
