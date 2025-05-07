"""
系统配置模块

负责管理所有系统配置：
1. 从环境变量或配置文件加载设置
2. 提供默认值
3. 类型转换
4. 更新配置状态
"""

import os
import multiprocessing
from dotenv import load_dotenv
import logging

class Config:
    def __init__(self, env_file: str = ".env"):
        """
        初始化配置对象
        
        从.env文件加载配置，并设置默认值
        
        Args:
            env_file: 环境配置文件路径
        """
        load_dotenv(env_file, override=True)
        
        # 数据库配置
        self.DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
        self.DB_PORT = int(os.getenv("DB_PORT", "3306"))
        self.DB_USER = os.getenv("DB_USER", "root")
        self.DB_PASSWORD = os.getenv("DB_PASSWORD", "")
        self.DB_NAME = os.getenv("DB_NAME", "resume_db")

        self.IS_FIRST_RUN = os.getenv("IS_FIRST_RUN", "False").lower() == "true"
        self.EMAIL_FETCH_RANGE_DAYS = int(os.getenv("EMAIL_FETCH_RANGE_DAYS", "90"))  # 首次运行默认检查90天
        self.EMAIL_FETCH_RANGE_DAYS_ROLL = int(os.getenv("EMAIL_FETCH_RANGE_DAYS_ROLL", "30"))  # 滚动运行 默认检查30天
        self.EMAIL_FETCH_LIMIT = int(os.getenv("EMAIL_FETCH_LIMIT", "0"))  # Add this line

        # 多邮箱配置，格式: imapHost:imapPort:username:password，多邮箱用逗号分隔
        self.EMAIL_ACCOUNTS = os.getenv("EMAIL_ACCOUNTS", "").split(",")

        # 发件人域名->来源渠道映射（JSON格式）
        import json
        try:
            self.RESUME_CHANNELS = json.loads(os.getenv("RESUME_CHANNELS_JSON", "{}"))
        except Exception:
            self.RESUME_CHANNELS = {}

        # SMTP
        self.EMAIL_SENDER_SMTP = os.getenv("EMAIL_SENDER_SMTP")
        self.EMAIL_SENDER_PORT = int(os.getenv("EMAIL_SENDER_PORT", "587"))
        self.EMAIL_SENDER_USER = os.getenv("EMAIL_SENDER_USER")
        self.EMAIL_SENDER_PASSWORD = os.getenv("EMAIL_SENDER_PASSWORD")

        # OpenAI
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")
        self.AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "60"))  # Add default 60 seconds timeout
        self.AI_RETRY_TIMES = int(os.getenv("AI_RETRY_TIMES", "5"))
        self.MAX_TOKEN = int(os.getenv("MAX_TOKEN", "10000"))

        # Twilio短信(可选)
        self.TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
        self.TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
        self.TWILIO_FROM_PHONE = os.getenv("TWILIO_FROM_PHONE")

        self.RECRUITER_LIST = os.getenv("RECRUITER_LIST", "")
        self.REPORT_LIST = os.getenv("REPORT_LIST", "")

        self.EXPORT_MAIL_RANGE_DAYS = int(os.getenv("EXPORT_MAIL_RANGE_DAYS", "0"))

        # OSS配置
        self.OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID")
        self.OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET")
        self.OSS_BUCKET_NAME = os.getenv("OSS_BUCKET_NAME")
        self.OSS_ENDPOINT = os.getenv("OSS_ENDPOINT")
        self.OSS_CUSTOM_DOMAIN = os.getenv("OSS_CUSTOM_DOMAIN", "")

        self.MAX_ATTACHMENT_SIZE_MB = float(os.getenv("MAX_ATTACHMENT_SIZE_MB", "5"))
        # 并发配置
        self.PARSE_WORKERS = int(os.getenv("PARSE_WORKERS", "4"))
        self.FETCH_CHUNK_SIZE = int(os.getenv("FETCH_CHUNK_SIZE", "100"))
        self.FETCH_CONCURRENCY = int(os.getenv("FETCH_CONCURRENCY", "3"))

        # Embedding & Celery
        self.USE_EMBEDDING = os.getenv("USE_EMBEDDING", "False").lower() == "true"
        self.CACHE_EMBEDDINGS = os.getenv("CACHE_EMBEDDINGS", "False").lower() == "true"
        self.USE_CELERY = os.getenv("USE_CELERY", "False").lower() == "true"
        self.CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
        self.CELERY_BACKEND_URL = os.getenv("CELERY_BACKEND_URL", "redis://127.0.0.1:6379/0")

        self.AI_QUEUE_WORKERS = int(os.getenv("AI_QUEUE_WORKERS", "3"))
        self.BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
        self.BATCH_SLEEP = int(os.getenv("BATCH_SLEEP", "1"))  # 修改批次间隔1秒
        self.AI_RETRY_TIMES = int(os.getenv("AI_RETRY_TIMES", "5"))

        # Feishu API
        self.FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
        self.FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
        self.FEISHU_DOC_ID = os.getenv("FEISHU_DOC_ID")  # 统一使用DOC_ID
        self.FEISHU_SHEET_NAME = os.getenv("FEISHU_SHEET_NAME", "0")  # sheet id 默认为"0"
        self.FEISHU_SYNC_INTERVAL = int(os.getenv("FEISHU_SYNC_INTERVAL", "300"))
        self.FEISHU_SYNC_BATCH_SIZE = int(os.getenv("FEISHU_SYNC_BATCH_SIZE", "1000"))


        # 新增：日志配置
        self.LOG_DIR = os.getenv("LOG_DIR", "logs")
        self.LOG_FILENAME = os.getenv("LOG_FILENAME", "resume_screening.log")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s - %(levelname)s - %(message)s")
        self.LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 10 * 1024 * 1024))  # 默认10MB
        self.LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))  # 默认保留5个备份

        # 新增：配置不同渠道简历的处理类型，默认使用text类型，只有牛客网使用hyperlink
        import json
        try:
            default_types = {
                "nowcoder.com": "hyperlink"  # 牛客网默认为超链接型处理
            }
            self.RESUME_PROCESSING_TYPES = json.loads(os.getenv("RESUME_PROCESSING_TYPES_JSON", json.dumps(default_types)))
        except Exception:
            self.RESUME_PROCESSING_TYPES = {"nowcoder.com": "hyperlink"}

        # 新增：牛客网账号配置
        self.NOWCODER_USERNAME = os.getenv("NOWCODER_USERNAME", "")
        self.NOWCODER_PASSWORD = os.getenv("NOWCODER_PASSWORD", "")

        # 批处理配置
        self.BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1000"))  # 每批处理的邮件数
        self.BATCH_SLEEP = int(os.getenv("BATCH_SLEEP", "1"))   # 修改批次间隔1秒
        self.MAX_CONCURRENT_EMAILS = int(os.getenv("MAX_CONCURRENT_EMAILS", "50"))  # 最大并发处理邮件数
        self.DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))  # 数据库连接池大小
        self.DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))  # 数据库连接池最大溢出

        # 简历筛选配置
        self.SCREENING_BATCH_SIZE = int(os.getenv("SCREENING_BATCH_SIZE", "50"))  # 修改每批处理50封
        self.SCREENING_WORKERS = int(os.getenv("SCREENING_WORKERS", "5"))  # 修改并发线程数
        self.SCREENING_TIMEOUT = int(os.getenv("SCREENING_TIMEOUT", "600"))  # 筛选超时时间(秒)
        self.SCREENING_INTERVAL = int(os.getenv("SCREENING_INTERVAL", "30"))  # 批次间隔时间(秒)
        self.SCREENING_CHECK_INTERVAL = int(os.getenv('SCREENING_CHECK_INTERVAL', '60'))  # 检查间隔1分钟
        self.SCREENING_STALL_TIMEOUT = int(os.getenv('SCREENING_STALL_TIMEOUT', '30'))  # 停滞超时(分钟)

        # 性能优化配置
        self.MAX_CONCURRENT_PROCESSES = int(os.getenv("MAX_CONCURRENT_PROCESSES", str(min(32, multiprocessing.cpu_count()))))
        self.EMAIL_BATCH_SIZE = int(os.getenv("EMAIL_BATCH_SIZE", "1000"))
        self.EMAIL_SAVE_BATCH_SIZE = int(os.getenv("EMAIL_SAVE_BATCH_SIZE", "20"))  # 修改每次保存20封
        self.EMAIL_FETCH_INTERVAL = int(os.getenv("EMAIL_FETCH_INTERVAL", "300"))

        # 重复处理模式配置（移除new选项）
        self.DUPLICATE_MESSAGE_MODE = os.getenv("DUPLICATE_MESSAGE_MODE", "skip")  # skip/update
        self.DUPLICATE_RESUME_MODE = os.getenv("DUPLICATE_RESUME_MODE", "skip")    # skip/update

        self.MAX_TOKEN =int(os.getenv("MAX_TOKEN", "10000"))

        # 添加服务间隔时间配置
        self.EMAIL_CHECK_INTERVAL = int(os.getenv('EMAIL_CHECK_INTERVAL', '300'))  # 默认5分钟
        self.EXPORT_INTERVAL = int(os.getenv('EXPORT_INTERVAL', '300'))  # 默认5分钟
        self.EXPORT_BATCH_SIZE = int(os.getenv('EXPORT_BATCH_SIZE', '100'))  # 每次导出100条

    def update_first_run_status(self, status: bool = False):
        """
        更新首次运行状态
        
        Args:
            status: 首次运行状态标志
        """
        self.IS_FIRST_RUN = status
        # 如果需要持久化到环境文件，可以添加以下代码
        try:
            with open(self.env_file, 'r') as f:
                lines = f.readlines()
            
            with open(self.env_file, 'w') as f:
                for line in lines:
                    if line.startswith('IS_FIRST_RUN='):
                        f.write(f'IS_FIRST_RUN={str(status).lower()}\n')
                    else:
                        f.write(line)
        except Exception as e:
            logging.error(f"更新首次运行状态失败: {e}")
