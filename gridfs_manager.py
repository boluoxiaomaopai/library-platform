# -*- coding: utf-8 -*-
"""GridFS 文件管理：上传 PDF/封面、按书名查询、下载并校验字节数、列出文件。"""

import json
from pathlib import Path

import audit
from config import DOWNLOAD_DIR, GRIDFS_BUCKET
from db import get_db, get_gridfs_bucket
from utils import fmt_dt, print_table


class GridFSManager:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()
        self.bucket = get_gridfs_bucket()
        self.files = self.db["%s.files" % GRIDFS_BUCKET]

    def count(self):
        return self.files.count_documents({})

    def upload_file(self, path, isbn, file_type="ebook"):
        path = Path(path)
        if not path.exists():
            print("[提示] 文件不存在：%s" % path)
            return None
        existing = self.files.find_one({"filename": path.name})
        if existing:
            print("[跳过] GridFS 已存在文件 %s（%d 字节）" % (path.name, existing.get("length", 0)))
            return existing["_id"]
        with path.open("rb") as stream:
            file_id = self.bucket.upload_from_stream(
                path.name,
                stream,
                metadata={
                    "isbn": str(isbn),
                    "file_type": file_type,
                    "original_name": path.name,
                },
            )
        audit.log_action("上传文件", path.name, "%s/%s" % (file_type, isbn))
        print("[上传成功] %s（%d 字节） file_id=%s"
              % (path.name, path.stat().st_size, file_id))
        return file_id

    def list_files(self):
        return list(self.files.find(
            {},
            {"_id": 1, "filename": 1, "length": 1, "uploadDate": 1, "metadata": 1},
        ).sort("uploadDate", 1))

    def print_files(self):
        data = []
        for f in self.list_files():
            meta = f.get("metadata") or {}
            data.append({
                "filename": f.get("filename", ""),
                "length": f.get("length", 0),
                "uploadDate": fmt_dt(f.get("uploadDate"), "%Y-%m-%d %H:%M:%S"),
                "isbn": meta.get("isbn", ""),
                "file_type": meta.get("file_type", ""),
            })
        return print_table("GridFS 文件清单", data,
                           ["filename", "length", "uploadDate", "isbn", "file_type"],
                           ["文件名", "字节数", "上传时间", "ISBN", "类型"])

    def find_ebook_by_title(self, title):
        book = self.db["books"].find_one(
            {"title": {"$regex": title, "$options": "i"}, "ebook_name": {"$exists": True}},
            {"isbn": 1, "title": 1, "ebook_name": 1},
        )
        if not book:
            return None, None
        file_doc = self.files.find_one({"filename": book["ebook_name"]})
        return book, file_doc

    def download_by_title(self, title, dest_dir=None):
        book, file_doc = self.find_ebook_by_title(title)
        if not book or not file_doc:
            print("[提示] 没有找到书名包含“%s”的电子书。" % title)
            return None
        return self.download_file(file_doc, dest_dir)

    def download_by_filename(self, filename, dest_dir=None):
        file_doc = self.files.find_one({"filename": filename})
        if not file_doc:
            print("[提示] GridFS 中不存在文件 %s。" % filename)
            return None
        return self.download_file(file_doc, dest_dir)

    def download_file(self, file_doc, dest_dir=None):
        dest_dir = Path(dest_dir or DOWNLOAD_DIR)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / file_doc["filename"]
        try:
            with self.bucket.open_download_stream(file_doc["_id"]) as stream:
                dest.write_bytes(stream.read())
        except Exception as exc:
            print("[下载失败] %s" % exc)
            return None
        expected = int(file_doc.get("length", 0))
        actual = dest.stat().st_size
        ok = expected == actual
        audit.log_action("下载文件", file_doc["filename"],
                         "%d/%d 字节 %s" % (actual, expected, "一致" if ok else "不一致"))
        print("[下载完成] %s" % dest)
        print("[字节校验] 上传 %d 字节，下载 %d 字节，%s"
              % (expected, actual, "一致" if ok else "不一致！"))
        return {"path": dest, "expected": expected, "actual": actual, "match": ok}

    def verify_manifest(self):
        manifest = Path("data/gridfs_files/files_manifest.txt")
        # 也可以从 data 目录读取清单，兼容不同工作目录
        if not manifest.exists():
            manifest = Path(__file__).resolve().parent / "data" / "gridfs_files" / "files_manifest.txt"
        with manifest.open(encoding="utf-8") as f:
            payload = json.load(f)
        results = []
        for group in ("ebooks", "covers"):
            for item in payload.get(group, []):
                doc = self.files.find_one({"filename": item["filename"]})
                actual = int(doc.get("length", 0)) if doc else 0
                results.append({
                    "filename": item["filename"],
                    "manifest_bytes": item["bytes"],
                    "gridfs_bytes": actual,
                    "match": item["bytes"] == actual,
                    "isbn": item["related_isbn"],
                    "file_type": "ebook" if group == "ebooks" else "cover",
                })
        return results
