
import io
import logging
import base64
import re
from PIL import Image
import pytesseract
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from urllib.request import urlopen

def extract_text_from_image(image_data: bytes) -> str:
    """从图片数据中提取文本"""
    try:
        # 将二进制数据转换为图像对象
        image = Image.open(io.BytesIO(image_data))
        
        # 使用OCR提取文本（使用中文和英文语言包）
        text = pytesseract.image_to_string(image, lang='chi_sim+eng')
        
        # 清理并返回文本
        return text.strip()
    except Exception as e:
        logging.error(f"图片文字识别失败: {e}")
        return ""

def extract_images_from_html(html_content: str) -> list:
    """从HTML中提取所有图片数据"""
    images = []
    try:
        # 提取base64编码的图片
        pattern = r'data:image/[^;]+;base64,([^"]+)'
        for match in re.finditer(pattern, html_content):
            try:
                img_data = base64.b64decode(match.group(1))
                images.append(img_data)
            except Exception as e:
                logging.error(f"Base64图片解码失败: {e}")
        
        # 提取图片URL
        pattern = r'src=["\']([^"\']+\.(?:png|jpg|jpeg))["\']'
        for match in re.finditer(pattern, html_content):
            try:
                url = match.group(1)
                with urlopen(url) as response:
                    images.append(response.read())
            except Exception as e:
                logging.error(f"下载图片失败 {url}: {e}")
                
        logging.info(f"从HTML中提取到 {len(images)} 张图片")
        return images
        
    except Exception as e:
        logging.error(f"提取HTML中的图片失败: {e}")
        return []

def capture_webpage_and_extract_text(html_content: str) -> str:
    """从网页截图中提取文本"""
    try:
        # 设置Chrome选项
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        # 初始化driver
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            # 保存HTML到临时文件并加载
            with open("temp.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            driver.get("file:///temp.html")
            
            # 等待页面加载完成
            driver.implicitly_wait(5)
            
            # 获取页面截图
            screenshot = driver.get_screenshot_as_png()
            capture_webpage_and_extract_text.last_image = screenshot
            
            # 从截图中提取文本
            return extract_text_from_image(screenshot)
            
        finally:
            driver.quit()
            
    except Exception as e:
        logging.error(f"网页截图失败: {e}")
        return ""

# 静态变量，用于存储最后的截图
capture_webpage_and_extract_text.last_image = None

def get_last_image():
    """获取最后一次网页截图"""
    return capture_webpage_and_extract_text.last_image
