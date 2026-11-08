# -*- coding: utf-8 -*-
"""通用工具：日期解析、日期显示、简单表格输出。"""

from datetime import datetime, timezone

from config import CST


def parse_dt(value):
    """把 ISO 8601 字符串转换成带时区的 datetime；空值返回 None。"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def now():
    return datetime.now(timezone.utc)


def fmt_dt(value, fmt="%Y-%m-%d"):
    if not value:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(CST).strftime(fmt)


def print_table(title, rows, fields, headers=None, limit=30):
    rows = list(rows)
    print("\n== %s ==" % title)
    if not rows:
        print("[提示] 没有查询到符合条件的记录。")
        return 0
    headers = headers or fields
    widths = []
    for i, name in enumerate(headers):
        width = len(str(name))
        for row in rows[:limit]:
            text = str(row.get(fields[i], ""))
            width = max(width, min(len(text), 28))
        widths.append(max(width, 4))
    line = "-" * (sum(widths) + 2 * len(widths))
    print(line)
    print("  ".join(str(name).ljust(widths[i]) for i, name in enumerate(headers)))
    print(line)
    for row in rows[:limit]:
        cells = []
        for i, field in enumerate(fields):
            text = str(row.get(field, ""))
            if len(text) > widths[i]:
                text = text[: widths[i] - 1] + "…"
            cells.append(text.ljust(widths[i]))
        print("  ".join(cells))
    print(line)
    print("共 %d 条%s" % (len(rows), "（只显示前 %d 条）" % limit if len(rows) > limit else ""))
    return len(rows)
