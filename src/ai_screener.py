# ai_screener.py
import json
import re
import openai
import logging
import time
from datetime import datetime
from resume_parser import compact_resume_text, md5_hash

"""
AI简历筛选模块

本模块负责简历的AI分析，包括：
1. 识别邮件是否为简历
2. 匹配应聘岗位和来源渠道
3. 分析简历内容，评估候选人各方面能力
4. 生成面试问题建议
"""

def log_prompt(name: str, prompt: str, messages: list = None):
    """记录 prompt 到日志"""
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'prompt_name': name,
        'prompt_text': prompt
    }
    if messages:
        log_data['messages'] = messages
    logging.debug(f"AI Prompt: {json.dumps(log_data, ensure_ascii=False, indent=2)}")

class AIScreener:
    def __init__(self, config, job_info: dict, company_info: str):
        self.config = config
        self.job_info = job_info
        self.company_info = company_info
        openai.api_key = self.config.OPENAI_API_KEY
        # Embedding cache可选
        self.embedding_cache = None
        if self.config.CACHE_EMBEDDINGS:
            from utils import EmbeddingCache
            self.embedding_cache = EmbeddingCache(self.config.embedding_cache_file)

    def identify_mail_type(self, subject: str, resume_text: str, attach_filenames: list, from_domain: str):
        """
        判断邮件类型并识别岗位和来源
        
        Args:
            subject: 邮件主题
            resume_text: 邮件正文文本
            attach_filenames: 附件文件名列表
            from_domain: 发件人域名
            
        Returns:
            tuple: (是否为简历, 匹配的岗位名称, 简历来源渠道)
        """
        prompt = self.identify_mail_type_get_prompt(subject, resume_text, attach_filenames, from_domain)
        # 记录prompt到日志
        log_prompt("identify_mail_type", prompt)
        return self.identify_mail_type_execute(prompt)

    def identify_mail_type_get_prompt(self, subject: str, resume_text: str, attach_filenames: list, from_domain: str):
        """生成邮件类型判断prompt"""
        attach_names = ", ".join(attach_filenames)
        job_keys = list(self.job_info.keys())
        channels = list(self.config.RESUME_CHANNELS.keys())
        
        prompt = f"""
你是专业HR助手。请判断下列邮件信息是否为候选人简历：

邮件信息:
- 主题: {subject}
- 简历内容: {truncate_text(resume_text, 1000, self.config.MODEL_NAME)}
- 附件文件名: {attach_names}
- 发件人域名: {from_domain}

公司岗位列表（必须严格从以下列表中选择）: 
{json.dumps(job_keys, ensure_ascii=False, indent=2)}

可选渠道列表: {channels}

请判断：
1. 这是否为应聘简历邮件？
2. 如果是简历，应聘的是哪个岗位？（必须严格从公司岗位列表中选择最匹配的岗位，不允许使用列表外的岗位名称）
3. 简历来自哪个渠道？（从渠道列表中选择）

请以JSON格式输出,不要带任何多余解释或代码块：
{{
  "is_resume": false,
  "matched_position": "",  # 必须完全匹配公司岗位列表中的某个岗位名称
  "matched_channel": ""
}}
"""
        return prompt

    def identify_mail_type_execute(self, prompt: str):
        """执行邮件类型判断prompt"""
        try:
            response = call_openai_with_retry(
                openai.ChatCompletion.create,
                self.config,
                model=self.config.MODEL_NAME,
                messages=[
                    {"role": "system", "content": "你是专业的HR招聘助理。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=500
            )
            txt = response["choices"][0]["message"]["content"].strip()
            try:
                # Clean up JSON text
                if txt.startswith("```"):
                    txt = txt.split("\n", 1)[1]
                if txt.endswith("```"):
                    txt = txt.rsplit("\n", 1)[0]
                result = json.loads(txt)
                return result.get("is_resume", False), result.get("matched_position", ""), result.get("matched_channel", "")
            except (json.JSONDecodeError, AttributeError) as e:
                logging.error(f"identify_mail_type JSON解析失败: {e}, raw_txt={txt}")
                return False, "", ""
        except Exception as e:
            logging.error(f"identify_mail_type失败: {e}")
            return False, "", ""

    def screen_resume(self, resume_text: str, position_name: str):
        """
        分析简历内容，评估候选人能力
        
        Args:
            resume_text: 简历文本内容
            position_name: 应聘岗位名称
            
        Returns:
            tuple: (候选人基本信息字典, 评估结果字典)
        """
        prompt = self.screen_resume_get_prompt(resume_text, position_name)
        # 记录prompt到日志
        log_prompt("screen_resume", prompt)
        return self.screen_resume_execute(prompt)

    def screen_resume_get_prompt(self, resume_text: str, position_name: str):
        """生成简历分析prompt"""
        detail = self.job_info.get(position_name, {})
        prompt = f"""
你是一位拥有10年以上招聘经验的资深HR专家，专注于人工智能公司的技术人才评估。作为创业型AI技术公司，我们特别重视以下能力和背景：
1. 技术创新能力和学习速度
2. 在快速迭代环境中的适应能力
3. 对AI技术的理解和热情
4. 创业精神和主人翁意识
5. 跨团队协作能力
6. 优质教育背景（特别是985、211或国际知名高校）

请基于以下信息，对候选人进行全方位、专业的评估：

【岗位信息】
岗位名称: {position_name}
工作职责: {detail.get("duties", "")}
任职要求: {detail.get("requirements", "")}
学历要求: {detail.get("education_req", "")}
经验要求: {detail.get("exp_req", "")}
绩效目标: {detail.get("perf_goals", "")}

【公司背景】
{self.company_info}

【教育背景评估标准】
按照第一学历和学校评估：
1. 最高级（15分）：清华、北大、Top30国际名校
2. 较高级（12分）：其他985高校、Top50国际名校
3. 中等级（10分）：211高校、知名外国大学
4. 基本级（5分）：一般本科院校
5. 其他（0分）：大专及其他院校，本科非统招视为专科

最高学历加分（在第一学历基础上）：
- 国内外顶尖院校相关专业硕博：+5分
- 985高校相关专业硕博：+4分
- 211高校相关专业硕博：+3分
- 其他院校相关专业硕博：+0分

【候选人简历】
{truncate_text(resume_text, self.config.MAX_TOKEN, self.config.MODEL_NAME)}

请根据以上信息，对候选人进行专业评估，只返回JSON格式数据，不要带任何多余解释或代码块,如无数据返回为空。

输出JSON格式示例:
{{
  "parsed_info": {{
    "name": "候选人姓名",
    "position": "应聘职位（必须匹配岗位要求中的职位名称）",
    "experience": "工作年限",
    "latest_company": "最近就职公司",
    "first_education": "第一学历",
    "first_university": "第一学历院校",
    "highest_education": "最高学历",
    "highest_university": "最高学历院校",
    "marital_status": "婚姻状况",
    "age": 0-30,
    "gender": "性别", 
    "phone": "联系电话",
    "email": "电子邮箱",
    "wechat": "微信号",
    "expected_salary": "期望薪资",
    "resume_source": "简历来源"
  }},
  "analysis": {{
    "education_score": 0,
    "education_detail": "教育背景评价（第一学历、学校层次、专业匹配度等）",
    "technical_score": 0,
    "technical_detail": "技术实力评价（技术栈匹配度、项目经验深度、算法能力等）",
    "innovation_score": 0,
    "innovation_detail": "创新潜力评价（高水平论文专利、学习能力、技术视野等）",
    "growth_score": 0,
    "growth_detail": "成长速度评价（履历提升、自我驱动力、知识更新速度等）",
    "startup_score": 0,
    "startup_detail": "创业特质评价（创业经历、主动性、抗压能力等）",
    "teamwork_score": 0,
    "teamwork_detail": "团队协作评价（团队领导经历、沟通能力、跨部门协作等）",
    "risk": "风险提示（教育风险、技术风险、稳定性风险、团队融入风险等）",
    "questions": "技术深度考察题（考察实际编码和算法能力）,
    项目难点解决案例（考察问题解决能力）,
    创新思维案例（考察技术创新能力）,
    学习能力案例（考察快速掌握新技术的能力）,
    压力处理案例（考察抗压能力）,
    对AI创业公司的理解（考察认知匹配度）"
  }}
}}
"""
        return prompt

    def screen_resume_execute(self, prompt: str):
        """执行简历分析prompt"""
        try:
            response = call_openai_with_retry(
                openai.ChatCompletion.create,
                self.config,
                model=self.config.MODEL_NAME,
                messages=[
                    {"role": "system", "content": "你是专业的HR招聘顾问。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1500
            )
            txt = response["choices"][0]["message"]["content"].strip()
            
            # 添加原始响应日志
            logging.debug(f"OpenAI原始响应:\n{txt}")
            
            try:
                # 清理和解析JSON
                txt = txt.strip()
                if "```" in txt:
                    txt = txt[txt.find("{"):txt.rfind("}")+1]  # 直接提取JSON部分
                
                # 打印原始响应和清理后的JSON
                logging.debug(f"OpenAI原始响应:\n{txt}")
                
                result = json.loads(txt)
                parsed_info = result.get("parsed_info", {})
                analysis = result.get("analysis", {})
                
                if not parsed_info or not analysis:
                    logging.error("JSON缺少必要字段 parsed_info 或 analysis")
                    logging.error(f"解析结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
                    return {}, {}

                # 补充缺失的评分和详情
                score_fields = [
                    ("education_score", "education_detail"),
                    ("technical_score", "technical_detail"),
                    ("innovation_score", "innovation_detail"),
                    ("growth_score", "growth_detail"),
                    ("startup_score", "startup_detail"),
                    ("teamwork_score", "teamwork_detail")
                ]

                # 确保所有字段都存在
                for score_field, detail_field in score_fields:
                    if score_field not in analysis:
                        logging.warning(f"缺失评分字段: {score_field}")
                        analysis[score_field] = 0
                    if detail_field not in analysis:
                        logging.warning(f"缺失详情字段: {detail_field}")
                        analysis[detail_field] = ""
                    
                    # 尝试转换score为整数
                    try:
                        analysis[score_field] = int(analysis[score_field])
                    except (ValueError, TypeError):
                        logging.warning(f"评分转换失败 {score_field}: {analysis[score_field]}")
                        analysis[score_field] = 0

                return parsed_info, analysis
                
            except json.JSONDecodeError as e:
                logging.error(f"JSON解析失败: {e}\nJSON文本:\n{txt}")
                return {}, {}
                
        except Exception as e:
            logging.error(f"AI评估失败: {e}")
            return {}, {}

    def get_embedding(self, text: str):
        if not text.strip():
            return []
        h = md5_hash(text)
        if self.embedding_cache:
            hit = self.embedding_cache.get(h)
            if hit:
                logging.info("[AIScreener] embedding缓存命中")
                return hit
        try:
            response = call_openai_with_retry(
                openai.Embedding.create,
                self.config,
                input=text,
                model="text-embedding-ada-002"
            )
            emb = response["data"][0]["embedding"]
            if self.embedding_cache:
                self.embedding_cache.set(h, emb)
                self.embedding_cache.save()
            return emb
        except Exception as e:
            logging.error(f"get_embedding失败: {e}")
            return []

def call_openai_with_retry(api_func, config, **kwargs):
    """带重试和超时机制的OpenAI API调用"""
    max_retries = config.AI_RETRY_TIMES
    base_timeout = config.AI_TIMEOUT
    backoff_factor = 2
    
    for attempt in range(max_retries):
        try:
            # 指数退避的等待时间
            if attempt > 0:
                wait_time = min(base_timeout * (backoff_factor ** (attempt - 1)), 60)
                logging.debug(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            
            # 根据尝试次数增加超时时间
            timeout = base_timeout * (attempt + 1)
            kwargs['timeout'] = timeout
            logging.debug(f"调用OpenAI API (尝试 {attempt + 1}/{max_retries}, 超时={timeout}秒)")
            
            response = api_func(**kwargs)
            return response
            
        except openai.error.Timeout as e:
            logging.warning(f"OpenAI请求超时 (尝试 {attempt + 1}/{max_retries}): {e}")
        except openai.error.APIError as e:
            if '502' in str(e):  # Bad Gateway error
                logging.warning(f"OpenAI API网关错误 (尝试 {attempt + 1}/{max_retries}): 502 Bad Gateway")
            else:
                logging.warning(f"OpenAI API错误 (尝试 {attempt + 1}/{max_retries}): {e}")
        except openai.error.RateLimitError as e:
            wait_time = min(backoff_factor ** attempt, 60)
            logging.warning(f"达到速率限制，等待{wait_time}秒后重试: {e}")
            time.sleep(wait_time)
        except openai.error.APIConnectionError as e:
            logging.warning(f"OpenAI API连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
            time.sleep(5)  # 连接错误等待更长时间
        except Exception as e:
            logging.error(f"OpenAI请求异常 (尝试 {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")
            if attempt == max_retries - 1:  # 最后一次尝试时记录更详细的错误信息
                logging.error(f"详细错误信息: {str(e)}", exc_info=True)
        
        # 最后一次尝试失败
        if attempt == max_retries - 1:
            error_msg = f"OpenAI API调用失败，已重试{max_retries}次"
            logging.error(error_msg)
            raise Exception(error_msg)

def truncate_text(text: str, max_len: int, model_name: str) -> str:
    # TODO: refine if needed
    return text[:max_len]
