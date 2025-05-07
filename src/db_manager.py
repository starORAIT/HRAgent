# db_manager.py
import time
import logging
import pymysql
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.dialects.mysql import LONGTEXT
from datetime import datetime
import pytz

CHINA_TZ = pytz.timezone("Asia/Shanghai")
Base = declarative_base()

def beijing_now():
    """返回当前北京时间"""
    return datetime.now(CHINA_TZ)

# Candidate: 候选人数据表，记录简历及AI筛选结果
class Candidate(Base):
    __tablename__ = "Candidates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 基本信息字段
    name = Column(String(50))
    apply_position = Column(String(100))
    phone = Column(String(50))
    email = Column(String(100))
    wechat = Column(String(100))
    latest_company = Column(String(100))
    work_experience = Column(String(100))
    highest_education = Column(String(50))
    highest_university = Column(String(100))
    first_education = Column(String(50))
    first_university = Column(String(100))
    marital_status = Column(String(20))
    age = Column(Integer)
    gender = Column(String(10))
    expected_salary = Column(String(50))
    resume_source = Column(String(100))

    # 总体评估结果
    total_score = Column(Integer, default=0, comment="总分(0-100)")
    is_qualified = Column(Boolean, default=False, comment="是否通过初筛")

    # AI分析结果
    education_score = Column(Integer, default=0, comment="教育背景得分(0-20)")
    education_detail = Column(Text, comment="教育背景评价详情")
    technical_score = Column(Integer, default=0, comment="技术实力得分(0-20)")
    technical_detail = Column(Text, comment="技术实力评价详情")
    innovation_score = Column(Integer, default=0, comment="创新潜力得分(0-20)")
    innovation_detail = Column(Text, comment="创新潜力评价详情")
    growth_score = Column(Integer, default=0, comment="成长速度得分(0-20)")
    growth_detail = Column(Text, comment="成长速度评价详情")
    startup_score = Column(Integer, default=0, comment="创业特质得分(0-10)")
    startup_detail = Column(Text, comment="创业特质评价详情")
    teamwork_score = Column(Integer, default=0, comment="团队协作得分(0-10)")
    teamwork_detail = Column(Text, comment="团队协作评价详情")
    
    focus_flag = Column(Boolean, default=False, comment="是否重点关注")
    risk = Column(Text, comment="风险提示")
    questions = Column(Text, comment="面试问题")
    

    # 简历文件和来源信息
    resume_file_url = Column(Text, comment="简历文件OSS URL，从Email表同步")
    resume_hash = Column(String(64), comment="简历内容哈希值,与Email表保持一致")
    email_subject = Column(String(500), comment="来源邮件主题")
    inbox_account = Column(String(200), comment="来源邮箱账号")
    mail_sent_time = Column(DateTime, comment="邮件发送时间")
    resume_text = Column(LONGTEXT, comment="纯文本格式的简历内容")

    # 其他系统字段
    status = Column(String(50), default="NEW", comment="处理状态")
    create_time = Column(DateTime, default=beijing_now)
    update_time = Column(DateTime, default=beijing_now, onupdate=beijing_now)
    

# CandidateEmbedding: 存储候选人embedding数据（JSON格式）
class CandidateEmbedding(Base):
    __tablename__ = "candidate_embeddings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer)
    embedding    = Column(Text)
    create_time  = Column(DateTime, default=beijing_now)

# Email: 存储邮件数据
class Email(Base):
    __tablename__ = "emails"
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(200))
    subject = Column(String(500))
    from_address = Column(String(200))
    content_text = Column(LONGTEXT)
    content_html = Column(LONGTEXT)
    attachments_info = Column(Text)  # JSON格式存储附件信息
    received_date = Column(DateTime)
    process_status = Column(String(50), default="NEW", index=True)  # 添加索引以加快查询
    error_message = Column(Text)
    candidate_id = Column(Integer, nullable=True)
    resume_hash = Column(String(64), comment="简历内容哈希值，基于最终提取的文本内容计算")
    attachment_url = Column(Text, comment="OSS附件URL，邮件处理时上传生成")
    inbox_account = Column(String(200), comment="收件邮箱账号")
    create_time = Column(DateTime, default=beijing_now)
    update_time = Column(DateTime, default=beijing_now, onupdate=beijing_now)

# ProcessingBatch: 存储处理批次数据
class ProcessingBatch(Base):
    __tablename__ = "processing_batches"
    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(50))
    total_count = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String(50), default="RUNNING")  # RUNNING, COMPLETED, FAILED
    create_time = Column(DateTime, default=beijing_now)

# Global engine for SQLAlchemy
engine = None
SessionLocal = None

class DBManager:
    def __init__(self, config):
        """初始化数据库管理器，保存配置参数"""
        self.config = config

    def create_database_if_not_exists(self):
        """若数据库不存在则自动创建"""
        conn = pymysql.connect(
            host=self.config.DB_HOST,
            port=self.config.DB_PORT,
            user=self.config.DB_USER,
            password=self.config.DB_PASSWORD,
            charset="utf8mb4"
        )
        try:
            with conn.cursor() as cur:
                sql = f"CREATE DATABASE IF NOT EXISTS `{self.config.DB_NAME}` DEFAULT CHARACTER SET utf8mb4;"
                cur.execute(sql)
            conn.commit()
        except Exception as e:
            logging.error(f"创建数据库失败: {e}")
        finally:
            conn.close()

    def init_engine_and_session(self):
        """初始化数据库引擎与会话"""
        global engine, SessionLocal
        start_t = time.time()
        db_url = (
            f"mysql+pymysql://{self.config.DB_USER}:{self.config.DB_PASSWORD}"
            f"@{self.config.DB_HOST}:{self.config.DB_PORT}/{self.config.DB_NAME}?charset=utf8mb4"
        )
        try:
            # Add pool configuration
            engine = create_engine(
                db_url, 
                echo=False, 
                pool_pre_ping=True,
                pool_size=self.config.DB_POOL_SIZE,
                max_overflow=self.config.DB_MAX_OVERFLOW
                
            )
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            
            # Create all tables
            Base.metadata.create_all(bind=engine)
            logging.info("数据库表结构已同步")
            
        except Exception as e:
            logging.error(f"数据库初始化失败: {e}")
            raise

        cost = time.time() - start_t
        logging.info(f"[DBManager] init_engine_and_session 耗时={cost:.2f}s")

def get_db():
    """获取数据库会话"""
    if not SessionLocal:
        raise RuntimeError("Database not initialized. Call DBManager.init_engine_and_session first.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_unprocessed_emails(session, batch_size=1000):
    """获取未处理的邮件批次，使用process_status判断"""
    try:
        # 添加错误处理和详细日志
        total = session.query(Email).filter(
            Email.process_status.in_(["NEW", "FAILED"])
        ).count()
        
        if total == 0:
            logging.info("数据库中没有待处理的邮件")
            return []

        emails = session.query(Email).filter(
            Email.process_status.in_(["NEW", "FAILED"])
        ).order_by(
            Email.id
        ).limit(batch_size).all()
        
        if emails:
            logging.info(f"获取到 {len(emails)} 封待处理邮件（总计 {total} 封）")
            for email in emails:
                logging.info(
                    f"待处理邮件详情:\n"
                    f"ID={email.id}\n"
                    f"状态={email.process_status}\n"
                    f"主题={email.subject[:50]}...\n"
                    f"内容长度={len(email.content_text) if email.content_text else 0}"
                )
        else:
            logging.warning(f"未获取到邮件，但数据库中有 {total} 封待处理邮件")
            
        return emails
        
    except Exception as e:
        logging.error(f"获取未处理邮件时发生错误: {e}")
        return []

def mark_email_processing(session, email_id):
    """标记邮件为处理中"""
    session.query(Email).filter_by(id=email_id).update({
        "process_status": "PROCESSING",
        "update_time": beijing_now()
    })
    session.commit()

def check_duplicate_email(session, message_id=None, inbox_account=None):
    """检查是否存在重复邮件，基于message_id(mid)和inbox_account的组合"""
    if message_id and inbox_account:
        return session.query(Email).filter_by(
            message_id=str(message_id),  # 确保mid转为字符串
            inbox_account=inbox_account
        ).first()
    return None

def get_processed_message_ids(session, inbox_account):
    """获取指定邮箱已处理的邮件ID列表"""
    try:
        processed_ids = set(
            str(row[0]) for row in 
            session.query(Email.message_id)
            .filter(
                Email.inbox_account == inbox_account,
                Email.message_id.isnot(None)
            ).all()
        )
        logging.info(f"获取到邮箱 {inbox_account} 的 {len(processed_ids)} 个已处理邮件ID")
        return processed_ids
    except Exception as e:
        logging.error(f"获取已处理邮件ID失败: {e}")
        return set()
