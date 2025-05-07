import logging
import asyncio
import hashlib  # 添加 hashlib 导入
from typing import Dict, Optional, Tuple, List
from email_fetcher import fetch_resume_from_link
from resume_parser import parse_pdf, parse_docx

class MailProcessor:
    def __init__(self, config):
        self.config = config

    def calculate_mail_hash(self, mail: dict) -> str:
        """计算邮件哈希值，主要基于简历文本内容"""
        # 使用简历文本内容作为主要哈希源
        resume_text = mail.get("resume_text", "").strip()
        if not resume_text:
            return ""
            
        hash_content = resume_text.encode('utf-8')
        return hashlib.md5(hash_content).hexdigest()

    async def process_mail(self, mail: dict, position: str, channel: str) -> Optional[Dict]:
        """处理单封邮件，返回处理结果"""
        try:
            mail_hash = self.calculate_mail_hash(mail)
            from_domain = mail.get("from_addr", "").split("@")[-1]
            
            # 确定简历处理类型
            resume_type = self._determine_resume_type(mail, from_domain)
            
            result = await self._process_by_type(
                resume_type, 
                mail, 
                position, 
                channel, 
                mail_hash
            )
            
            if result:
                logging.info(f"Successfully processed mail: {mail.get('subject')} [{resume_type}]")
                return result
            
        except Exception as e:
            logging.error(f"Failed to process mail: {e}, subject: {mail.get('subject')}")
            
        return None

    def _determine_resume_type(self, mail: dict, from_domain: str) -> str:
        """确定简历类型"""
        # 首先检查配置的处理类型
        if from_domain in self.config.RESUME_PROCESSING_TYPES:
            return self.config.RESUME_PROCESSING_TYPES[from_domain]
            
        # 然后检查附件
        if mail.get("attachments"):
            for fname, _ in mail.get("attachments"):
                if fname.lower().endswith(('.pdf', '.doc', '.docx')):
                    return "attachment"
                    
        # 最后默认为文本类型
        return "text"

    async def _process_by_type(self, 
                             resume_type: str, 
                             mail: dict, 
                             position: str, 
                             channel: str,
                             mail_hash: str) -> Optional[Dict]:
        """根据不同类型处理简历"""
        if resume_type == "hyperlink":
            return await self._process_hyperlink_resume(mail, position, channel, mail_hash)
        elif resume_type == "attachment":
            return self._process_attachment_resume(mail, position, channel, mail_hash)
        else:  # text type
            return self._process_text_resume(mail, position, channel, mail_hash)

    async def _process_hyperlink_resume(self, mail: dict, position: str, 
                                      channel: str, mail_hash: str) -> Optional[Dict]:
        """处理超链接类型简历"""
        txt, attachment = await fetch_resume_from_link(
            mail.get("html_body", ""),
            mail.get("mail_id")
        )
        
        if not txt.strip():
            return None
            
        return {
            "subject": mail.get("subject", ""),
            "from_addr": mail.get("from_addr", ""),
            "mail_date": mail.get("mail_date"),
            "position": position,
            "channel": channel,
            "resume_text": txt,
            "attachment_name": attachment[0] if attachment else None,
            "attachment_data": attachment[1] if attachment else None,
            "resume_hash": mail_hash,
            "original_email_url": mail.get("original_email_url", "")
        }

    def _process_attachment_resume(self, mail: dict, position: str,
                                 channel: str, mail_hash: str) -> Optional[Dict]:
        """处理附件类型简历"""
        for fname, fdata in mail.get("attachments", []):
            try:
                txt = None
                if fname.lower().endswith(".pdf"):
                    txt = parse_pdf(fdata)
                elif fname.lower().endswith(".docx"):
                    txt = parse_docx(fdata)
                
                if txt and txt.strip():
                    return {
                        "subject": mail.get("subject", ""),
                        "from_addr": mail.get("from_addr", ""),
                        "mail_date": mail.get("mail_date"),
                        "position": position,
                        "channel": channel,
                        "resume_text": txt,
                        "attachment_name": fname,
                        "attachment_data": fdata,
                        "resume_hash": mail_hash,
                        "original_email_url": mail.get("original_email_url", "")
                    }
            except Exception as e:
                logging.error(f"Failed to process attachment {fname}: {e}")
                
        return None

    def _process_text_resume(self, mail: dict, position: str,
                           channel: str, mail_hash: str) -> Optional[Dict]:
        """处理文本类型简历"""
        txt = mail.get("body", "").strip()
        if not txt and mail.get("html_body"):
            txt = mail.get("html_body", "")
            
        if not txt.strip():
            return None
            
        return {
            "subject": mail.get("subject", ""),
            "from_addr": mail.get("from_addr", ""),
            "mail_date": mail.get("mail_date"),
            "position": position,
            "channel": channel,
            "resume_text": txt,
            "attachment_name": None,
            "attachment_data": None,
            "resume_hash": mail_hash,
            "original_email_url": mail.get("original_email_url", "")
        }
