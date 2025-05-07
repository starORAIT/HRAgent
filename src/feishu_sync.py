# feishu_sync.py
import requests
import json
import logging
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs, urlencode  # 添加 URL 处理相关导入

"""
飞书同步模块

本模块负责将候选人数据同步到飞书表格：
1. 获取飞书API访问令牌
2. 格式化候选人数据
3. 处理URL编码以解决中文和特殊字符问题
4. 分批写入数据到飞书表格
"""

def get_feishu_access_token(config) -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": config.FEISHU_APP_ID,
        "app_secret": config.FEISHU_APP_SECRET
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("tenant_access_token", "")
            return token
        else:
            logging.error(f"获取飞书令牌失败, 状态码: {resp.status_code}, 响应: {resp.text}")
    except Exception as e:
        logging.error(f"获取飞书令牌异常: {e}")
    return ""

def convert_value(value, field_name=None, config=None):
    """
    转换各类型字段值为适合飞书API的格式
    
    处理内容包括:
    - 数值字段转为整数
    - 布尔值转为是/否
    - URL编码处理，解决中文字符问题
    - 日期时间格式化
    
    Args:
        value: 字段原始值
        field_name: 字段名称，用于特定处理逻辑
        config: 配置对象，可选
        
    Returns:
        转换后的值，适合飞书API使用
    """
    # 如果值为None或空，返回空值
    if value is None or value == "":
        return None  # 返回None而不是空字符串，让飞书API处理

    # 处理数值类型字段 - 直接返回整数值
    number_fields = {
        "id", "age", "total_score", 
        "education_score", "technical_score", "innovation_score",
        "growth_score", "startup_score", "teamwork_score"
    }
    if field_name in number_fields:
        try:
            if isinstance(value, (int, float)):
                return int(value)  # 直接返回整数
            if isinstance(value, str) and value.strip():
                return int(float(value))  # 处理字符串数字
            return 0  # 处理其他情况
        except (ValueError, TypeError):
            return 0

    # 处理布尔值字段
    if isinstance(value, bool):
        return "是" if value else "否"

    # 处理URL类型字段 - 添加URL编码处理
    if field_name in ["resume_file_url", "original_email_url"]:
        if value and str(value).strip() and str(value).strip().lower() != "none":
            try:
                # 解析 URL
                parsed = urlparse(str(value))
                
                # 对路径部分进行编码，保持原始的查询参数
                encoded_path = quote(parsed.path)
                
                # 重建 URL，保持原始的 scheme、netloc 和查询参数
                encoded_url = f"{parsed.scheme}://{parsed.netloc}{encoded_path}"
                if parsed.query:
                    # 解析并重新编码查询参数
                    query_params = parse_qs(parsed.query)
                    encoded_params = {k: [quote(v) for v in vs] for k, vs in query_params.items()}
                    encoded_url = f"{encoded_url}?{urlencode(encoded_params, doseq=True)}"
                
                return encoded_url
            except Exception as e:
                logging.warning(f"URL编码失败 ({value}): {e}")
                return str(value)
        return None

    # 处理日期时间
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    # 其他字段转为字符串
    return str(value)

def format_candidate_table(session):
    """格式化候选人数据表"""
    from db_manager import Candidate
    candidates = session.query(Candidate).all()
    
    # 定义列类型
    column_types = [
        "number",    # ID
        "string",    # 姓名
        "string",    # 应聘职位
        "string",    # 电话
        "string",    # 邮箱
        "string",    # 微信
        "string",    # 最近公司
        "string",    # 工作经验
        "string",    # 最高学历
        "string",    # 最高院校
        "string",    # 第一学历
        "string",    # 第一院校
        "string",    # 婚姻状况
        "number",    # 年龄
        "string",    # 性别
        "string",    # 期望薪资
        "string",    # 简历来源
        "number",    # 总分
        "string",    # 是否通过
        "string",    # 重点关注
        "number",    # 教育得分
        "string",    # 教育评价
        "number",    # 技术得分
        "string",    # 技术评价
        "number",    # 创新得分
        "string",    # 创新评价
        "number",    # 成长得分
        "string",    # 成长评价
        "number",    # 创业得分
        "string",    # 创业评价
        "number",    # 团队得分
        "string",    # 团队评价
        "string",    # 风险提示
        "string",    # 面试问题
        "string",    # 状态
        "string",    # 简历哈希值
        "string",    # 邮件标题
        "string",    # 收件邮箱
        "string",    # 发件时间
        "string",    # 简历OSS链接
        "string",    # 创建时间
        "string",    # 更新时间
    ]
    
    header = [
        # 基本信息
        "ID", "姓名", "应聘职位", "电话", "邮箱", "微信", "最近公司",
        "工作经验", "最高学历", "最高院校", "第一学历", "第一院校",
        "婚姻状况", "年龄", "性别", "期望薪资", "简历来源",
        # AI评估结果
        "总分", "是否通过", "重点关注",
        # 维度评分
        "教育得分", "教育评价",
        "技术得分", "技术评价",
        "创新得分", "创新评价",
        "成长得分", "成长评价",
        "创业得分", "创业评价",
        "团队得分", "团队评价",
        # 风险和问题
        "风险提示", "面试问题",
        # 系统信息
        "状态", "简历哈希值", "邮件标题", "收件邮箱", "发件时间",
        "简历OSS链接", "创建时间", "更新时间"
    ]
    
    rows = [header]
    for c in candidates:
        # Helper function to format datetime
        def format_datetime(dt):
            if dt is None:
                return ""
            if isinstance(dt, datetime):
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            return str(dt)
            
        row = [
            int(c.id) if c.id is not None else 0,  # ID 必须为数字
            c.name or "",
            c.apply_position or "",
            c.phone or "",
            c.email or "",
            c.wechat or "",
            c.latest_company or "",
            c.work_experience or "",
            c.highest_education or "",
            c.highest_university or "",
            c.first_education or "",
            c.first_university or "",
            c.marital_status or "",
            int(c.age) if c.age is not None else 0,  # 年龄必须为数字
            c.gender or "",
            c.expected_salary or "",
            c.resume_source or "",
            int(c.total_score) if c.total_score is not None else 0,  # 总分必须为数字
            "通过" if c.is_qualified else "不通过",
            "是" if c.focus_flag else "否",
            # 各维度评分必须为数字
            int(c.education_score) if c.education_score is not None else 0,
            c.education_detail or "",
            int(c.technical_score) if c.technical_score is not None else 0,
            c.technical_detail or "",
            int(c.innovation_score) if c.innovation_score is not None else 0,
            c.innovation_detail or "",
            int(c.growth_score) if c.growth_score is not None else 0,
            c.growth_detail or "",
            int(c.startup_score) if c.startup_score is not None else 0,
            c.startup_detail or "",
            int(c.teamwork_score) if c.teamwork_score is not None else 0,
            c.teamwork_detail or "",
            c.risk or "",
            c.questions or "",
            c.status or "",
            c.resume_hash or "",
            c.email_subject or "",
            c.inbox_account or "",
            format_datetime(c.mail_sent_time),
            convert_value(c.resume_file_url, "resume_file_url"),
            format_datetime(c.create_time),
            format_datetime(c.update_time)
        ]
        rows.append(row)
    return rows, column_types

def col_to_letter(n):
    """将数字转换为Excel风格的列标，1->A, 2->B, ... 27->AA"""
    result = ""
    while n:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result

def sync_candidates_to_feishu(config, session):
    """同步候选人数据到飞书表格"""
    token = get_feishu_access_token(config)
    if not token:
        logging.error("无法获取飞书访问令牌")
        return
    
    table_data, column_types = format_candidate_table(session)
    if not table_data or len(table_data) < 2:
        return

    num_rows = len(table_data)
    num_cols = len(table_data[0])
    last_col = col_to_letter(num_cols)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }

    try:
        spreadsheet_token = config.FEISHU_DOC_ID
        sheet_id = config.FEISHU_SHEET_NAME
        base_url = "https://open.feishu.cn/open-apis"
        
        # 1. 获取电子表格元数据 - 使用正确的API路径
        logging.info(f"获取电子表格信息 - spreadsheet_token: {spreadsheet_token}")
        meta_url = f"{base_url}/sheets/v2/spreadsheets/{spreadsheet_token}/metainfo"
        meta_resp = requests.get(meta_url, headers=headers)
        if meta_resp.status_code != 200:
            logging.error(f"获取电子表格元数据失败: {meta_resp.status_code} - {meta_resp.text}")
            return

        # 2. 清空表格内容
        range_str = f"{sheet_id}!A1:{last_col}{num_rows+1}"
        clear_url = f"{base_url}/sheets/v2/spreadsheets/{spreadsheet_token}/values"
        clear_data = {
            "valueRange": {
                "range": range_str,
                "values": [[""]]
            }
        }
        
        logging.info(f"清空表格范围: {range_str}")
        clear_resp = requests.put(
            clear_url,
            headers=headers,
            json=clear_data
        )
        
        if clear_resp.status_code != 200:
            logging.error(f"清空表格失败: {clear_resp.status_code} - {clear_resp.text}")
            return

        # 3. 写入数据 - 确保数据可以JSON序列化
        write_url = f"{base_url}/sheets/v2/spreadsheets/{spreadsheet_token}/values"
        
        # 先写入表头
        header_data = {
            "valueRange": {
                "range": f"{sheet_id}!A1:{last_col}1",
                "values": [table_data[0]]
            }
        }
        
        # Debug log for data
        logging.debug(f"Header data: {json.dumps(header_data, ensure_ascii=False)}")
        
        header_resp = requests.put(write_url, headers=headers, json=header_data)
        if header_resp.status_code != 200:
            logging.error(f"写入表头失败: {header_resp.status_code} - {header_resp.text}")
            return

        # 分批写入数据
        batch_size = 1000
        data_rows = table_data[1:]  # 跳过表头
        for i in range(0, len(data_rows), batch_size):
            batch = data_rows[i:i + batch_size]
            batch_range = f"{sheet_id}!A{i+2}:{last_col}{i+len(batch)+1}"
            
            write_data = {
                "valueRange": {
                    "range": batch_range,
                    "values": batch
                }
            }
            
            # Verify data is JSON serializable
            try:
                json.dumps(write_data)
            except TypeError as e:
                logging.error(f"数据序列化失败: {e}")
                continue
            
            logging.info(f"写入数据批次 {i//batch_size + 1}, 范围: {batch_range}")
            write_resp = requests.put(write_url, headers=headers, json=write_data)
            
            if write_resp.status_code != 200:
                logging.error(f"写入数据失败: {write_resp.status_code} - {write_resp.text}")
                return
            
        logging.info(f"成功同步 {num_rows} 行数据到飞书表格")
        
    except Exception as e:
        logging.error(f"同步到飞书失败: {e}", exc_info=True)
