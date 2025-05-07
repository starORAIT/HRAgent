import pymysql
import subprocess
import sys
import os
import logging
from datetime import datetime
import tempfile
import getpass

# Add path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

# 从配置文件获取数据库配置
config = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config/.env"))

# 使用配置文件中的数据库名称
DB_NAME = config.DB_NAME

# 设置备份目录
BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backup")

# 确保备份目录存在
if not os.path.isdir(BACKUP_DIR):
    print(f"备份目录 {BACKUP_DIR} 不存在，正在创建...")
    os.makedirs(BACKUP_DIR)

# 验证数据库密码前先打印提示信息
print(f"准备删除数据库 {DB_NAME}")
print("请输入数据库密码以确认操作（回显已关闭）:")

# 使用 getpass 模块来安全地读取密码
input_password = getpass.getpass().strip()

# 测试输入的密码是否可用
try:
    test_conn = pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=input_password,
        charset='utf8mb4'
    )
    test_conn.close()
    print("密码验证通过，开始操作...")
except pymysql.Error:
    print("密码验证失败，操作取消")
    sys.exit(1)

# 第一步：备份数据库
backup_file = os.path.join(BACKUP_DIR, f"{DB_NAME}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql")

# 创建临时配置文件
temp_cnf = None
try:
    # 创建一个正确格式的MySQL配置文件
    temp_cnf = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.cnf')
    temp_cnf.write('[client]\n')  # 使用[client]部分
    temp_cnf.write(f'user={config.DB_USER}\n')  # 移除引号
    temp_cnf.write(f'password={input_password}\n')  # 移除引号
    temp_cnf.write(f'host={config.DB_HOST}\n')  # 移除引号
    temp_cnf.write(f'port={config.DB_PORT}\n')
    temp_cnf.close()  # 确保写入完成
    os.chmod(temp_cnf.name, 0o600)  # 设置正确的权限

    # 执行备份命令
    print(f"正在备份数据库 {DB_NAME} 到 {backup_file} ...")
    with open(backup_file, 'w') as f:
        backup_cmd = [
            "mysqldump",
            f"--defaults-file={temp_cnf.name}",
            "--set-gtid-purged=OFF",
            "--no-tablespaces",
            "--column-statistics=0",
            "--single-transaction",
            "--quick",
            DB_NAME
        ]
        ret = subprocess.run(backup_cmd, stdout=f, stderr=subprocess.PIPE, text=True)
    
    if ret.returncode != 0:
        print(f"备份数据库失败: {ret.stderr}")
        sys.exit(1)
    print("数据库备份成功！")

    # 连接 MySQL 并删除数据库
    conn = pymysql.connect(
        user=config.DB_USER,
        password=input_password,  # Use input password
        host=config.DB_HOST,
        port=config.DB_PORT,
        charset='utf8mb4'
    )
    cursor = conn.cursor()
    
    # 删除数据库的 SQL 语句
    drop_db_sql = f"DROP DATABASE {DB_NAME};"
    print(f"正在删除数据库 {DB_NAME} ...")
    cursor.execute(drop_db_sql)
    conn.commit()
    print("数据库删除成功！")
    print(f"备份文件保存在: {backup_file}")
    
except Exception as e:
    print(f"操作失败: {e}")
    sys.exit(1)
finally:
    # 清理临时配置文件
    if temp_cnf:
        try:
            os.unlink(temp_cnf.name)
        except:
            pass
    if 'cursor' in locals():
        cursor.close()
    if 'conn' in locals():
        conn.close()
