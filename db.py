# -*- coding: utf-8 -*-
"""MongoDB 连接模块（全项目唯一的连接入口）。

默认连接本机 27017 的 smart_library；地址、端口、账号、副本集名称都可用环境变量覆盖：

    export MONGO_HOST=127.0.0.1
    export MONGO_PORT=27017
    export MONGO_DB=smart_library
    export MONGO_USERNAME=lib_writer
    export MONGO_PASSWORD=你的密码
    export MONGO_AUTH_SOURCE=smart_library
    export MONGO_REPLICA_SET=rs0          # 连接副本集时设置
    export MONGO_READ_PREFERENCE=primary  # 或 secondaryPreferred
"""

from urllib.parse import quote_plus

from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from config import (
    GRIDFS_BUCKET,
    MONGO_AUTH_SOURCE,
    MONGO_DB,
    MONGO_HOST,
    MONGO_PASSWORD,
    MONGO_PORT,
    MONGO_READ_PREFERENCE,
    MONGO_REPLICA_SET,
    MONGO_URI,
    MONGO_USERNAME,
)

_client = None


def build_uri():
    """根据配置拼出连接串，绝不把密码写死在代码里。"""
    if MONGO_URI:
        return MONGO_URI

    auth = ""
    if MONGO_USERNAME:
        auth = "%s:%s@" % (quote_plus(MONGO_USERNAME), quote_plus(MONGO_PASSWORD))

    params = []
    if MONGO_REPLICA_SET:
        params.append("replicaSet=%s" % MONGO_REPLICA_SET)
    if MONGO_USERNAME:
        params.append("authSource=%s" % MONGO_AUTH_SOURCE)
    if MONGO_READ_PREFERENCE:
        params.append("readPreference=%s" % MONGO_READ_PREFERENCE)

    uri = "mongodb://%s%s:%d/%s" % (auth, MONGO_HOST, MONGO_PORT, MONGO_DB)
    if params:
        uri += "?" + "&".join(params)
    return uri


def get_client():
    global _client
    if _client is None:
        _client = MongoClient(
            build_uri(),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
    return _client


def get_db():
    return get_client()[MONGO_DB]


def get_gridfs_bucket():
    import gridfs

    return gridfs.GridFSBucket(get_db(), bucket_name=GRIDFS_BUCKET)


def ping():
    try:
        get_client().admin.command("ping")
        version = get_client().server_info().get("version", "未知")
        return True, "连接成功，MongoDB 版本 %s" % version
    except ServerSelectionTimeoutError:
        return False, "连接超时：请确认 MongoDB 已启动，地址 %s:%d" % (MONGO_HOST, MONGO_PORT)
    except PyMongoError as exc:
        return False, "连接失败：%s" % exc


def close():
    global _client
    if _client is not None:
        _client.close()
        _client = None


if __name__ == "__main__":
    ok, message = ping()
    print("[连接串] %s" % build_uri())
    print("[状态] %s" % message)
    if ok:
        db = get_db()
        for name in ("books", "readers", "borrow_logs", "category_stats", "audit_logs"):
            print("  %-15s %d" % (name, db[name].count_documents({})))
    close()
