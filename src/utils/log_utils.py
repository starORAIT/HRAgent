"""
日志工具模块

提供统一的日志配置和管理：
1. 日志格式化
2. 控制台和文件双重输出
3. 日志过滤
4. 日志轮转
"""

import logging
import sys
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name=None, log_dir='logs'):
    """
    设置日志配置
    
    创建和配置日志记录器，支持：
    1. 控制台输出
    2. 文件日志（可选）
    3. 日志过滤（只显示重要信息）
    4. 日志大小轮转
    
    Args:
        name: 日志记录器名称
        log_dir: 日志文件目录路径
        
    Returns:
        Logger: 配置好的日志记录器
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)

    # 简化格式，只保留时间、进程名和消息
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(message)s'
    )
    
    # 过滤不必要的DEBUG日志
    class KeyInfoFilter(logging.Filter):
        def filter(self, record):
            # 总是显示ERROR及以上级别的日志
            if record.levelno >= logging.ERROR:
                return True
                
            # 只显示包含关键词的INFO日志
            if record.levelno == logging.INFO:
                keywords = [
                    "任务开始", "任务完成", "处理进度", "成功处理",
                    "发现", "处理完成", "统计", "失败", "错误"
                ]
                return any(k in record.msg for k in keywords)
            return False

    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(KeyInfoFilter())
    logger.addHandler(console_handler)

    # 如果指定了日志目录，添加文件处理器
    if log_dir:
        try:
            # 确保日志目录存在
            os.makedirs(log_dir, exist_ok=True)
            
            # 创建按大小轮转的文件处理器
            log_file = os.path.join(log_dir, f'{name or "app"}.log')
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(KeyInfoFilter())
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Failed to setup file logging: {e}")

    return logger

def get_logger(name=None):
    """
    获取已配置的logger实例
    
    Args:
        name: 日志记录器名称
        
    Returns:
        Logger: 指定名称的日志记录器
    """
    return logging.getLogger(name)
