# HRAgent

## Project Overview

HRAgent is a complete solution for automating the recruitment process. It leverages AI technology to implement features such as resume screening, candidate analysis, and data synchronization, significantly improving recruitment efficiency. The system automatically processes received resume emails, performs intelligent analysis, and synchronizes the results to collaboration platforms like Feishu (Lark).

## Core Features

### 1. Automatic Email Retrieval and Parsing

- Supports multiple email account configurations for scheduled fetching of resume emails.
- Automatically extracts resume body text and attachments.
- Supports various attachment formats: PDF, DOCX, HTML, etc.
- Automatically distinguishes between resume emails and regular emails.

### 2. AI Resume Screening and Analysis

- Intelligent resume parsing based on the OpenAI API.
- Automatic identification of the applied position and resume source channel.
- Multi-dimensional candidate assessment (education background, technical skills, innovation potential, etc.).
- Automatic scoring and suggestions for initial screening decisions.
- Generates suggested interview questions.

### 3. Data Synchronization and Export

- Automatically synchronizes candidate data to Feishu (Lark) Sheets.
- Supports URL encoding to handle Chinese characters.
- Processes large volumes of data in batches to avoid API limitations.

### 4. System Architecture

- Modular design, supporting distributed deployment.
- Multi-process concurrent processing to enhance efficiency.
- Comprehensive error handling and logging mechanisms.
- Flexible configuration, allowing system parameter adjustments via environment variables.

## Technology Stack

- Python 3.8+
- SQLAlchemy (ORM)
- OpenAI API (GPT-4/GPT-3.5)
- Feishu (Lark) Open Platform API
- PyMuPDF, python-docx (Document parsing)
- Playwright (Web scraping)
- asyncio (Asynchronous processing)

## Installation and Deployment

### Prerequisites

- Python 3.8 or higher
- MySQL 5.7 or higher
- Sufficient API call quotas (OpenAI, Feishu, etc.)

### Installation Steps

1. Clone the code repository.
2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate  # Windows
   ```
3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables:

   ```bash
   cp config/.env.example config/.env
   # Edit the .env file and fill in the necessary configuration items.
   ```

   (Optional) You can also configure company information and job description templates:

   ```bash
   cp config/company_info.example.txt config/company_info.txt
   cp config/job_desc.example.xlsx config/job_desc.xlsx
   # Edit the newly created .txt and .xlsx files with your specific information.
   ```

   **Note for testing environment: Copy or rename `.env.testing` to `.env`**
5. Initialize the database:

   ```bash
   python code/init_db.py
   ```

### Configuration Item Description

Configure the following necessary parameters in the `config/.env` file:

#### Database Configuration

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_NAME=resume_db
```

#### OpenAI Configuration

```
OPENAI_API_KEY=your_api_key
MODEL_NAME=gpt-4  # or gpt-3.5-turbo
```

#### Email Configuration

```
EMAIL_ACCOUNTS=imap.example.com:993:username:password
EMAIL_FETCH_RANGE_DAYS=7
```

#### Feishu (Lark) Configuration

```
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_DOC_ID=your_doc_id
FEISHU_SHEET_NAME=0
```

#### Other Important Configurations

```
SCREENING_BATCH_SIZE=50
SCREENING_WORKERS=5
SCREENING_CHECK_INTERVAL=60
EMAIL_CHECK_INTERVAL=300
EXPORT_INTERVAL=300
```

## Running the System

### Start the Complete System

```bash
python code/workflow_manager.py
```

### Run Individual Modules

Email Fetching:

```bash
python code/email_fetching.py
```

Resume Screening:

```bash
python code/screening.py
```

Data Synchronization and Export:

```bash
python code/sync_and_export.py
```

## System Extension

### Adding a New Resume Source

Modify the `resume_fetcher.py` file to add logic for handling new resume websites. For example, to add support for Liepin:

```python
async def _extract_liepin_resume(page, url):
    # Implement Liepin resume extraction logic
    # ...
```

### Handling Websites Requiring Login

For websites that require login, add configuration to the `SITE_LOGIN_INFO` dictionary:

```python
SITE_LOGIN_INFO = {
    "liepin.com": {
        "username": os.environ.get("LIEPIN_USERNAME", ""),
        "password": os.environ.get("LIEPIN_PASSWORD", ""),
        # ...other configuration items
    }
}
```

## FAQ (Frequently Asked Questions)

1. **Email Fetching Fails**
   * Check if the email configuration is correct.
   * Confirm that IMAP access is enabled for the email account.
   * Check network connection and firewall settings.
2. **AI Analysis is Inaccurate**
   * Try using a more advanced model (e.g., GPT-4).
   * Adjust the `MAX_TOKEN` parameter to allow processing of longer resume texts.
   * Modify the prompt to improve analysis accuracy.
3. **Feishu (Lark) Synchronization Fails**
   * Check if Feishu application permissions are configured correctly.
   * Confirm that `DOC_ID` and `SHEET_NAME` are correct.
   * Check the logs for detailed error information.

## Logging and Monitoring

System logs are saved in the `logs` directory by default. Log level and rotation policy can be adjusted through the configuration file.

## Contribution Guidelines

Pull Requests or Issues are welcome to improve the system. Before submitting code, please ensure:

1. All test cases pass.
2. Adherence to the existing code style.
3. Necessary documentation and comments are added.

## License

This software is licensed under the [MIT License](LICENSE).
