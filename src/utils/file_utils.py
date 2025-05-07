import os
import logging
import oss2
from .text_utils import sanitize_filename

def save_attachments_for_debug(attachments, email_id):
    """保存附件到debug目录"""
    download_dir = os.path.abspath("download")
    os.makedirs(download_dir, exist_ok=True)
    
    for fname, fdata in attachments:
        try:
            safe_fname = sanitize_filename(f"{email_id}_{fname}")
            file_path = os.path.join(download_dir, safe_fname)
            with open(file_path, "wb") as f:
                f.write(fdata)
            logging.info(f"已保存附件到: {file_path}")
        except Exception as e:
            logging.error(f"保存附件失败: {e}")

def save_and_upload_attachment(fname, fdata, config):
    """保存并上传附件到OSS"""
    safe_fname = sanitize_filename(fname)
    download_dir = os.path.abspath("download")
    os.makedirs(download_dir, exist_ok=True)
    local_path = os.path.join(download_dir, safe_fname)
    
    with open(local_path, "wb") as f:
        f.write(fdata)
        
    try:
        auth = oss2.Auth(config.OSS_ACCESS_KEY_ID, config.OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, config.OSS_ENDPOINT, config.OSS_BUCKET_NAME)
        with open(local_path, "rb") as fp:
            bucket.put_object(safe_fname, fp)
        logging.info(f"附件 {safe_fname} 已上传至 OSS。")
    except Exception as e:
        logging.error(f"上传附件至 OSS 失败: {e}")

def get_wkhtmltopdf_path():
    """获取wkhtmltopdf可执行文件路径"""
    likely_paths = ["/usr/local/bin/wkhtmltopdf", "/opt/homebrew/bin/wkhtmltopdf"]
    for path in likely_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return "wkhtmltopdf"
