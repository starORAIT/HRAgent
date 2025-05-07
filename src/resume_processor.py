import logging
import json
from db_manager import Email, beijing_now

def create_candidate(session, email):
    """创建候选人记录"""
    from db_manager import Candidate
    try:
        candidate = Candidate(
            email_subject=email.subject,
            inbox_account=email.inbox_account,
            resume_file_url=email.attachment_url,
            resume_hash=email.resume_hash,
            resume_text=email.content_text,
            status="NEW"
        )
        session.add(candidate)
        session.flush()  # 获取ID但不提交
        return candidate
    except Exception as e:
        session.rollback()
        logging.error(f"创建候选人记录失败: {str(e)}")
        raise

def save_resume_analysis(session, candidate, parsed_info, analysis):
    """保存简历分析结果"""
    try:
        # 基础信息
        for key, value in parsed_info.items():
            if hasattr(candidate, key):
                setattr(candidate, key, value)
        
        # AI分析结果 - 使用新的字段名
        candidate.education_score = analysis.get("education_score", 0)
        candidate.education_detail = analysis.get("education_detail", "")
        candidate.technical_score = analysis.get("technical_score", 0)
        candidate.technical_detail = analysis.get("technical_detail", "")
        candidate.innovation_score = analysis.get("innovation_score", 0)
        candidate.innovation_detail = analysis.get("innovation_detail", "")
        candidate.growth_score = analysis.get("growth_score", 0)
        candidate.growth_detail = analysis.get("growth_detail", "")
        candidate.startup_score = analysis.get("startup_score", 0)
        candidate.startup_detail = analysis.get("startup_detail", "")
        candidate.teamwork_score = analysis.get("teamwork_score", 0)
        candidate.teamwork_detail = analysis.get("teamwork_detail", "")
        
        # 总体评估结果 - 使用新的字段名
        candidate.total_score = analysis.get("total_score", 0)
        candidate.is_qualified = analysis.get("is_qualified", False)
        candidate.focus_flag = analysis.get("focus_flag", False)
        candidate.risk = analysis.get("risk", "")
        candidate.questions = analysis.get("questions", "")
        
        session.commit()
        logging.info(f"已保存候选人 {candidate.name} 的分析结果，总分：{candidate.total_score}")
        
    except Exception as e:
        session.rollback()
        logging.error(f"保存分析结果失败: {str(e)}")
        raise

def process_single_email(email_dict, session, config, ai_screener, service):
    """处理单个邮件"""
    worker_id = "MainProcess"  # Default worker ID
    
    try:
        # 使用悲观锁获取邮件记录
        db_email = session.query(Email).filter(
            Email.id == email_dict['id'],
            Email.process_status.in_(["NEW", "FAILED"])
        ).with_for_update().first()
        
        if not db_email:
            logging.info(f"[Worker {worker_id}] 邮件 {email_dict['id']} 已被其他进程处理或状态已改变")
            return None

        # 更新处理状态为处理中
        db_email.process_status = "PROCESSING"
        db_email.update_time = beijing_now()
        session.commit()
        
        # 解析附件信息
        try:
            attachments_info = json.loads(db_email.attachments_info) if db_email.attachments_info else []
            attach_filenames = [att.get('name', '') for att in attachments_info if isinstance(att, dict)]
        except Exception as e:
            logging.warning(f"[Worker {worker_id}] 解析附件信息失败: {str(e)}")
            attach_filenames = []
        
        # 识别邮件类型和岗位
        try:
            is_resume, position, channel = ai_screener.identify_mail_type(
                subject=db_email.subject,
                resume_text=db_email.content_text,
                attach_filenames=attach_filenames,
                from_domain=db_email.from_address.split('@')[-1] if db_email.from_address else ""
            )
            if not is_resume:
                db_email.process_status = "SKIPPED"
                db_email.error_message = "非简历邮件"
                session.commit()
                return None

            if not position:
                db_email.process_status = "FAILED"
                db_email.error_message = "未能识别出匹配的岗位"
                session.commit()
                return None
                
        except Exception as e:
            db_email.process_status = "FAILED"
            db_email.error_message = f"邮件类型识别失败: {str(e)}"
            session.commit()
            return None

        # 简历分析
        try:
            parsed, analysis = ai_screener.screen_resume(db_email.content_text, position)
            if not parsed or not analysis:
                db_email.process_status = "FAILED"
                db_email.error_message = "AI分析返回空结果"
                session.commit()
                return None
                
            # 保存候选人信息
            candidate_id = service.store_candidate(
                session=session,
                parsed_info=parsed,
                analysis=analysis,
                resume_source=channel,
                resume_full_text=db_email.content_text,
                resume_hash=db_email.resume_hash,
                email_subject=str(db_email.subject),
                inbox_account=str(db_email.inbox_account),
                resume_file_url=str(db_email.attachment_url) if db_email.attachment_url else "",
                mail_sent_time=db_email.received_date
            )

            # 更新邮件状态
            db_email.process_status = "COMPLETED"
            db_email.candidate_id = candidate_id
            db_email.error_message = ""
            session.commit()
            
            return db_email.id
            
        except Exception as e:
            db_email.process_status = "FAILED"
            db_email.error_message = f"简历分析失败: {str(e)}"
            session.commit()
            return None
            
    except Exception as e:
        if 'db_email' in locals():
            db_email.process_status = "FAILED"
            db_email.error_message = str(e)
            session.commit()
        logging.error(f"[Worker {worker_id}] 处理邮件失败: {email_dict['id']}: {str(e)}")
        return None
