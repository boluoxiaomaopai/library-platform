# -*- coding: utf-8 -*-
"""统计分析：分类统计、学院借阅 Top5、月度趋势、热门图书、统计结果落库。"""

import json
from pathlib import Path

from bson import json_util

import audit
from config import EXPORT_DIR
from db import get_db
from utils import fmt_dt, print_table


class StatManager:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()
        self.books = self.db["books"]
        self.readers = self.db["readers"]
        self.logs = self.db["borrow_logs"]
        self.stats = self.db["category_stats"]

    def category_stats(self):
        return list(self.books.aggregate([
            {"$group": {
                "_id": "$category",
                "book_count": {"$sum": 1},
                "avg_price": {"$avg": "$price"},
                "avg_rating": {"$avg": "$rating"},
                "stock_total": {"$sum": "$stock"},
            }},
            {"$sort": {"book_count": -1, "_id": 1}},
        ]))

    def college_top5(self):
        return list(self.logs.aggregate([
            {"$lookup": {
                "from": "readers",
                "localField": "reader_card",
                "foreignField": "card_no",
                "as": "reader",
            }},
            {"$unwind": "$reader"},
            {"$group": {"_id": "$reader.college", "borrow_total": {"$sum": 1}}},
            {"$sort": {"borrow_total": -1, "_id": 1}},
            {"$limit": 5},
            {"$project": {"_id": 0, "college": "$_id", "borrow_total": 1}},
        ]))

    def monthly_trend(self):
        return list(self.logs.aggregate([
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$borrow_date",
                                          "timezone": "+08:00"}},
                "borrow_total": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
            {"$project": {"_id": 0, "month": "$_id", "borrow_total": 1}},
        ]))

    def top_borrowed_with_location(self, limit=10):
        return list(self.books.find(
            {},
            {"_id": 0, "isbn": 1, "title": 1, "author": 1,
             "borrow_count": 1, "location": 1},
        ).sort("borrow_count", -1).limit(int(limit)))

    def save_category_stats(self):
        pipeline = [
            {"$group": {
                "_id": "$category",
                "book_count": {"$sum": 1},
                "avg_price": {"$avg": "$price"},
                "avg_rating": {"$avg": "$rating"},
                "stock_total": {"$sum": "$stock"},
            }},
            {"$merge": {
                "into": "category_stats",
                "on": "_id",
                "whenMatched": "replace",
                "whenNotMatched": "insert",
            }},
        ]
        list(self.books.aggregate(pipeline))
        n = self.stats.count_documents({})
        audit.log_action("统计结果落库", "category_stats", "%d 组" % n)
        print("[落库完成] category_stats 共 %d 条" % n)
        return n

    def export_category_stats(self):
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = Path(EXPORT_DIR) / "category_stats.json"
        rows = list(self.stats.find({}))
        path.write_text(json_util.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        audit.log_action("导出统计结果", str(path), "%d 条" % len(rows))
        print("[导出完成] %s（%d 条）" % (path, len(rows)))
        return path

    def print_category(self):
        rows = self.category_stats()
        data = [{
            "category": r["_id"],
            "book_count": r["book_count"],
            "avg_price": round(r["avg_price"], 2),
            "avg_rating": round(r["avg_rating"], 2),
            "stock_total": r["stock_total"],
        } for r in rows]
        return print_table("分类统计", data,
                           ["category", "book_count", "avg_price", "avg_rating", "stock_total"],
                           ["类别", "藏书量", "平均价格", "平均评分", "库存总量"])

    def print_college_top5(self):
        rows = self.college_top5()
        return print_table("学院借阅总量 Top5", rows,
                           ["college", "borrow_total"], ["学院", "借阅总量"])

    def print_monthly_trend(self):
        rows = self.monthly_trend()
        return print_table("月度借阅趋势", rows,
                           ["month", "borrow_total"], ["年月", "借阅量"])

    def print_top_books(self):
        rows = self.top_borrowed_with_location()
        data = []
        for r in rows:
            loc = r.get("location") or {}
            data.append({
                "title": r.get("title", ""),
                "author": r.get("author", ""),
                "borrow_count": r.get("borrow_count", 0),
                "location": "%s/%s/复本%s" % (loc.get("floor", "-"), loc.get("shelf", "-"),
                                              loc.get("copies", "-")),
            })
        return print_table("借阅次数 Top10 与馆藏位置", data,
                           ["title", "author", "borrow_count", "location"],
                           ["书名", "作者", "借阅次数", "馆藏位置"])
