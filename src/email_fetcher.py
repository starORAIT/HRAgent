# email_fetcher.py
import logging
import datetime
import hashlib
from imapclient import IMAPClient
from email.utils import parseaddr, parsedate_to_datetime
from email import message_from_bytes
import concurrent.futures
import asyncio
import pytz
import time
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker  # 添加这行导入
import multiprocessing  # 添加 multiprocessing 模块导入
from db_manager import (
    Email,
    check_duplicate_email,
    get_processed_message_ids
)
from utils import (
    create_db_session,
    decode_subject,
    html_to_text,
    extract_clean_text,
    decode_attachment_filename,
    create_pdf_from_html_string,
    save_attachments_for_debug,
    truncate_text_field,
)
from utils.text_utils import extract_text_from_html  # 添加此行
from nowcoder.resume_fetcher import fetch_resume_from_link
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from utils.log_utils import setup_logger

CHINA_TZ = pytz.timezone("Asia/Shanghai")

class MailFetcher:
    def __init__(self, config):
        self.logger = setup_logger('MailFetcher')
        self.config = config
        if not config.EMAIL_ACCOUNTS or config.EMAIL_ACCOUNTS[0] == "":
            raise ValueError("[错误] EMAIL_ACCOUNTS 未配置.")
        self.accounts = self._parse_accounts(config.EMAIL_ACCOUNTS)
        self.oss_enabled = all([
            config.OSS_ACCESS_KEY_ID,
            config.OSS_ACCESS_KEY_SECRET,
            config.OSS_BUCKET_NAME,
            config.OSS_ENDPOINT
        ])
        self.current_batch_size = config.EMAIL_SAVE_BATCH_SIZE  # 从配置读取批次大小
        self.logger.debug(f"设置邮件处理批次大小: {self.current_batch_size}")

    def _parse_accounts(self, raw_list):
        """解析邮箱账户配置"""
        try:
            # 如果是字符串，按逗号分割成列表
            if isinstance(raw_list, str):
                raw_list = [x.strip() for x in raw_list.split(",") if x.strip()]
                
            res = []
            for item in raw_list:
                parts = item.strip().split(":")
                if len(parts) < 4:
                    self.logger.error(f"无效的邮箱配置: {item}, 格式应为 host:port:user:password")
                    continue
                host, port, user, pwd = parts[:4]
                try:
                    port = int(port)
                    self.logger.debug(f"成功加载邮箱账户: {user}")
                    res.append((host, port, user, pwd))
                except ValueError:
                    self.logger.error(f"邮箱端口号无效: {port}")
                    continue
            
            if not res:
                raise ValueError("没有有效的邮箱账户配置")
                
            self.logger.info(f"总计加载 {len(res)} 个邮箱账户")
            return res
            
        except Exception as e:
            self.logger.error(f"解析邮箱账户配置失败: {e}")
            raise

    def fetch_emails_from_all(self, is_first_run: bool = False):
        """使用线程池并行获取多个邮箱账户的邮件"""
        start_time = time.time()
        total_processed = 0

        # 使用线程池而不是进程池
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(self.accounts), self.config.FETCH_CONCURRENCY)
        ) as executor:
            # 创建每个账户的处理任务
            futures = []
            for host, port, user, pwd in self.accounts:
                future = executor.submit(
                    self._fetch_single_account_parallel,
                    host=host,
                    port=port,
                    user=user,
                    pwd=pwd,
                    batch_size=self.current_batch_size,
                    config_dict={k: v for k, v in self.config.__dict__.items() 
                               if not k.startswith('_') and not callable(v)}
                )
                futures.append((user, future))
            
            # 收集所有账户的处理结果
            for user, future in futures:
                try:
                    results = future.result(timeout=3600)  # 1小时超时
                    if results:
                        for batch in results:
                            if batch:
                                total_processed += len(batch)
                                yield batch
                                
                    # 显示每个邮箱的处理状态
                    elapsed = time.time() - start_time
                    speed = total_processed / elapsed if elapsed > 0 else 0
                    self.logger.info(f"邮箱账户 {user} 完成处理，总数={total_processed}, "
                               f"速度: {speed:.1f} 封/秒")
                    
                except Exception as e:
                    self.logger.error(f"处理邮箱账户 {user} 失败: {e}")
                    continue

        # 任务完成统计
        total_time = time.time() - start_time
        self.logger.info(f"所有邮箱处理完成，共处理 {total_processed} 封邮件，"
                    f"总耗时: {total_time:.1f}秒，"
                    f"平均速度: {total_processed/total_time:.1f} 封/秒")

    def _fetch_single_account_parallel(self, host, port, user, pwd, batch_size, config_dict):
        """并行处理单个邮箱账户的邮件"""
        logger = setup_logger(f'MailFetcher-{user}')
        processed_results = []
        
        try:
            # 重建配置对象
            from config import Config
            config = Config.__new__(Config)
            for k, v in config_dict.items():
                setattr(config, k, v)

            # 创建独立的数据库引擎
            if 'db_config' in config_dict:
                engine = create_engine(
                    config_dict['db_config']['engine_url'],
                    pool_pre_ping=True,
                    pool_recycle=config_dict['db_config']['pool_recycle'],
                    pool_size=config_dict['db_config']['pool_size'] // 4,
                    max_overflow=config_dict['db_config']['max_overflow'] // 4,
                    echo=False
                )
            else:
                engine = create_engine(
                    f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}",
                    pool_pre_ping=True,
                    pool_recycle=1800,
                    pool_size=5,
                    max_overflow=5,
                    echo=False
                )

            Session = sessionmaker(bind=engine)
            
            with Session() as session:
                # 1. 先获取已处理的邮件ID列表
                processed_ids = get_processed_message_ids(session, user)
                logger.info(f"账户 {user}: 已处理邮件 {len(processed_ids)} 封")
                
                with IMAPClient(host, use_uid=True, ssl=True) as client:
                    client.login(user, pwd)
                    client.select_folder("INBOX", readonly=False)
                    
                    # 获取日期范围
                    since_date = (datetime.date.today() - 
                              datetime.timedelta(days=config.EMAIL_FETCH_RANGE_DAYS if config.IS_FIRST_RUN else config.EMAIL_FETCH_RANGE_DAYS_ROLL))
                    criteria = ["SINCE", since_date.strftime("%d-%b-%Y")]
                    
                    # 搜索邮件
                    msg_ids = client.search(criteria)
                    if not msg_ids:
                        logger.info(f"账户 {user} 没有新邮件")
                        return []
                        
                    # 时间倒序排列并过滤已处理的
                    msg_ids = sorted(msg_ids, reverse=True)
                    if config.EMAIL_FETCH_LIMIT > 0:
                        msg_ids = msg_ids[:config.EMAIL_FETCH_LIMIT]
                        
                    # 2. 在这里就过滤掉已处理的邮件
                    new_msg_ids = [mid for mid in msg_ids if str(mid) not in processed_ids]
                    if not new_msg_ids:
                        logger.debug(f"账户 {user} 没有未处理的邮件")
                        return []
                        
                    logger.info(f"账户 {user} 发现 {len(new_msg_ids)} 封未处理邮件")

                    # 获取邮件数据
                    raw_messages = client.fetch(new_msg_ids, ["RFC822"])
                    logger.debug(f"获取到原始邮件数: {len(raw_messages)}")

                    # 使用线程池并行处理邮件，但每个线程使用独立的数据库会话
                    with ThreadPoolExecutor(max_workers=min(5, len(raw_messages))) as executor:
                        futures = []
                        for mid, data in raw_messages.items():
                            raw_msg = data[b"RFC822"]
                            future = executor.submit(
                                self._process_without_check,  # 修改为新的处理方法
                                mid=mid,
                                raw_msg=raw_msg,
                                user=user,
                                config=config,  # 修改：传递config而不是engine
                            )
                            futures.append((mid, future))

                        current_batch = []
                        processed = 0
                        failed = 0
                        
                        for mid, future in futures:
                            try:
                                result = future.result(timeout=300)  # 5分钟超时
                                if result:
                                    logger.debug(f"邮件 {mid} 处理成功")
                                    current_batch.append(result)
                                    processed += 1
                                    
                                    if len(current_batch) >= batch_size:
                                        logger.debug(f"保存批次: {len(current_batch)}封")
                                        self._save_batch_to_db(current_batch, session)
                                        processed_results.append(current_batch.copy())
                                        current_batch = []
                                else:
                                    logger.warning(f"[Fetch-6] 邮件 {mid} 处理返回空结果")
                                    failed += 1
                                    
                            except Exception as e:
                                logger.error(f"[Fetch-7] 处理邮件 {mid} 失败: {e}")
                                failed += 1

                        # 处理最后一个批次
                        if current_batch:
                            logger.debug(f"保存最后批次: {len(current_batch)}封")
                            self._save_batch_to_db(current_batch, session)
                            processed_results.append(current_batch.copy())

                        # 记录处理结果统计
                        logger.info(f"账户处理完成统计:\n"
                                  f"- 总数: {len(raw_messages)}封\n"
                                  f"- 成功: {processed}封\n"
                                  f"- 失败: {failed}封\n"
                                  f"- 成功率: {(processed/len(raw_messages)*100):.1f}%")
                        return processed_results

        except Exception as e:
            logger.error(f"处理邮箱 {user} 失败: {e}")
        return []

    def _process_without_check(self, mid, raw_msg, user, config):
        """处理邮件但不检查重复"""
        logger = setup_logger(f'MailProcessor-{mid}')
        session = None
        
        try:
            logger.debug(f"[Process-1] 开始处理邮件 {mid}")
            session = create_db_session(config)
            
            # 直接处理邮件，因为已经在外层过滤过了
            msg = message_from_bytes(raw_msg)
            if not msg:
                logger.warning(f"[Process-2] 邮件解析失败")
                return None
                    
            # 处理邮件
            logger.debug(f"[Process-3] 开始处理简历内容，主题: {msg.get('Subject', '')}")
            result = self.process_resume(
                mid=mid,
                msg=msg,
                from_addr=parseaddr(msg.get("From", ""))[1],
                mail_date=self._parse_date(msg.get("Date")),
                inbox_account=user
            )
            
            if result:
                logger.info(f"[Process-4] 处理成功: 简历类型={result.get('resume_type')}, "
                           f"文本长度={len(result.get('resume_text', ''))}")
            else:
                logger.warning("[Process-5] 处理返回空结果")
                
            return result
            
        except Exception as e:
            logger.error(f"[Process-6] 处理失败: {str(e)}", exc_info=True)
            return None
        finally:
            if session:
                session.close()

    def _process_single_mail(self, mid, raw_msg, user, session):
        """处理单封邮件"""
        logger = setup_logger(f'MailProcessor-{mid}')
        try:
            if not raw_msg or not isinstance(raw_msg, bytes):
                logger.warning(f"邮件 {mid} 数据无效")
                return None
                
            msg = message_from_bytes(raw_msg)
            if not msg:
                logger.warning(f"邮件 {mid} 解析失败")
                return None
                
            # 检查是否已经处理过
            if session.query(Email).filter_by(message_id=str(mid)).first():
                logger.info(f"邮件 {mid} 已存在，跳过处理")
                return None
                
            result = self.process_resume(
                mid=mid,
                msg=msg,
                from_addr=parseaddr(msg.get("From", ""))[1],
                mail_date=self._parse_date(msg.get("Date")),
                inbox_account=user
            )
            
            return result
            
        except Exception as e:
            logger.error(f"处理邮件 {mid} 失败: {e}")
            return None

    def _parse_date(self, date_str):
        """安全解析邮件日期"""
        if not date_str:
            return None
            
        try:
            from email.utils import parsedate_tz, mktime_tz
            parsed_date = parsedate_tz(date_str)
            if parsed_date:
                timestamp = mktime_tz(parsed_date)
                return datetime.datetime.fromtimestamp(timestamp, CHINA_TZ)
        except Exception as e:
            self.logger.warning(f"解析邮件日期失败: {date_str}, error: {e}")
        return None

    def _process_msg_chunk(self, mail_data, user):
        """处理一块邮件数据"""
        results = []
        
        if not mail_data:
            return results
            
        for mid, raw_msg in mail_data.items():
            try:
                if not raw_msg:
                    self.logger.warning(f"邮件 {mid} 内容为空")
                    continue
                    
                msg = message_from_bytes(raw_msg)
                if not msg:
                    self.logger.warning(f"邮件 {mid} 解析失败")
                    continue
                    
                # 安全地解析日期
                mail_date = None
                date_str = msg.get("Date")
                if date_str:
                    try:
                        from email.utils import parsedate_tz, mktime_tz
                        parsed_date = parsedate_tz(date_str)
                        if parsed_date:
                            timestamp = mktime_tz(parsed_date)
                            mail_date = datetime.datetime.fromtimestamp(timestamp, CHINA_TZ)
                    except Exception as e:
                        self.logger.warning(f"解析邮件日期失败: {date_str}, error: {e}")
                        mail_date = None
                    
                result = self.process_resume(
                    mid=mid,
                    msg=msg,
                    from_addr=parseaddr(msg.get("From", ""))[1],
                    mail_date=mail_date,
                    inbox_account=user
                )
                
                if result and isinstance(result, dict):
                    results.append(result)
                    
            except Exception as e:
                self.logger.error(f"处理单封邮件失败 {mid}: {e}", exc_info=True)
                continue
                
        return results

    def _save_batch_to_db(self, batch, session):
        """将一批邮件保存到数据库"""
        try:
            if not batch:
                self.logger.info("没有需要保存的邮件")
                return
                
            # 开启事务
            emails_to_save = []
            saved_count = 0
            
            for mail in batch:
                try:
                    email = Email()
                    # 更新邮件数据
                    email.message_id = mail.get("mail_id")
                    email.subject = mail.get("subject")
                    email.from_address = mail.get("from_addr")
                    email.content_text = truncate_text_field(mail.get("resume_text", ""), 65000)
                    email.content_html = truncate_text_field(mail.get("html_body", ""), 16700000)
                    email.attachments_info = json.dumps([
                        {"name": fname, "size": len(fdata)}
                        for fname, fdata in mail.get("attachments", [])
                    ])
                    email.received_date = mail.get("mail_date")
                    email.resume_hash = mail.get("resume_hash", "")
                    email.attachment_url = mail.get("attachment_url", "")
                    email.inbox_account = mail.get("inbox_account", "")
                    email.process_status = "NEW"

                    emails_to_save.append(email)
                    saved_count += 1
                        
                except Exception as e:
                    self.logger.error(f"处理单封邮件失败: {e}")
                    continue

            if emails_to_save:
                session.bulk_save_objects(emails_to_save)
                session.commit()
                self.logger.info(f"批次处理完成 - 成功保存: {saved_count} 封邮件")
                            
        except Exception as e:
            self.logger.error(f"保存批次到数据库失败: {e}")
            session.rollback()
            raise

    def process_resume(self, mid, msg, from_addr, mail_date, inbox_account):
        """处理简历邮件，返回结果字典"""
        logger = setup_logger(f'MailProcessor-{mid}')
        try:
            logger.debug(f"开始处理邮件 ID: {mid}")
            subj = decode_subject(msg.get("Subject", ""))
            body, html_content, attachments = self._extract_parts(msg)
            
            logger.debug(f"邮件内容状态: body={bool(body)}, "
                       f"html_content={bool(html_content)}, "
                       f"attachments={len(attachments)}")
            
            # 如果邮件内容完全为空则返回None
            if not any([body, html_content, attachments]):
                self.logger.warning(f"邮件内容为空: mid={mid}, subject={subj}")
                return None
                
            text_content = body.strip() + "\n" + html_content.strip()
            
            # 判断简历类型
            resume_type = "text"  # 默认为正文型
            if attachments and any(f.lower().endswith(('.pdf', '.doc', '.docx')) for f, _ in attachments):
                resume_type = "attachment"  # 附件型
            elif ("牛客优聘" in subj) or ("nowcoder.com" in from_addr.lower()):
                resume_type = "hyperlink"  # 超链接型
            
            logger.info(f"邮件 ID: {mid} 识别为 {resume_type} 类型")
            
            resume_text = ""
            final_attachments = []
            attachment_url = None  # 初始化attachment_url
            
            try:
                if resume_type == "attachment":
                    # 1. 附件型简历处理
                    logger.info(f"邮件 id: {mid} 检测到附件型简历")
                    for fname, fdata in attachments:
                        try:
                            # 处理图片类型附件
                            if fname.lower().endswith(('.png', '.jpg', '.jpeg')):
                                logger.info(f"处理图片附件: {fname}")
                                from utils.image_utils import extract_text_from_image
                                image_text = extract_text_from_image(fdata)
                                if image_text.strip():
                                    resume_text = image_text
                                    final_attachments = [(fname, fdata)]
                                    break
                            # 处理PDF和Word文件
                            elif fname.lower().endswith(('.pdf', '.docx', '.doc')):
                                final_attachments = [(fname, fdata)]
                                if fname.lower().endswith(".pdf"):
                                    from resume_parser import parse_pdf
                                    resume_text = parse_pdf(fdata)
                                elif fname.lower().endswith(".docx"):
                                    from resume_parser import parse_docx
                                    resume_text = parse_docx(fdata)
                                if resume_text.strip():
                                    break
                        except Exception as e:
                            self.logger.error(f"解析附件 {fname} 失败: {e}")
                            
                elif resume_type == "hyperlink":
                    logger.info(f"[邮件{mid}] 开始处理超链接型简历")
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            logger.debug(f"[邮件{mid}] 调用fetch_resume_from_link")
                            result = loop.run_until_complete(fetch_resume_from_link(html_content, email_id=mid))
                            logger.debug(f"[邮件{mid}] fetch_resume_from_link返回结果类型: {type(result)}")
                        finally:
                            loop.close()
                    except Exception as e:
                        self.logger.error(f"[邮件{mid}] 调用fetch_resume_from_link异常: {e}", exc_info=True)
                        result = None

                    logger.debug(f"[邮件{mid}] 检查result类型: {type(result)}")
                    if result is None:
                        self.logger.warning(f"[邮件{mid}] result为None")
                    elif not isinstance(result, tuple):
                        self.logger.warning(f"[邮件{mid}] result不是元组: {type(result)}")
                    elif len(result) != 2:
                        self.logger.warning(f"[邮件{mid}] result元组长度不为2: {len(result)}")

                    # 仅进行一次解包检查
                    if (result is None or not isinstance(result, tuple) or len(result) != 2):
                        self.logger.warning(f"[邮件{mid}] fetch_resume_from_link返回无效，使用fallback")
                        resume_text, attachment = "", None
                    else:
                        logger.debug(f"[邮件{mid}] 成功解析返回值")
                        resume_text, attachment = result

                    if attachment:
                        final_attachments = [attachment]

                    if not resume_text or not resume_text.strip():
                        logger.debug("链接简历获取失败，尝试从HTML内容提取...")
                        resume_text = html_to_text(html_content)

                    if not resume_text or not resume_text.strip():
                        logger.debug("尝试从预览窗格中提取图片...")
                        from utils.image_utils import extract_images_from_html, extract_text_from_image
                        images = extract_images_from_html(html_content)
                        for img_data in images:
                            try:
                                img_text = extract_text_from_image(img_data)
                                if (img_text and img_text.strip()):
                                    resume_text = img_text
                                    break
                            except Exception as e:
                                self.logger.error(f"处理图片失败: {e}")
                                continue
                                
                        # 如果还是没有内容，尝试网页截图
                        if not resume_text or not resume_text.strip():
                            logger.debug("尝试网页截图...")
                            from utils.image_utils import capture_webpage_and_extract_text
                            resume_text = capture_webpage_and_extract_text(html_content)
                            if resume_text and resume_text.strip():
                                screenshot_name = f"screenshot_{mid}.png"
                                final_attachments = [(screenshot_name, capture_webpage_and_extract_text.get_last_image())]
                            
                elif resume_type == "text":
                    # 3. 正文型简历处理
                    logger.debug(f"[Step 3] 正文型简历处理开始 - 邮件ID: {mid}")
                    
                    # 先尝试从HTML提取文本，如果失败则使用原始body
                    resume_text = extract_text_from_html(html_content)
                    logger.debug(f"从HTML提取文本长度: {len(resume_text)}")
                    
                    if not resume_text.strip():
                        resume_text = body
                        logger.debug(f"使用原始body文本，长度: {len(resume_text)}")
                        
                    # 确保resume_text不为空
                    if not resume_text.strip():
                        self.logger.warning("无法提取到有效文本内容")
                        return None
                        
                    logger.debug(f"[Step 4] 最终文本长度: {len(resume_text)}")
                    logger.debug(f"[Step 4.1] 文本前100个字符: {resume_text[:100]}")
                
                    try:
                        pdf_result = create_pdf_from_html_string(resume_text, f"text_{mid}")
                        logger.debug(f"[Step 5] PDF创建返回值: {pdf_result}")
                        
                        # 详细检查pdf_result
                        if pdf_result is None:
                            self.logger.error("[Step 5.1] PDF创建返回了None")
                            pdf_fname, pdf_data = "", None
                        elif not isinstance(pdf_result, tuple):
                            self.logger.error(f"[Step 5.2] PDF创建返回了非元组类型: {type(pdf_result)}")
                            pdf_fname, pdf_data = "", None
                        elif len(pdf_result) != 2:
                            self.logger.error(f"[Step 5.3] PDF创建返回了长度不为2的元组: {len(pdf_result)}")
                            pdf_fname, pdf_data = "", None
                        else:
                            logger.debug("[Step 5.4] PDF创建成功")
                            pdf_fname, pdf_data = pdf_result
                            
                        # 记录PDF结果状态
                        logger.debug(f"[Step 6] PDF处理结果: fname={pdf_fname}, "
                                  f"data_size={len(pdf_data) if pdf_data else 0}")
                        
                        final_attachments = [(pdf_fname, pdf_data)] if pdf_data else []
                        
                    except Exception as e:
                        self.logger.error(f"[Step 7] 创建PDF失败: {e}", exc_info=True)
                        final_attachments = []

                    # 记录最终结果状态
                    logger.debug(f"[Step 8] 最终附件数量: {len(final_attachments)}")
                
                # 只在最后阶段清理resume_text
                clean_resume_text = extract_clean_text(resume_text)
                if (clean_resume_text.strip()):
                    # 总是计算resume_hash
                    resume_hash = hashlib.md5(clean_resume_text.encode('utf-8')).hexdigest()
                    logger.debug(f"计算 resume_hash: {resume_hash[:8]}... for mail_id: {mid}")

                    # 保存附件到download目录用于debug
                    if final_attachments:
                        attachment_url = None
                        if self.oss_enabled:
                            # Upload the first attachment to OSS
                            fname, fdata = final_attachments[0]
                            try:
                                from utils import upload_to_oss
                                from datetime import datetime
                                current_month = datetime.now(pytz.UTC).strftime('%Y%m')  # Fix: use datetime.now(UTC)
                                attachment_url = upload_to_oss(
                                    fname, 
                                    fdata, 
                                    self.config,
                                    prefix=f"resumes/{current_month}"
                                )
                                logger.info(f"简历已上传到OSS: {attachment_url}")
                            except Exception as e:
                                self.logger.error(f"上传简历到OSS失败: {e}")

                    # Save debug copy if needed
                    save_attachments_for_debug(final_attachments, mid)
                        
                    result_dict = {
                        "subject": subj,
                        "from_addr": from_addr,
                        "body": body,
                        "html_body": html_content,
                        "attachments": final_attachments,
                        "resume_text": clean_resume_text,  # 使用清理后的文本
                        "mail_date": mail_date,
                        "raw_msg": msg.as_bytes(),
                        "mail_id": mid,
                        "resume_type": resume_type,
                        "resume_hash": resume_hash,  # Always include resume_hash
                        "attachment_url": attachment_url,
                        "inbox_account": inbox_account
                    }
                    logger.debug(f"[Final] 成功创建结果字典: {result_dict.keys()}")
                    return result_dict
                else:
                    self.logger.warning(f"[Final] 简历文本为空，返回None")
                    return None
                
            except Exception as e:
                self.logger.error(f"处理简历失败: {e}")
            
            return None
        except Exception as e:
            self.logger.error(f"处理简历失败: {e}")
        
        return None

    def _fetch_single_account(self, host, port, user, pwd, is_first_run):
        """处理单个邮箱账户"""
        results = []
        self.logger.info(f"开始处理邮箱账户：{user}")
        since_date = (datetime.date.today() - 
                              datetime.timedelta(days=self.config.EMAIL_FETCH_RANGE_DAYS if self.config.IS_FIRST_RUN else self.config.EMAIL_FETCH_RANGE_DAYS_ROLL))               
        since_str = since_date.strftime("%d-%b-%Y")
        criteria = ["SINCE", since_str]  # 只根据发件日期筛选邮件
        try:
            with IMAPClient(host, use_uid=True, ssl=True) as client:
                client.login(user, pwd)
                client.select_folder("INBOX", readonly=False)
                msg_ids = client.search(criteria)
                
                # 如果设置了邮件数量限制，则按时间倒序排列并只取最近的N封
                if self.config.EMAIL_FETCH_LIMIT > 0:
                    msg_ids = sorted(msg_ids, reverse=True)[:self.config.EMAIL_FETCH_LIMIT]
                    self.logger.info(f"[MailFetcher] user={user}, 限制处理最新的 {self.config.EMAIL_FETCH_LIMIT} 封邮件")
                
                self.logger.info(f"[MailFetcher] user={user}, 待处理邮件数: {len(msg_ids)}")
                if not msg_ids:
                    return results
                    
                fetch_data = self._fetch_in_chunks(client, msg_ids)
                for mid, raw_msg in fetch_data:
                    if not raw_msg:
                        continue
                    msg = message_from_bytes(raw_msg)
                    from_str = msg.get("From", "")
                    _, from_addr = parseaddr(from_str)
                    date_str = msg.get("Date")
                    mail_date = None
                    if date_str:
                        try:
                            mail_date = parsedate_to_datetime(date_str).astimezone(CHINA_TZ)
                        except Exception:
                            pass
                            
                    result = self.process_resume(mid, msg, from_addr, mail_date, user)  # Pass inbox account
                    if result:
                        results.append(result)
                        self.logger.info(f"完成处理邮件 id: {mid}, 主题: {result['subject']}, "
                                   f"简历类型: {result['resume_type']}, "
                                   f"简历文本长度: {len(result['resume_text'])}")
        except Exception as e:
            self.logger.error(f"抓取邮箱 {user} 时出错: {e}")
        return results

    def _fetch_in_chunks(self, client, msg_ids):
        """分块获取邮件数据"""
        chunk_size = self.config.FETCH_CHUNK_SIZE
        results = []
        for i in range(0, len(msg_ids), chunk_size):
            chunk = msg_ids[i:i+chunk_size]
            try:
                data = client.fetch(chunk, "RFC822")
                for mid, d in data.items():
                    results.append((mid, d.get(b"RFC822")))
            except Exception as e:
                self.logger.error(f"抓取块时出错: {e}")
        return results

    def _extract_parts(self, msg):
        """提取邮件各部分内容"""
        logger = setup_logger('MailExtractor')
        body = ""
        html_body = ""
        attachments = []
        
        try:
            if not msg:
                logger.warning("邮件对象为空")
                return body, html_body, attachments
                
            # 记录原始内容类型
            content_type = msg.get_content_type()
            logger.debug(f"邮件主体内容类型: {content_type}")
                
            for part in msg.walk():
                try:
                    part_type = part.get_content_type()
                    logger.debug(f"处理邮件部分: {part_type}")
                    
                    # 如果是附件
                    if part.get_filename():
                        fname = decode_attachment_filename(part.get_filename())
                        if fname:
                            try:
                                payload = part.get_payload(decode=True)
                                if payload:
                                    attachments.append((fname, payload))
                                    logger.debug(f"提取到附件: {fname}, {len(payload)}字节")
                            except Exception as e:
                                logger.error(f"处理附件失败: {fname}, {e}")
                        continue
                    
                    # 处理正文
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue
                    
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        text = payload.decode(charset, errors='replace')
                        
                        if part_type == 'text/plain':
                            body += text + "\n"
                        elif part_type == 'text/html':
                            html_body += text + "\n"
                            
                    except Exception as e:
                        logger.error(f"解码文本失败: {e}")
                        
                except Exception as e:
                    logger.error(f"处理邮件部分失败: {e}")
                    continue
                    
            # 确保至少有一种文本内容
            if not body.strip() and not html_body.strip():
                logger.warning("未能提取到任何文本内容")
            else:
                logger.info(f"提取结果: plain={len(body)}字节, html={len(html_body)}字节")
                
            return body.strip(), html_body.strip(), attachments
            
        except Exception as e:
            logger.error(f"提取邮件内容失败: {e}", exc_info=True)
            return "", "", []
