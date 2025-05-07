import logging
import re
from bs4 import BeautifulSoup
from email.header import decode_header
from utils.log_utils import setup_logger
import warnings
 
def decode_subject(subject):
    """解码邮件主题"""
    parts = decode_header(subject)
    out = ""
    for t, enc in parts:
        if isinstance(t, bytes):
            try:
                out += t.decode(enc or 'utf-8', 'ignore')
            except Exception:
                out += t.decode('utf-8', 'ignore')
        else:
            out += t
    return out

def extract_text_from_html(html_content: str) -> str:
    """从HTML中提取清理后的文本内容"""
    logger = setup_logger('TextUtils')
    try:
        if not html_content:
            logger.warning("输入HTML内容为空")
            return ""
            
        logger.debug(f"处理HTML内容: {len(html_content)}字节")
        
        # 使用BeautifulSoup解析HTML
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=UserWarning)
            soup = BeautifulSoup(html_content, 'html.parser')
            
        # 移除不需要的元素
        for tag in soup(['script', 'style', 'head', 'title', 'meta', '[document]', 'iframe', 'noscript']):
            tag.decompose()
            
        # 替换特殊标签为换行
        for tag in soup.find_all(['br', 'p', 'div', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            tag.append('\n')
            
        # 提取文本
        text = soup.get_text(separator='\n', strip=True)
        
        # 清理文本
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if line:  # 只保留非空行
                # 去除可能的控制字符
                line = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', line)
                # 规范化空白字符
                line = re.sub(r'\s+', ' ', line)
                lines.append(line)
                
        cleaned_text = '\n'.join(lines)
        logger.debug(f"提取到文本: {len(cleaned_text)}字节")
        
        # 记录一些统计信息
        if cleaned_text:
            logger.info(f"提取结果: {len(lines)}行, 平均每行{sum(len(l) for l in lines)/len(lines):.1f}字符")
        else:
            logger.warning("提取结果为空")
            
        return cleaned_text
        
    except Exception as e:
        logger.error(f"HTML文本提取失败: {e}", exc_info=True)
        return ""

def html_to_text(html_content: str) -> str:
    return extract_text_from_html(html_content)

def extract_clean_text(text: str) -> str:
    """清理文本内容，去除无用字符"""
    if not text:
        return ""
    
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 替换特殊空白字符为普通空格
    text = re.sub(r'[\u00A0\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F]', ' ', text)
    
    # 替换多个空格为单个空格
    text = re.sub(r'\s+', ' ', text)
    
    # 去除首尾空白
    return text.strip()

def decode_attachment_filename(raw_fname):
    """解码附件文件名"""
    if not raw_fname:
        return ""
    try:
        if "=?" in raw_fname:
            parts = decode_header(raw_fname)
            fname = ""
            for part, charset in parts:
                if isinstance(part, bytes):
                    fname += part.decode(charset or 'utf-8', 'ignore')
                else:
                    fname += str(part)
            return fname
        return raw_fname
    except Exception as e:
        logging.error(f"解码附件文件名失败: {raw_fname}, 错误: {e}")
        return raw_fname

def sanitize_filename(name: str) -> str:
    """清理文件名，移除不合法字符"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)
