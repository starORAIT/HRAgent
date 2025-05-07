from .text_utils import (
    extract_clean_text, 
    html_to_text, 
    sanitize_filename,
    decode_subject,          # Add this
    decode_attachment_filename  # Add this
)
from .pdf_utils import (
    create_pdf_from_html,
    create_pdf_from_html_string,
    create_error_pdf,
    create_pdf_with_screenshot,
    create_pdf_from_body
)
from .file_utils import save_attachments_for_debug, save_and_upload_attachment, get_wkhtmltopdf_path
from .db_utils import create_db_session
from .oss_helper import upload_to_oss

def truncate_text_field(text: str, max_length: int = 65000) -> str:
    """截断文本字段，确保不超过数据库字段长度限制
    
    Args:
        text (str): 要处理的文本
        max_length (int): 最大长度限制，默认65000
        
    Returns:
        str: 处理后的文本
    """
    if not text:
        return ""
    if len(text) > max_length:
        return text[:max_length-3] + "..."
    return text

__all__ = [
    'extract_clean_text',
    'html_to_text',
    'sanitize_filename',
    'decode_subject',           # Add this
    'decode_attachment_filename', # Add this
    'create_pdf_from_html',
    'create_pdf_from_html_string',
    'create_error_pdf',
    'create_pdf_with_screenshot',
    'create_pdf_from_body',
    'save_attachments_for_debug',
    'save_and_upload_attachment',
    'get_wkhtmltopdf_path',
    'create_db_session',
    'upload_to_oss',
]
