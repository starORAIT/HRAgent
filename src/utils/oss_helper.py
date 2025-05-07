import os
import logging
import oss2
import pytz
from datetime import datetime

def upload_to_oss(filename: str, filedata: bytes, config, prefix: str = "") -> str:
    """
    上传文件到阿里云OSS
    
    Args:
        filename: 文件名
        filedata: 文件内容(二进制)
        config: 配置对象，需包含OSS配置
        prefix: 文件路径前缀，例如 "resumes/202502"
        
    Returns:
        str: 文件的访问URL，上传失败返回空字符串
    """
    try:
        # 创建OSS认证对象
        auth = oss2.Auth(config.OSS_ACCESS_KEY_ID, config.OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, config.OSS_ENDPOINT, config.OSS_BUCKET_NAME)
        
        # 生成OSS中的文件路径
        if prefix:
            prefix = prefix.rstrip('/') + '/'
            
        # Fix: use datetime.now(UTC)
        timestamp = datetime.now(pytz.UTC).strftime('%Y%m%d_%H%M%S')
        safe_filename = os.path.basename(filename)  # 移除路径中的目录部分
        object_name = f"{prefix}{timestamp}_{safe_filename}"
        
        # 上传文件
        result = bucket.put_object(object_name, filedata)
        if result.status == 200:
            # 生成文件访问URL
            if config.OSS_CUSTOM_DOMAIN:
                url = f"https://{config.OSS_CUSTOM_DOMAIN}/{object_name}"
            else:
                url = f"https://{config.OSS_BUCKET_NAME}.{config.OSS_ENDPOINT}/{object_name}"
            logging.info(f"文件已上传到OSS: {url}")
            return url
            
        logging.error(f"上传文件到OSS失败，状态码: {result.status}")
        return ""
        
    except Exception as e:
        logging.error(f"上传文件到OSS出错: {str(e)}")
        return ""
