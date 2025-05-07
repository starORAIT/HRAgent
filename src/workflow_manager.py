"""
工作流管理模块

系统的总控制器，负责：
1. 初始化并启动各个功能模块
2. 协调不同模块之间的工作
3. 监控进程状态
4. 处理异常情况
"""

import multiprocessing as mp
from config import Config
import logging
import time
from log_manager import LogManager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def run_email_fetching(config_dict):
    """
    运行邮件获取进程
    
    初始化配置并启动邮件获取模块
    
    Args:
        config_dict: 配置字典
    """
    from email_fetching import run_email_fetching
    from config import Config
    # 重建配置对象
    config = Config.__new__(Config)
    for k, v in config_dict.items():
        setattr(config, k, v)
    run_email_fetching(config)

def run_screening(config_dict):
    """
    运行简历筛选进程
    
    初始化配置并启动简历筛选模块
    
    Args:
        config_dict: 配置字典
    """
    from screening import run_screening
    from config import Config
    # 重建配置对象
    config = Config.__new__(Config)
    for k, v in config_dict.items():
        setattr(config, k, v)
    run_screening(config)

def run_sync_and_export(config_dict):
    """
    运行同步导出进程
    
    初始化配置并启动数据同步导出模块
    
    Args:
        config_dict: 配置字典
    """
    from sync_and_export import run_sync_and_export
    from config import Config
    # 重建配置对象
    config = Config.__new__(Config)
    for k, v in config_dict.items():
        setattr(config, k, v)
    run_sync_and_export(config)

def main():
    """
    主函数
    
    初始化系统并启动所有功能模块：
    1. 邮件获取
    2. 简历筛选
    3. 数据同步导出
    
    监控进程状态，处理异常退出情况
    """
    # 初始化配置和日志
    config = Config("config/.env")
    LogManager.setup_logging(config)
    logging.info("=== 招聘自动化系统启动 ===")
    
    # 将配置对象转换为字典
    config_dict = {k: v for k, v in config.__dict__.items() 
                  if not k.startswith('_') and not callable(v)}
    
    # 创建并启动进程
    processes = {
        'email': mp.Process(
            name='EmailFetcher',
            target=run_email_fetching,
            args=(config_dict,)
        ),
        'screen': mp.Process(
            name='Screener',
            target=run_screening,
            args=(config_dict,)
        ),
        'sync': mp.Process(
            name='Syncer',
            target=run_sync_and_export,
            args=(config_dict,)
        )
    }
    
    # 启动所有进程
    for name, process in processes.items():
        logging.info(f"启动进程: {process.name} (PID: {process.pid})")
        process.start()
    
    # 调整进程监控的日志输出
    try:
        while True:
            status = {name: process.is_alive() for name, process in processes.items()}
            
            # 只在状态变化时输出日志
            if status != getattr(main, 'last_status', None):
                logging.info("进程状态: " + 
                           ", ".join(f"{name}: {'运行中' if alive else '已停止'}"
                                   for name, alive in status.items()))
                main.last_status = status
            
            # 检查是否有进程异常退出
            for name, process in list(processes.items()):
                if not process.is_alive() and process.exitcode != 0:
                    logging.error(f"进程异常退出: {name} (退出码: {process.exitcode})")
                    del processes[name]
                
            if not processes:
                break
            time.sleep(5)  # 降低检查频率
            
    except KeyboardInterrupt:
        logging.info("收到终止信号，正在停止所有进程...")
        for process in processes.values():
            process.terminate()
            process.join()
    
    logging.info("=== 招聘自动化系统已停止 ===")

if __name__ == "__main__":
    main()
