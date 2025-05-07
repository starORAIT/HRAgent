# utils.py
import time
import logging
import json
import openai
import re
import tiktoken

# 新增工具函数
def beijing_now():
    from datetime import datetime
    import pytz
    CHINA_TZ = pytz.timezone("Asia/Shanghai")
    return datetime.now(CHINA_TZ)

def md5_hash(text: str) -> str:
    import hashlib
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def create_db_session(config):
    """创建数据库会话"""
    from db_manager import DBManager, get_db
    db_manager = DBManager(config)
    db_manager.create_database_if_not_exists()
    db_manager.init_engine_and_session()
    return next(get_db())

# timer: 装饰器，用于计时并记录函数运行时间
def timer(func):
    """计时装饰器，记录函数执行时间"""
    def wrapper(*args, **kwargs):
        logging.debug(f"Entering {func.__name__}")
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logging.info(f"{func.__name__} 耗时 {elapsed:.4f} 秒")
        return elapsed if result is None else result
    return wrapper

# call_openai_with_retry: 调用OpenAI接口并支持多次重试
def call_openai_with_retry(func, config, *args, **kwargs):
    max_retry = config.AI_RETRY_TIMES
    for attempt in range(max_retry):
        try:
            return func(*args, **kwargs)
        except openai.error.RateLimitError as e:
            logging.error(f"OpenAI频率限制: {e}")
            wait_match = re.search(r"Please try again in ([\d.]+)s", str(e))
            if wait_match:
                wait_s = float(wait_match.group(1)) + 1
            else:
                wait_s = 30
            logging.warning(f"等待 {wait_s:.1f}s后重试 (attempt={attempt+1}/{max_retry})")
            time.sleep(wait_s)
        except openai.error.APIConnectionError as e:
            logging.error(f"OpenAI连接错误: {e}")
            time.sleep(10)
        except Exception as e:
            logging.error(f"OpenAI调用异常: {e}")
            time.sleep(5)
    raise RuntimeError(f"call_openai_with_retry 超过最大重试 {max_retry} 次，仍无法完成请求")

# truncate_text: 根据最大token数（简单按字符）截断文本
def truncate_text(text, max_tokens=4000, model="gpt-4"):
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]
        text = enc.decode(tokens)
    return text

# EmbeddingCache: 用于缓存embedding，避免重复调用OpenAI
class EmbeddingCache:
    def __init__(self, cache_file: str):
        self.cache_file = cache_file
        self.cache = {}
        self.load()

    def load(self):
        import os, json
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def save(self):
        import json
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def get(self, key: str):
        return self.cache.get(key)

    def set(self, key: str, value):
        self.cache[key] = value

