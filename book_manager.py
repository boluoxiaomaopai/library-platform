# -*- coding: utf-8 -*-
"""图书管理：检索、评分排行、新增、删除、缺失字段统计。"""

from datetime import datetime

from pymongo import DESCENDING

import audit
from config import CST
from db import get_db
from utils import fmt_dt, parse_dt, print_table


class BookManager:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()
        self.col = self.db["books"]

    def count(self):
        return self.col.count_documents({})

    def get_by_isbn(self, isbn):
        return self.col.find_one({"isbn": str(isbn).strip()})

    def search(self, category=None, price_min=None, price_max=None, tags=None,
               title=None, year_min=None, year_max=None, missing_tags=False,
               limit=0, sort=None):
        conditions = []
        if category:
            conditions.append({"category": category})
        if price_min is not None or price_max is not None:
            price = {}
            if price_min is not None:
                price["$gte"] = float(price_min)
            if price_max is not None:
                price["$lte"] = float(price_max)
            conditions.append({"price": price})
        if tags:
            conditions.append({"tags": {"$all": list(tags)}})
        if title:
            conditions.append({"title": {"$regex": title, "$options": "i"}})
        if year_min is not None or year_max is not None:
            date = {}
            if year_min is not None:
                date["$gte"] = datetime(int(year_min), 1, 1, tzinfo=CST)
            if year_max is not None:
                date["$lt"] = datetime(int(year_max) + 1, 1, 1, tzinfo=CST)
            conditions.append({"publish_date": date})
        if missing_tags:
            conditions.append({"tags": {"$exists": False}})

        query = {"$and": conditions} if conditions else {}
        cursor = self.col.find(query)
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(int(limit))
        return list(cursor)

    def missing_tags(self):
        return list(self.col.find({"tags": {"$exists": False}}))

    def missing_tags_count(self):
        return self.col.count_documents({"tags": {"$exists": False}})

    def top_rated(self, limit=10):
        return list(self.col.find(
            {},
            {"_id": 0, "isbn": 1, "title": 1, "author": 1, "rating": 1},
        ).sort([("rating", DESCENDING), ("borrow_count", DESCENDING)]).limit(int(limit)))

    def distinct_categories(self):
        return sorted(self.col.distinct("category"))

    def add_book(self, isbn, title, author, publisher, category, price, rating,
                 stock, tags=None, publish_date=None, location=None, ebook_name=None):
        doc = {
            "isbn": str(isbn).strip(),
            "title": str(title).strip(),
            "author": str(author).strip(),
            "publisher": str(publisher).strip(),
            "category": str(category).strip(),
            "price": float(price),
            "rating": float(rating),
            "stock": int(stock),
            "tags": tags or [],
            "publish_date": parse_dt(publish_date) or datetime.now(CST),
            "borrow_count": 0,
            "location": location or {"floor": "", "shelf": "", "copies": int(stock)},
        }
        if ebook_name:
            doc["ebook_name"] = ebook_name
        result = self.col.insert_one(doc)
        audit.log_action("新增图书", doc["isbn"], "《%s》" % doc["title"])
        print("[新增成功] 《%s》 _id=%s" % (doc["title"], result.inserted_id))
        return result

    def delete_book(self, isbn):
        book = self.get_by_isbn(isbn)
        if not book:
            print("[提示] 没有找到 ISBN 为 %s 的图书。" % isbn)
            return 0
        result = self.col.delete_one({"isbn": str(isbn).strip()})
        audit.log_action("删除图书", isbn, "《%s》" % book.get("title", ""))
        print("[删除完成] 删除 %d 条图书《%s》" % (result.deleted_count, book.get("title", "")))
        return result.deleted_count

    def print_books(self, rows, limit=30):
        data = []
        for b in rows:
            data.append({
                "isbn": b.get("isbn", ""),
                "title": b.get("title", ""),
                "author": b.get("author", ""),
                "category": b.get("category", ""),
                "price": b.get("price", ""),
                "stock": b.get("stock", ""),
                "rating": b.get("rating", ""),
                "publish_date": fmt_dt(b.get("publish_date")),
            })
        return print_table("图书查询结果", data,
                           ["isbn", "title", "author", "category", "price", "stock",
                            "rating", "publish_date"],
                           ["ISBN", "书名", "作者", "类别", "价格", "库存", "评分", "出版日期"],
                           limit=limit)
