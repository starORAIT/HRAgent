import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def create_db_session(config):
    """Create a new database session"""
    db_url = (
        f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}"
        f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}?charset=utf8mb4"
    )
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW
    )
    Session = sessionmaker(bind=engine)
    return Session()
