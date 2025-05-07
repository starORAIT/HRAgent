import os
import logging
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from PIL import Image
from font_manager import FontManager
from bs4 import BeautifulSoup
import re
from .text_utils import html_to_text, sanitize_filename
from utils.log_utils import setup_logger
from utils.text_utils import extract_text_from_html  # 添加这行

def create_pdf_from_html(html_content: str) -> bytes:
    """将HTML内容转换为PDF"""
    logger = setup_logger('PDFUtils')
    pdf_buffer = BytesIO()
    
    try:
        font_manager = FontManager(os.path.dirname(os.path.dirname(__file__)))
        font_manager.initialize()
        font_name = font_manager.get_font_name()
        
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        width, height = letter
        margin = 50
        font_size = 10
        line_height = font_size * 1.2
        
        c.setFont(font_name, font_size)
        
        # 使用新的文本提取函数
        text = extract_text_from_html(html_content)
        logger.debug(f"提取到的文本长度: {len(text)}")
        
        if not text.strip():
            logger.warning("未能提取到有效文本内容")
            c.drawString(margin, height - margin, "No valid content extracted")
            c.save()
            return pdf_buffer.getvalue()
            
        text = re.sub(r'([。！？；])', r'\1\n', text)
        text = re.sub(r'\n+', '\n', text)

        x = margin
        y = height - margin
        
        for paragraph in text.split("\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                y -= line_height
                continue
            
            words = paragraph.split(" ")
            current_line = ""
            for word in words:
                test_line = current_line + (" " if current_line else "") + word
                if c.stringWidth(test_line, font_name, font_size) <= width - 2 * margin:
                    current_line = test_line
                else:
                    c.drawString(x, y, current_line)
                    y -= line_height
                    current_line = word
                    if y < margin:
                        c.showPage()
                        y = height - margin
                        c.setFont(font_name, font_size)
                        
            if current_line:
                c.drawString(x, y, current_line)
                y -= line_height
                if y < margin:
                    c.showPage()
                    y = height - margin
                    c.setFont(font_name, font_size)
        
        c.save()
        return pdf_buffer.getvalue()
    except Exception as e:
        logger.error(f"创建PDF失败: {e}", exc_info=True)
        return create_error_pdf(f"PDF创建失败: {str(e)}")
    finally:
        pdf_buffer.close()

def create_pdf_from_html_string(html_content: str, prefix: str) -> tuple:
    logger = setup_logger('PDFUtils')
    try:
        logger.debug(f"[PDF-1] 开始处理文件: {prefix}")
        
        if not html_content or not isinstance(html_content, str):
            logger.error(f"[PDF-2] 无效的HTML内容: type={type(html_content)}, "
                        f"length={len(html_content) if html_content else 0}")
            return ("", None)
            
        logger.debug(f"[PDF-3] HTML内容长度: {len(html_content)}")
        
        try:
            pdf_data = create_pdf_from_html(html_content)
            logger.debug(f"[PDF-4] PDF生成结果大小: {len(pdf_data) if pdf_data else 0}")
            
            if not pdf_data:
                logger.error("[PDF-5] PDF数据生成失败")
                return ("", None)
                
        except Exception as e:
            logger.error(f"[PDF-6] PDF生成异常: {e}", exc_info=True)
            return ("", None)
            
        filename = f"{prefix}.pdf"
        logger.debug(f"[PDF-7] 成功完成: {filename}, size={len(pdf_data)}")
        return (filename, pdf_data)
        
    except Exception as e:
        logger.error(f"[PDF-8] 创建PDF总体失败: {e}", exc_info=True)
        return ("", None)

def create_error_pdf(error_message: str = "Error creating PDF") -> bytes:
    """创建错误信息PDF"""
    pdf_buffer = BytesIO()
    try:
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        width, height = letter
        
        try:
            pdfmetrics.registerFont(TTFont('SimHei', os.path.join(os.path.dirname(__file__), "fonts", "simhei.ttf")))
            c.setFont('SimHei', 12)
        except:
            c.setFont('Helvetica', 12)
            
        c.drawString(30, height - 30, error_message)
        c.save()
        return pdf_buffer.getvalue()
    finally:
        pdf_buffer.close()

def create_pdf_with_screenshot(text_content: str, screenshot_path: str) -> bytes:
    """创建包含文本和截图的PDF"""
    pdf_buffer = BytesIO()
    
    # 初始化PDF和字体
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    width, height = A4
    font_manager = FontManager(os.path.dirname(os.path.dirname(__file__)))
    font_manager.initialize()
    font_name = font_manager.get_font_name()
    
    try:
        # 1. 添加文本页
        if text_content.strip():
            margin = 20 * mm
            font_size = 10
            line_height = font_size * 1.2
            c.setFont(font_name, font_size)
            y = height - margin
            
            for paragraph in text_content.split("\n"):
                if not paragraph.strip():
                    y -= line_height
                    continue
                
                words = paragraph.split(" ")
                current_line = ""
                for word in words:
                    test_line = current_line + (" " if current_line else "") + word
                    if c.stringWidth(test_line, font_name, font_size) <= (width - 2 * margin):
                        current_line = test_line
                    else:
                        c.drawString(margin, y, current_line)
                        y -= line_height
                        current_line = word
                        
                        if y < margin:
                            c.showPage()
                            y = height - margin
                            c.setFont(font_name, font_size)
                            
                if current_line:
                    c.drawString(margin, y, current_line)
                    y -= line_height
            
            c.showPage()

        # 2. 添加截图页面
        img = Image.open(screenshot_path)
        img_width, img_height = img.size
        
        # 设置页面边距为10mm
        margin = 10 * mm
        available_width = width - (2 * margin)
        available_height = height - (2 * margin)
        
        # 计算缩放比例
        width_ratio = available_width / img_width
        height_ratio = available_height / img_height
        scale_ratio = min(width_ratio, height_ratio)
        
        # 计算缩放后的尺寸
        scaled_width = img_width * scale_ratio
        scaled_height = img_height * scale_ratio
        
        # 在页面上居中显示
        x = (width - scaled_width) / 2
        y = height - margin - scaled_height
        
        # 处理大图片，可能需要多页
        if scaled_height > available_height:
            slice_height = int(available_height / scale_ratio)
            slices = (img_height + slice_height - 1) // slice_height
            
            for i in range(slices):
                top = i * slice_height
                bottom = min((i + 1) * slice_height, img_height)
                slice_img = img.crop((0, top, img_width, bottom))
                
                # 计算当前切片的缩放后高度
                current_height = (bottom - top) * scale_ratio
                y = height - margin - current_height
                
                c.drawImage(ImageReader(slice_img), 
                          x, y,
                          width=scaled_width,
                          height=current_height)
                
                if i < slices - 1:
                    c.showPage()
        else:
            c.drawImage(ImageReader(img),
                       x, y,
                       width=scaled_width,
                       height=scaled_height)
        
        c.save()
        return pdf_buffer.getvalue()
        
    except Exception as e:
        logging.error(f"创建PDF失败: {e}")
        return create_error_pdf(f"PDF创建失败: {str(e)}")
    finally:
        pdf_buffer.close()

def create_pdf_from_body(content: str, email_id=None) -> tuple:
    """将邮件正文内容转换为PDF并返回(文件名, PDF字节数据)"""
    try:
        filename = f"{email_id or 'unknown'}.pdf"
        pdf_data = create_pdf_from_html(content)
        if not pdf_data:
            return ("", None)
        return (filename, pdf_data)
    except Exception as e:
        logging.error(f"创建PDF失败: {e}")
        return ("", None)
