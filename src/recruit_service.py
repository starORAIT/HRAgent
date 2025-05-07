import json
import re
import logging
from resume_parser import md5_hash, compact_resume_text
from db_manager import Candidate, beijing_now

class RecruitService:
    def __init__(self, config, session=None):
        """初始化招聘服务"""
        self.config = config
        self.session = session
        if not session:
            from utils import create_db_session
            self.session = create_db_session(config)

    def store_candidate(self, session, parsed_info, analysis, resume_source="", 
                       resume_full_text="", resume_hash="", email_subject="",
                       inbox_account="", resume_file_url="", mail_sent_time=None):
        """存储候选人信息"""
        try:
            # 计算总分
            total_score = sum([
                analysis.get('education_score', 0),
                analysis.get('technical_score', 0),
                analysis.get('innovation_score', 0),
                analysis.get('growth_score', 0),
                analysis.get('startup_score', 0),
                analysis.get('teamwork_score', 0)
            ])
            
            # 设置是否合格(总分大于60分为合格)
            is_qualified = 1 if total_score >= 60 else 0
            
            # Convert boolean values to integers for MySQL compatibility
            focus_flag = int(analysis.get('focus_flag', False))
            
            # 检查是否存在重复简历
            if resume_hash:
                existing = session.query(Candidate).filter_by(resume_hash=resume_hash).first()
                if existing:
                    logging.info(f"发现重复简历，ID={existing.id}，将用新数据覆盖")
                    session.delete(existing)
                    session.flush()
            
            # 创建新的候选人记录
            candidate = Candidate(
                # 基本信息
                name=parsed_info.get('name', ''),
                apply_position=parsed_info.get('position', ''),
                phone=parsed_info.get('phone', ''),
                email=parsed_info.get('email', ''),
                wechat=parsed_info.get('wechat', ''),
                latest_company=parsed_info.get('latest_company', ''),
                work_experience=parsed_info.get('experience', ''),
                highest_education=parsed_info.get('highest_education', ''),
                highest_university=parsed_info.get('highest_university', ''),
                first_education=parsed_info.get('first_education', ''),
                first_university=parsed_info.get('first_university', ''),
                marital_status=parsed_info.get('marital_status', ''),
                age=parsed_info.get('age', 0),
                gender=parsed_info.get('gender', ''),
                expected_salary=parsed_info.get('expected_salary', ''),
                
                # 来源信息
                resume_source=resume_source,
                resume_text=resume_full_text,
                resume_hash=resume_hash,
                email_subject=email_subject,
                inbox_account=inbox_account,
                resume_file_url=resume_file_url,
                mail_sent_time=mail_sent_time,
                
                # AI分析结果
                total_score=total_score,
                education_score=analysis.get('education_score', 0),
                education_detail=analysis.get('education_detail', ''),
                technical_score=analysis.get('technical_score', 0),
                technical_detail=analysis.get('technical_detail', ''),
                innovation_score=analysis.get('innovation_score', 0),
                innovation_detail=analysis.get('innovation_detail', ''),
                growth_score=analysis.get('growth_score', 0),
                growth_detail=analysis.get('growth_detail', ''),
                startup_score=analysis.get('startup_score', 0),
                startup_detail=analysis.get('startup_detail', ''),
                teamwork_score=analysis.get('teamwork_score', 0),
                teamwork_detail=analysis.get('teamwork_detail', ''),
                
                # 其他评估结果
                is_qualified=is_qualified,
                focus_flag=focus_flag,
                risk=analysis.get('risk', ''),
                questions=analysis.get('questions', ''),
                
                # 状态信息
                status="NEW",
                create_time=beijing_now(),
                update_time=beijing_now()
            )
            
            session.add(candidate)
            session.flush()
            
            logging.info(f"成功创建候选人记录:\n"
                        f"ID: {candidate.id}\n"
                        f"姓名: {candidate.name}\n"
                        f"职位: {candidate.apply_position}\n"
                        f"总分: {total_score}\n"
                        f"是否合格: {'是' if is_qualified else '否'}")
            
            return candidate.id
            
        except Exception as e:
            session.rollback()
            logging.error(f"保存候选人信息失败: {str(e)}")
            raise

    def upload_to_oss(self, filename: str, filedata: bytes) -> str:
        """上传文件到OSS并返回URL"""
        try:
            import oss2
            from datetime import datetime
            
            auth = oss2.Auth(
                self.config.OSS_ACCESS_KEY_ID,
                self.config.OSS_ACCESS_KEY_SECRET
            )
            bucket = oss2.Bucket(
                auth,
                self.config.OSS_ENDPOINT,
                self.config.OSS_BUCKET_NAME
            )
            
            current_date = datetime.now().strftime('%Y%m')
            safe_filename = filename.replace(' ', '_')
            oss_path = f"resumes/{current_date}/{safe_filename}"
            
            result = bucket.put_object(oss_path, filedata)
            if result.status == 200:
                if self.config.OSS_CUSTOM_DOMAIN:
                    url = f"https://{self.config.OSS_CUSTOM_DOMAIN}/{oss_path}"
                else:
                    url = f"https://{self.config.OSS_BUCKET_NAME}.{self.config.OSS_ENDPOINT}/{oss_path}"
                logging.info(f"文件已上传到OSS: {url}")
                return url
                
        except Exception as e:
            logging.error(f"上传文件到OSS失败: {str(e)}")
        return ""
