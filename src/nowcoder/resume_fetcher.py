import logging
import asyncio
import os
import sys
from playwright.async_api import async_playwright, TimeoutError
from bs4 import BeautifulSoup
import re
from utils.log_utils import setup_logger

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.text_utils import extract_clean_text, html_to_text
from utils.pdf_utils import create_pdf_from_body, create_pdf_with_screenshot

async def fetch_resume_from_link(html_content: str, email_id: str = None) -> tuple:
    """从HTML内容中提取并获取牛客网简历链接内容"""
    logger = setup_logger(f'ResumeFetcher-{email_id}')
    try:
        if not html_content:
            logger.warning("HTML内容为空")
            return ("", None)
        
        logging.info(f"[简历提取] 开始处理邮件ID: {email_id}")
        
        if not html_content:
            logging.warning(f"[简历提取] 邮件{email_id}: HTML内容为空")
            return ("", None)
            
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 1. 提取初始简历文本
            text_content = html_to_text(html_content)
            base_info = extract_nowcoder_base_info(text_content, html_content)

            # 2. 寻找并清理简历链接
            urls = extract_nowcoder_links(html_content)
            logging.info(f"[简历提取] 邮件{email_id}: 提取到链接数量: {len(urls)}")
            
            if not urls:
                logger.warning("未找到简历链接")
                if base_info:
                    logger.info("使用基本信息创建PDF")
                    try:
                        pdf_result = create_pdf_from_body(base_info, email_id)
                        if not isinstance(pdf_result, tuple) or len(pdf_result) != 2:
                            logger.warning("创建PDF返回值无效")
                            return ("", None)
                        return (base_info, pdf_result)
                    except Exception as e:
                        logger.error(f"创建PDF失败: {e}")
                        return ("", None)
                return ("", None)
                
            # 3. 尝试通过浏览器获取完整简历
            temp = await fetch_resume_via_browser(urls[0], email_id)
            if not (temp and isinstance(temp, tuple) and len(temp) == 2):
                logging.warning(f"fetch_resume_via_browser返回无效结果, email_id={email_id}")
                temp = ("", None)
            resume_text, attachment = temp
            
            # 4. 如果浏览器获取失败，回退到基本信息
            if not resume_text.strip() and base_info:
                resume_text = base_info
                if not attachment:
                    pdf_result = create_pdf_from_body(base_info, email_id)
                    if not (pdf_result and isinstance(pdf_result, tuple) and len(pdf_result) == 2):
                        pdf_result = ("", None)
                    attachment = pdf_result
                    
            # 确保返回值始终为元组
            if resume_text is None:
                resume_text = ""
            return (resume_text, attachment)
            
        except Exception as e:
            logging.error(f"[简历提取] 邮件{email_id}: 处理失败 - {str(e)}", exc_info=True)
            return ("", None)
        
    except Exception as e:
        logger.error(f"处理简历失败: {e}", exc_info=True)
        return ("", None)

def extract_nowcoder_base_info(text_content: str, html_content: str = "") -> str:
    """从牛客邮件中提取基本信息"""
    if not text_content or not ("你发布的" in text_content and "查看完整简历" in text_content):
        return ""
        
    lines = text_content.split("\n")
    info_parts = []
    in_info_section = False
    
    # 先提取简历链接
    urls = extract_nowcoder_links(html_content)
    if urls:
        info_parts.append("简历链接:")
        for url in urls:
            info_parts.append(url)
        info_parts.append("")
    
    # 提取其他基本信息
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if "你发布的" in line:
            try:
                position = line.split(']')[0].split('[')[-1]
                info_parts.append(f"应聘岗位: {position}")
                in_info_section = True
            except:
                pass
            continue
            
        if in_info_section:
            if "注：此邮件为系统邮件" in line:
                break
            if any(x in line for x in ["岁", "届", "男", "女", "本科", "硕士", "博士", "工作", "实习"]):
                info_parts.append(line)
    
    return "\n".join(info_parts)

def extract_nowcoder_links(html_content: str) -> list:
    """提取牛客网简历链接"""
    if not isinstance(html_content, str):
        return []
    
    logging.info("开始提取牛客网简历链接...")
    soup = BeautifulSoup(html_content, "lxml")
    urls = []
    
    # 1. 直接匹配"查看完整简历"链接
    for a in soup.find_all("a"):
        text = a.get_text().strip()
        href = a.get("href", "").strip()
        
        if "查看完整简历" in text and href:
            if not href.startswith('http'):
                href = 'https://www.nowcoder.com' + href.lstrip('/')
            urls.append(href)
    
    # 2. 如果没找到，尝试所有链接文本中包含"简历"的链接
    if not urls:
        for a in soup.find_all("a"):
            text = a.get_text().strip()
            href = a.get("href", "").strip()
            if "简历" in text and href and "nowcoder.com" in href.lower():
                if not href.startswith('http'):
                    href = 'https://www.nowcoder.com' + href.lstrip('/')
                urls.append(href)
    
    # 3. 如果还是没找到，尝试正则匹配
    if not urls:
        pattern = r'https?://[^"\'\s<>]+?nowcoder\.com/jobs/resume/preview/complete/[^"\'\s<>]+'
        matches = re.findall(pattern, html_content, re.I)
        for url in matches:
            urls.append(url)
    
    return list(set(urls))  # 去重后返回

def extract_nowcoder_text_from_spans(html_content: str) -> str:
    """从预览窗格提取简历文本"""
    if not html_content:
        return ""
        
    soup = BeautifulSoup(html_content, "lxml")
    spans = soup.find_all("span", attrs={"role": "presentation", "dir": "ltr"})
    
    resume_parts = {}
    last_top = None
    
    for span in spans:
        try:
            style = span.get("style", "")
            if "top:" not in style:
                continue
                
            top = float(style.split("top: ")[1].split("px")[0])
            text = span.get_text(strip=True)
            
            if not text:
                continue
                
            if last_top is not None and abs(top - last_top) < 2:  # 2px误差范围内认为是同一行
                resume_parts[last_top] = resume_parts[last_top] + " " + text
            else:
                resume_parts[top] = text
                last_top = top
                
        except (IndexError, ValueError) as e:
            logging.error(f"解析span样式失败: {e}")
            continue
    
    # 按垂直位置排序重组文本
    sorted_texts = []
    for k in sorted(resume_parts.keys()):
        line = resume_parts[k].strip()
        # 如果是标题行，增加额外换行
        if re.match(r'^[【\[\(].+?[\]\)】]$', line) or line.isupper():
            sorted_texts.extend(['', line, ''])
        else:
            sorted_texts.append(line)
    
    return "\n".join(sorted_texts)

async def fetch_resume_via_browser(url: str, email_id=None) -> tuple:
    """使用 Playwright 获取动态加载的简历内容"""
    max_attempts = 3  # 增加重试次数
    debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    logger = setup_logger(f'ResumeFetcher-{email_id}')

    browser = None
    context = None
    
    for attempt in range(max_attempts):
        try:
            logger.info(f"[尝试 {attempt + 1}/{max_attempts}] 访问链接: {url}")
            p = await async_playwright().start()
            
            # 配置浏览器启动选项
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-web-security',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                ]
            )

            # 创建上下文
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                ignore_https_errors=True
            )

            page = await context.new_page()
            
            # 简化请求拦截
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ['image', 'media', 'font', 'stylesheet'] 
                else route.continue_())

            # 增加超时时间，使用DOM内容加载而不是networkidle
            logger.info(f"[尝试 {attempt + 1}] 开始加载页面...")
            await page.goto(
                url, 
                wait_until='domcontentloaded',
                timeout=60000  # 增加到60秒
            )
            
            # 等待页面稳定
            logger.info(f"[尝试 {attempt + 1}] 等待页面稳定...")
            await page.wait_for_load_state('networkidle', timeout=10000)
            await page.wait_for_timeout(2000)  # 额外等待2秒

            try:
                # 按优先级检查多个可能的内容容器
                selectors = [
                    ".textLayer",
                    "#resumeContentContainer", 
                    ".resume-content",
                    "body"  # 如果其他都失败，尝试整个body
                ]
                
                content = None
                resume_text = ""
                
                for selector in selectors:
                    try:
                        logger.info(f"[尝试 {attempt + 1}] 检查选择器: {selector}")
                        element = await page.wait_for_selector(selector, timeout=5000)
                        if element:
                            content = await element.inner_html()
                            if content and content.strip():
                                if selector == ".textLayer":
                                    resume_text = extract_nowcoder_text_from_spans(content)
                                else:
                                    text = await element.text_content()
                                    resume_text = extract_clean_text(text)
                                
                                if resume_text.strip():
                                    logger.info(f"[成功] 通过选择器 {selector} 获取到内容")
                                    break
                    except Exception as e:
                        logger.warning(f"选择器 {selector} 处理失败: {e}")
                        continue

                if resume_text.strip():
                    screenshot_path = os.path.join(debug_dir, f"resume_{email_id}.png")
                    await page.screenshot(path=screenshot_path, full_page=True)
                    
                    pdf_fname = f"resume_{email_id}.pdf"
                    pdf_data = create_pdf_with_screenshot(resume_text, screenshot_path)
                    
                    os.unlink(screenshot_path)
                    return resume_text, (pdf_fname, pdf_data)
                    
            except Exception as e:
                logger.error(f"[尝试 {attempt + 1}] 内容提取失败: {e}")
                
            # 如果失败，截图用于调试
            if attempt == max_attempts - 1:
                logger.error("所有尝试均失败，保存错误截图")
                await page.screenshot(path=os.path.join(debug_dir, f"error_{email_id}.png"))
                
        except Exception as e:
            logger.error(f"[尝试 {attempt + 1}] 处理失败: {e}")
            if attempt == max_attempts - 1:
                if 'page' in locals():
                    await page.screenshot(
                        path=os.path.join(debug_dir, f"error_{email_id}_{attempt}.png")
                    )
        finally:
            if context: await context.close()
            if browser: await browser.close()
            if 'p' in locals(): await p.stop()

        # 重试间隔
        if attempt < max_attempts - 1:
            retry_delay = (attempt + 1) * 5  # 递增等待时间
            logger.info(f"等待 {retry_delay} 秒后重试...")
            await asyncio.sleep(retry_delay)

    return "", None
