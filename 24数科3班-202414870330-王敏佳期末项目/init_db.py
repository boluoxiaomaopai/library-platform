# -*- coding: utf-8 -*-
"""初始化智慧图书馆数据库。

用法：
    python3 init_db.py                    # 单机/副本集：borrow_logs 使用时间序列集合
    python3 init_db.py --mode sharded     # 分片集群：borrow_logs 使用普通集合 + 5 年 TTL 索引
    python3 init_db.py --reset            # 清空并重建
    python3 init_db.py --skip-gridfs      # 不上传电子书文件

连接参数全部来自环境变量（见 config.py / db.py），不在代码里写死地址和密码。
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from pymongo import ASCENDING, DESCENDING

from config import DATA_DIR, GRIDFS_BUCKET, MONGO_DB, TTL_SECONDS
from db import close, get_db, get_gridfs_bucket
from utils import parse_dt

SOURCE_FILES = {
    "books": "books.txt",
    "readers": "readers.txt",
    "borrow_logs": "borrow_logs.txt",
}
DATE_FIELDS = {
    "books": ["publish_date"],
    "readers": ["register_date"],
    "borrow_logs": ["borrow_date", "return_date"],
}
EXPECTED = {"books": 50, "readers": 30, "borrow_logs": 3000}


def load_records(name):
    path = Path(DATA_DIR) / SOURCE_FILES[name]
    with path.open(encoding="utf-8") as handle:
        docs = json.load(handle)
    for doc in docs:
        for field in DATE_FIELDS[name]:
            if field in doc and doc[field]:
                doc[field] = parse_dt(doc[field])
    return docs


def reset(db):
    for name in ("books", "readers", "borrow_logs", "category_stats",
                 "audit_logs", "%s.files" % GRIDFS_BUCKET,
                 "%s.chunks" % GRIDFS_BUCKET):
        db.drop_collection(name)
    print("[重置] 已删除业务集合")


def create_borrow_logs(db, mode):
    if mode == "timeseries":
        try:
            db.create_collection(
                "borrow_logs",
                timeseries={"timeField": "borrow_date", "granularity": "hours"},
                expireAfterSeconds=TTL_SECONDS,
            )
            print("[创建] borrow_logs = 时间序列集合，TTL=%d 秒（5 年）" % TTL_SECONDS)
        except Exception as exc:
            # 兼容不支持顶层 expireAfterSeconds 的版本
            print("[兼容] 顶层 TTL 写法失败（%s），改用内嵌写法" % exc)
            db.create_collection(
                "borrow_logs",
                timeseries={
                    "timeField": "borrow_date",
                    "granularity": "hours",
                    "expireAfterSeconds": TTL_SECONDS,
                },
            )
    else:
        db.create_collection("borrow_logs")
        db["borrow_logs"].create_index(
            [("borrow_date", ASCENDING)],
            name="ttl_borrow_date",
            expireAfterSeconds=TTL_SECONDS,
        )
        print("[创建] borrow_logs = 普通集合 + TTL 索引，TTL=%d 秒（5 年）" % TTL_SECONDS)


def create_collections(db, mode):
    db.create_collection("books")
    db.create_collection("readers")
    db.create_collection("category_stats")
    db.create_collection("audit_logs", capped=True, size=1048576, max=1000)
    create_borrow_logs(db, mode)


def create_indexes(db, mode):
    books = db["books"]
    books.create_index([("isbn", ASCENDING)], unique=True, name="uk_isbn")
    books.create_index([("category", ASCENDING), ("price", ASCENDING)],
                       name="idx_category_price")
    books.create_index([("tags", ASCENDING)], name="idx_tags")
    books.create_index([("title", ASCENDING)], name="idx_title")
    books.create_index([("publish_date", ASCENDING)], name="idx_publish_date")
    books.create_index([("rating", DESCENDING)], name="idx_rating")

    readers = db["readers"]
    readers.create_index([("card_no", ASCENDING)], unique=True, name="uk_card_no")
    readers.create_index([("college", ASCENDING)], name="idx_college")

    logs = db["borrow_logs"]
    # 分片模式只保留 TTL 索引和分片键索引，跨分片查询走全扫，
    # 用于和“按 borrow_date 定向查询”做对比；单机/副本集仍建读者、图书索引。
    if mode != "sharded":
        logs.create_index([("reader_card", ASCENDING), ("borrow_date", DESCENDING)],
                          name="idx_reader_date")
        logs.create_index([("book_isbn", ASCENDING), ("borrow_date", DESCENDING)],
                          name="idx_book_date")

    db["audit_logs"].create_index([("time", DESCENDING)], name="idx_audit_time")
    borrow_index_count = 0 if mode == "sharded" else 2
    print("[创建] 索引完成（books 6 个、readers 2 个、borrow_logs %d 个、audit_logs 1 个）"
          % borrow_index_count)


def import_data(db):
    for name in ("books", "readers", "borrow_logs"):
        if db[name].count_documents({}) > 0:
            print("[跳过] %-12s 已有 %d 条，不重复导入" % (name, db[name].count_documents({})))
            continue
        docs = load_records(name)
        if docs:
            db[name].insert_many(docs)
        actual = db[name].count_documents({})
        print("[导入] %-12s %4d 条（源文件 %d 条）" % (name, actual, len(docs)))


def upload_gridfs(db):
    manifest_path = Path(DATA_DIR) / "gridfs_files" / "files_manifest.txt"
    if not manifest_path.exists():
        print("[跳过] 找不到 files_manifest.txt")
        return
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)

    bucket = get_gridfs_bucket()
    files = db["%s.files" % GRIDFS_BUCKET]
    for group, file_type in (("ebooks", "ebook"), ("covers", "cover")):
        for item in manifest.get(group, []):
            path = Path(DATA_DIR) / "gridfs_files" / item["filename"]
            if not path.exists():
                print("[警告] 缺少文件 %s" % path)
                continue
            existing = files.find_one({"filename": item["filename"]})
            if existing:
                print("[跳过] GridFS 已存在 %s" % item["filename"])
                continue
            with path.open("rb") as stream:
                bucket.upload_from_stream(
                    item["filename"],
                    stream,
                    metadata={
                        "isbn": item["related_isbn"],
                        "file_type": file_type,
                        "original_name": item["filename"],
                    },
                )
            print("[上传] %-12s %6d 字节 -> %s"
                  % (item["filename"], item["bytes"], item["related_isbn"]))
    print("[GridFS] 文件总数 %d" % files.count_documents({}))


def verify(db):
    print("\n========== 数据核对 ==========")
    ok = True
    for name, expected in EXPECTED.items():
        actual = db[name].count_documents({})
        flag = "OK" if actual == expected else "不一致"
        if actual != expected:
            ok = False
        print("  %-12s %4d / %4d  %s" % (name, actual, expected, flag))

    info = {c["name"]: c for c in db.list_collections()}
    log_type = info.get("borrow_logs", {}).get("type")
    print("  borrow_logs 类型：%s" % log_type)
    print("  GridFS 文件数：%d" % db["%s.files" % GRIDFS_BUCKET].count_documents({}))
    print("  总体：%s" % ("通过" if ok else "请检查"))
    return ok


def main():
    parser = argparse.ArgumentParser(description="初始化智慧图书馆数据库")
    parser.add_argument("--mode", choices=["timeseries", "sharded"], default="timeseries",
                        help="timeseries=单机/副本集使用时间序列；sharded=分片集群使用普通集合")
    parser.add_argument("--reset", action="store_true", help="清空后重建")
    parser.add_argument("--skip-gridfs", action="store_true", help="不上传 GridFS 文件")
    args = parser.parse_args()

    db = get_db()
    print("目标数据库：%s（mode=%s）" % (MONGO_DB, args.mode))
    if args.reset:
        reset(db)
    else:
        # 不 reset 时，如果已有业务数据，先提示
        if db["books"].count_documents({}) > 0:
            print("[提示] books 已有数据；如需重建请加 --reset")

    names = set(db.list_collection_names())
    if "books" not in names and "borrow_logs" not in names:
        create_collections(db, args.mode)
    else:
        # 仅补齐缺失集合，避免重复 create_collection
        for name in ("books", "readers", "category_stats", "audit_logs"):
            if name not in names:
                if name == "audit_logs":
                    db.create_collection(name, capped=True, size=1048576, max=1000)
                else:
                    db.create_collection(name)
        if "borrow_logs" not in names:
            create_borrow_logs(db, args.mode)

    import_data(db)
    create_indexes(db, args.mode)
    if not args.skip_gridfs:
        upload_gridfs(db)
    verify(db)
    close()


if __name__ == "__main__":
    main()
