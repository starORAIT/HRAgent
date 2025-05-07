# HRAgent

## 项目概述

HRAgent 是一套完整的招聘流程自动化解决方案，通过AI技术实现简历筛选、候选人分析和数据同步等功能，大幅提升招聘效率。系统自动处理收到的简历邮件，执行智能分析，并将结果同步至飞书等协作平台。

## 核心功能

### 1. 邮件自动获取与解析

- 支持多邮箱配置，定时收取简历邮件
- 自动提取简历正文和附件
- 支持多种附件格式：PDF, DOCX, HTML等
- 自动区分简历邮件与普通邮件

### 2. AI简历筛选分析

- 基于OpenAI API的智能简历解析
- 自动识别应聘岗位和简历来源渠道
- 多维度评估候选人（教育背景、技术能力、创新潜力等）
- 自动打分并提供是否通过初筛的建议
- 生成面试问题建议

### 3. 数据同步与导出

- 自动同步候选人数据到飞书表格
- 支持URL编码处理，解决中文字符问题
- 分批处理大量数据，避免API限制

### 4. 系统架构

- 模块化设计，支持分布式部署
- 多进程并发处理，提高效率
- 完善的错误处理和日志记录
- 配置灵活，支持通过环境变量调整系统参数

## 技术栈

- Python 3.8+
- SQLAlchemy (ORM)
- OpenAI API (GPT-4/GPT-3.5)
- 飞书开放平台API
- PyMuPDF, docx (文档解析)
- Playwright (网页爬取)
- asyncio (异步处理)

## 安装部署

### 环境要求

- Python 3.8 或更高版本
- MySQL 5.7 或更高版本
- 足够的API调用额度（OpenAI, 飞书等）

### 安装步骤

1. 克隆代码仓库。
2. 创建并激活虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows
```

3. 安装依赖包

```bash
pip install -r requirements.txt
```

4. 配置环境变量

```bash
cp config/.env.example config/.env
# 编辑 .env 文件，填入必要的配置项
```

   （可选）如果需要，你也可以配置公司信息和职位描述模板：

```bash
cp config/company_info.example.txt config/company_info.txt
cp config/job_desc.example.xlsx config/job_desc.xlsx
# 编辑新创建的 .txt 和 .xlsx 文件，填入你的具体信息。
```

 **在测试环境下，注意把.env.tesing文件拷贝或重命名为.env**

6. 初始化数据库

```bash
python code/init_db.py
```

### 配置项说明

在 `config/.env` 文件中配置以下必要参数：

#### 数据库配置

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=resume_db
```

#### OpenAI配置

```
OPENAI_API_KEY=your_api_key
MODEL_NAME=gpt-4  # 或 gpt-3.5-turbo
```

#### 邮箱配置

```
EMAIL_ACCOUNTS=imap.example.com:993:username:password
EMAIL_FETCH_RANGE_DAYS=7
```

#### 飞书配置

```
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_DOC_ID=your_doc_id
FEISHU_SHEET_NAME=0
```

#### 其他重要配置

```
SCREENING_BATCH_SIZE=50
SCREENING_WORKERS=5
SCREENING_CHECK_INTERVAL=60
EMAIL_CHECK_INTERVAL=300
EXPORT_INTERVAL=300
```

## 运行系统

### 启动完整系统

```bash
python code/workflow_manager.py
```

### 单独运行各模块

邮件获取:

```bash
python code/email_fetching.py
```

简历筛选:

```bash
python code/screening.py
```

数据同步导出:

```bash
python code/sync_and_export.py
```

## 系统扩展

### 添加新的简历源

修改 `resume_fetcher.py` 文件，添加新的简历网站处理逻辑。例如添加猎聘网支持:

```python
async def _extract_liepin_resume(page, url):
    # 实现猎聘网简历提取逻辑
    # ...
```

### 处理需要登录的网站

对于需要登录的网站，在 `SITE_LOGIN_INFO` 字典中添加配置:

```python
SITE_LOGIN_INFO = {
    "liepin.com": {
        "username": os.environ.get("LIEPIN_USERNAME", ""),
        "password": os.environ.get("LIEPIN_PASSWORD", ""),
        # ...其他配置项
    }
}
```

## 常见问题

1. **邮件获取失败**

   - 检查邮箱配置是否正确
   - 确认邮箱开启了IMAP访问
   - 检查网络连接和防火墙设置
2. **AI分析不准确**

   - 尝试使用更高级的模型 (如 GPT-4)
   - 调整 MAX_TOKEN 参数允许处理更长的简历文本
   - 修改 prompt 以提高分析精度
3. **飞书同步失败**

   - 检查飞书应用权限是否配置正确
   - 确认 DOC_ID 和 SHEET_NAME 是否正确
   - 查看日志了解详细错误信息

## 日志和监控

系统日志默认保存在 `logs` 目录下，可通过配置文件调整日志级别和轮转策略。

## 贡献指南

欢迎提交 Pull Request 或 Issue 来改进系统。在提交代码前，请确保:

1. 通过所有测试用例
2. 遵循既有的代码风格
3. 添加必要的文档和注释

## 许可证 (License)

本软件根据 [MIT 许可证](LICENSE) 授权。
