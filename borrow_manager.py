# -*- coding: utf-8 -*-
"""借阅管理：借阅登记、归还、逾期查询、流水查询。

borrow_logs 的任务二设计是时间序列集合；时间序列集合不支持单条 update，
因此归还是“删除原借出流水 + 插入一条已归还流水”，库存用 update_many 恢复。
"""

from datetime import timedelta, timezone

from pymongo import DESCENDING

import audit
from db import get_db
from utils import fmt_dt, now, print_table


class BorrowManager:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()
        self.logs = self.db["borrow_logs"]
        self.books = self.db["books"]
        self.readers = self.db["readers"]

    def count(self):
        return self.logs.count_documents({})

    def borrow(self, card_no, isbn):
        card_no, isbn = str(card_no).strip(), str(isbn).strip()
        reader = self.readers.find_one({"card_no": card_no})
        book = self.books.find_one({"isbn": isbn})
        if not reader:
            print("[提示] 不存在借阅证号 %s。" % card_no)
            return 0
        if not book:
            print("[提示] 不存在 ISBN 为 %s 的图书。" % isbn)
            return 0
        if int(book.get("stock", 0)) <= 0:
            print("[提示] 《%s》库存为 0，无法借出。" % book.get("title"))
            return 0
        opened = self.logs.find_one({
            "reader_card": card_no,
            "book_isbn": isbn,
            "status": {"$in": ["借出", "逾期"]},
        })
        if opened:
            print("[提示] 该读者对这本书已有未归还记录，请勿重复借阅。")
            return 0

        self.logs.insert_one({
            "borrow_date": now(),
            "reader_card": card_no,
            "book_isbn": isbn,
            "status": "借出",
            "duration_days": 0,
        })
        self.books.update_one({"isbn": isbn},
                              {"$inc": {"stock": -1, "borrow_count": 1}})
        audit.log_action("借阅登记", "%s/%s" % (card_no, isbn), reader.get("name", ""))
        print("[借阅成功] %s 借出《%s》，库存 %d -> %d"
              % (reader.get("name"), book.get("title"), book.get("stock"),
                 int(book.get("stock")) - 1))
        return 1

    def return_book(self, card_no, isbn):
        card_no, isbn = str(card_no).strip(), str(isbn).strip()
        log = self.logs.find_one(
            {"reader_card": card_no, "book_isbn": isbn,
             "status": {"$in": ["借出", "逾期"]}},
            sort=[("borrow_date", DESCENDING)],
        )
        if not log:
            print("[提示] 没有找到该读者对这本书的未归还记录。")
            return 0

        borrow_date = log["borrow_date"]
        if borrow_date.tzinfo is None:
            borrow_date = borrow_date.replace(tzinfo=timezone.utc)
        days = max((now() - borrow_date).days, 1)

        # 时间序列集合不支持单条 update，删除 + 重新插入等价实现
        deleted = self.logs.delete_one({"_id": log["_id"]})
        self.logs.insert_one({
            "borrow_date": borrow_date,
            "return_date": now(),
            "reader_card": card_no,
            "book_isbn": isbn,
            "status": "已归还",
            "duration_days": days,
        })
        updated = self.books.update_many({"isbn": isbn}, {"$inc": {"stock": 1}})
        audit.log_action("归还处理", "%s/%s" % (card_no, isbn), "借阅 %d 天" % days)
        print("[归还成功] 删除原流水 %d 条，新增已归还流水，借阅 %d 天，库存更新 %d 条"
              % (deleted.deleted_count, days, updated.modified_count))
        return 1

    def history_by_reader(self, card_no):
        return list(self.logs.find({"reader_card": str(card_no).strip()})
                    .sort("borrow_date", DESCENDING))

    def overdue(self, days=30):
        cutoff = now() - timedelta(days=int(days))
        rows = list(self.logs.find({
            "$or": [
                {"status": "逾期"},
                {"status": "借出", "borrow_date": {"$lt": cutoff}},
            ]
        }).sort("borrow_date", 1))
        return rows

    def status_summary(self):
        return list(self.logs.aggregate([
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]))

    def print_logs(self, rows, limit=30):
        data = [{
            "reader_card": r.get("reader_card", ""),
            "book_isbn": r.get("book_isbn", ""),
            "status": r.get("status", ""),
            "borrow_date": fmt_dt(r.get("borrow_date"), "%Y-%m-%d %H:%M"),
            "return_date": fmt_dt(r.get("return_date"), "%Y-%m-%d %H:%M"),
            "duration_days": r.get("duration_days", ""),
        } for r in rows]
        return print_table("借阅流水", data,
                           ["reader_card", "book_isbn", "status", "borrow_date",
                            "return_date", "duration_days"],
                           ["借阅证号", "ISBN", "状态", "借阅时间", "归还时间", "天数"],
                           limit=limit)
