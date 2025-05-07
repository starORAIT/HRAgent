import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import traceback

class LogManager:
    @staticmethod
    def setup_logging(config):
        """配置日志系统，同时输出到文件和控制台"""
        try:
            # 确保日志目录存在
            os.makedirs(config.LOG_DIR, exist_ok=True)
            
            # 生成带日期的日志文件名
            today = datetime.now().strftime('%Y%m%d')
            log_file = os.path.join(config.LOG_DIR, f"screening_{today}.log")
            
            # 配置根日志记录器
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)
            
            # 如果已经有handlers，先清除
            if root_logger.handlers:
                root_logger.handlers.clear()
                
            # 日志格式
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - [%(processName)s:%(threadName)s] - %(message)s'
            )
            
            # 文件处理器（按大小滚动）
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            root_logger.addHandler(file_handler)
            
            # 控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.INFO)
            root_logger.addHandler(console_handler)
            
            # 记录启动信息
            logging.info(f"日志系统初始化完成，日志文件：{log_file}")
            
            # 设置异常处理器，确保未捕获的异常也被记录
            def handle_exception(exc_type, exc_value, exc_traceback):
                if issubclass(exc_type, KeyboardInterrupt):
                    sys.__excepthook__(exc_type, exc_value, exc_traceback)
                    return
                logging.error("未捕获的异常:", exc_info=(exc_type, exc_value, exc_traceback))
            
            sys.excepthook = handle_exception
            
        except Exception as e:
            print(f"设置日志系统失败: {e}")
            print(traceback.format_exc())
            sys.exit(1)
