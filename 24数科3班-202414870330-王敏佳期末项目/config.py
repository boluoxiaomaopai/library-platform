# -*- coding: utf-8 -*-
"""全局配置：连接参数、数据库名、TTL、路径。

所有连接参数优先从环境变量读取，避免把真实地址、账号、密码写死在代码里。
"""

import os
from datetime import timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(BASE_DIR / "downloads")))
EXPORT_DIR = Path(os.getenv("EXPORT_DIR", str(BASE_DIR / "exports")))

MONGO_HOST = os.getenv("MONGO_HOST", "127.0.0.1")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "smart_library")
MONGO_USERNAME = os.getenv("MONGO_USERNAME", "")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "")
MONGO_AUTH_SOURCE = os.getenv("MONGO_AUTH_SOURCE", MONGO_DB)
MONGO_REPLICA_SET = os.getenv("MONGO_REPLICA_SET", "")
MONGO_READ_PREFERENCE = os.getenv("MONGO_READ_PREFERENCE", "primary")
MONGO_URI = os.getenv("MONGO_URI", "")

# borrow_logs 保留 5 年（老师反馈：2 年会清掉 2024 年 10 月以前的数据）
TTL_SECONDS = 5 * 365 * 24 * 60 * 60
GRIDFS_BUCKET = os.getenv("GRIDFS_BUCKET", "fs")

CST = timezone(timedelta(hours=8))
DATE_FIELDS = {
    "books": ["publish_date"],
    "readers": ["register_date"],
    "borrow_logs": ["borrow_date", "return_date"],
}
