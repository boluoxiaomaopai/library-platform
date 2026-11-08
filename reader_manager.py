# -*- coding: utf-8 -*-
"""读者管理：查询、新增、删除、统计。"""

import audit
from db import get_db
from utils import fmt_dt, parse_dt, print_table


class ReaderManager:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()
        self.col = self.db["readers"]

    def count(self):
        return self.col.count_documents({})

    def get(self, card_no):
        return self.col.find_one({"card_no": str(card_no).strip()})

    def search(self, keyword=None, college=None, level=None):
        conditions = []
        if keyword:
            regex = {"$regex": keyword, "$options": "i"}
            conditions.append({"$or": [{"name": regex}, {"card_no": regex},
                                       {"email": regex}]})
        if college:
            conditions.append({"college": college})
        if level:
            conditions.append({"level": level})
        query = {"$and": conditions} if conditions else {}
        return list(self.col.find(query).sort("card_no", 1))

    def add_reader(self, card_no, name, college, email="", phone="", level="普通",
                   register_date=None, fav_categories=None):
        doc = {
            "card_no": str(card_no).strip(),
            "name": name.strip(),
            "college": college.strip(),
            "email": email.strip() or None,
            "phone": phone.strip(),
            "level": level.strip(),
            "register_date": parse_dt(register_date),
            "fav_categories": fav_categories or [],
        }
        result = self.col.insert_one(doc)
        audit.log_action("新增读者", card_no, name)
        print("[新增成功] 读者 %s（%s）" % (name, card_no))
        return result

    def delete_reader(self, card_no):
        reader = self.get(card_no)
        if not reader:
            print("[提示] 没有找到借阅证号 %s。" % card_no)
            return 0
        result = self.col.delete_one({"card_no": str(card_no).strip()})
        audit.log_action("删除读者", card_no, reader.get("name", ""))
        print("[删除完成] 删除 %d 位读者。" % result.deleted_count)
        return result.deleted_count

    def print_readers(self, rows, limit=30):
        data = [{
            "card_no": r.get("card_no", ""),
            "name": r.get("name", ""),
            "college": r.get("college", ""),
            "level": r.get("level", ""),
            "email": r.get("email") or "（空）",
            "register_date": fmt_dt(r.get("register_date")),
        } for r in rows]
        return print_table("读者查询结果", data,
                           ["card_no", "name", "college", "level", "email", "register_date"],
                           ["借阅证号", "姓名", "学院", "等级", "邮箱", "注册时间"],
                           limit=limit)
