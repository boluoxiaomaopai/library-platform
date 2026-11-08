# -*- coding: utf-8 -*-
"""操作日志模块：把新增、删除、导出、上传等关键操作写入 audit_logs。

audit_logs 设计为固定集合（capped），最多保留 1000 条，天然只保留最近操作；
按 time 倒序取最近 100 条即可满足任务要求。
"""

from db import get_db
from utils import now

COLLECTION = "audit_logs"


def log_action(action, target="", detail="", result="success", operator="cli"):
    doc = {
        "time": now(),
        "operator": operator,
        "action": action,
        "target": str(target),
        "detail": str(detail),
        "result": str(result),
    }
    try:
        get_db()[COLLECTION].insert_one(doc)
    except Exception as exc:
        # 审计日志失败不应中断主业务，但要在控制台提示
        print("[警告] 操作日志写入失败：%s" % exc)
    return doc


def recent(limit=100):
    return list(get_db()[COLLECTION].find({}).sort("time", -1).limit(int(limit)))


def count():
    return get_db()[COLLECTION].count_documents({})
