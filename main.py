# -*- coding: utf-8 -*-
"""智慧图书馆数字资源平台 —— 菜单式主程序。

运行前：
    export MONGO_HOST=127.0.0.1
    export MONGO_PORT=27017
    export MONGO_DB=smart_library
    # 启用认证后：
    export MONGO_USERNAME=lib_writer
    export MONGO_PASSWORD=你的密码
    export MONGO_AUTH_SOURCE=smart_library
    # 副本集：
    export MONGO_REPLICA_SET=rs0
    export MONGO_READ_PREFERENCE=secondaryPreferred

    python3 main.py
"""

import sys

from pymongo.errors import PyMongoError

import audit
from book_manager import BookManager
from borrow_manager import BorrowManager
from db import build_uri, close, get_db, ping
from gridfs_manager import GridFSManager
from reader_manager import ReaderManager
from stat_manager import StatManager
from utils import fmt_dt, print_table

MENU = """
================= 智慧图书馆数字资源平台 =================
  1. 按类别 + 价格区间检索图书
  2. 按多个标签检索（要求全部包含）
  3. 按书名模糊检索
  4. 按出版年份范围检索
  5. 查询缺少 tags 字段的图书（数据质量核查）
  6. 评分最高的 10 本图书
  7. 按类别统计藏书量 / 平均价格 / 平均评分
  8. 各学院借阅总量 Top5
  9. 按月统计借阅趋势
 10. 借阅次数 Top10 图书及馆藏位置
 11. 将分类统计结果写入 category_stats
 12. 导出 category_stats 为 JSON
 13. 上传电子书 / 封面到 GridFS
 14. 按书名查询并下载电子书（校验字节数）
 15. 列出 GridFS 所有文件
 16. 查看最近 100 条操作日志
 17. 新增图书
 18. 删除图书
 19. 借阅登记
 20. 归还处理
 21. 新增读者
 22. 删除读者
  0. 退出
==========================================================
"""


def ask(prompt, default=None):
    tip = prompt
    if default not in (None, ""):
        tip += "（默认 %s）" % default
    value = input(tip + "：").strip()
    return default if value == "" else value


def ask_float(prompt, default=None):
    value = ask(prompt, default)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        print("[提示] 不是数字，已忽略。")
        return None


class Application:
    def __init__(self):
        self.db = get_db()
        self.books = BookManager(self.db)
        self.readers = ReaderManager(self.db)
        self.borrows = BorrowManager(self.db)
        self.stats = StatManager(self.db)
        self.gridfs = GridFSManager(self.db)

    # ---------------- 检索 ----------------
    def menu_category_price(self):
        category = ask("类别（回车跳过）")
        low = ask_float("最低价格")
        high = ask_float("最高价格")
        rows = self.books.search(category=category or None, price_min=low, price_max=high)
        self.books.print_books(rows)

    def menu_tags(self):
        text = ask("标签（多个用逗号分隔，要求全部包含）")
        text = text.replace("，", ",").replace("、", ",")
        tags = [x.strip() for x in text.split(",") if x.strip()]
        rows = self.books.search(tags=tags)
        self.books.print_books(rows)

    def menu_title(self):
        title = ask("书名关键词")
        rows = self.books.search(title=title)
        self.books.print_books(rows)

    def menu_year(self):
        low = ask("起始年份（如 2020）")
        high = ask("结束年份（如 2025）")
        rows = self.books.search(
            year_min=int(low) if str(low).isdigit() else None,
            year_max=int(high) if str(high).isdigit() else None,
        )
        self.books.print_books(rows)

    def menu_missing_tags(self):
        rows = self.books.missing_tags()
        print("[数据质量] 缺少 tags 字段的图书 %d 本" % len(rows))
        self.books.print_books(rows)

    def menu_top_rated(self):
        rows = self.books.top_rated(10)
        print_table("评分最高的 10 本图书", rows,
                    ["title", "author", "rating"],
                    ["书名", "作者", "评分"])

    # ---------------- 统计 ----------------
    def menu_category_stats(self):
        self.stats.print_category()

    def menu_college_top5(self):
        self.stats.print_college_top5()

    def menu_monthly_trend(self):
        self.stats.print_monthly_trend()

    def menu_top_books(self):
        self.stats.print_top_books()

    def menu_save_stats(self):
        self.stats.save_category_stats()

    def menu_export_stats(self):
        self.stats.export_category_stats()

    # ---------------- GridFS ----------------
    def menu_upload(self):
        path = ask("本地文件路径（如 data/gridfs_files/ebook_1.pdf）")
        isbn = ask("关联 ISBN")
        file_type = ask("文件类型（ebook/cover）", "ebook")
        self.gridfs.upload_file(path, isbn, file_type)

    def menu_download(self):
        title = ask("书名关键词（如 Python）")
        self.gridfs.download_by_title(title)

    def menu_list_files(self):
        self.gridfs.print_files()

    # ---------------- 日志 ----------------
    def menu_audit(self):
        rows = audit.recent(100)
        data = [{
            "time": fmt_dt(r.get("time"), "%Y-%m-%d %H:%M:%S"),
            "action": r.get("action", ""),
            "target": r.get("target", ""),
            "detail": r.get("detail", ""),
            "result": r.get("result", ""),
        } for r in rows]
        print_table("最近 100 条操作日志", data,
                    ["time", "action", "target", "detail", "result"],
                    ["时间", "操作", "对象", "详情", "结果"])

    # ---------------- 增删借还 ----------------
    def menu_add_book(self):
        isbn = ask("ISBN")
        if self.books.get_by_isbn(isbn):
            print("[提示] ISBN 已存在。")
            return
        title = ask("书名")
        author = ask("作者")
        publisher = ask("出版社")
        category = ask("类别（计算机/文学/经济管理/数学/外语/历史）")
        price = ask_float("价格", "0")
        rating = ask_float("评分", "0")
        stock = ask("库存", "0")
        raw_tags = ask("标签（逗号分隔）").replace("，", ",").replace("、", ",")
        tags = [x.strip() for x in raw_tags.split(",") if x.strip()]
        publish_date = ask("出版日期（YYYY-MM-DD）")
        floor = ask("馆藏楼层区域", "二楼专业图书区")
        shelf = ask("架位号", "A-01")
        location = {"floor": floor, "shelf": shelf, "copies": int(stock) if str(stock).isdigit() else 0}
        self.books.add_book(isbn, title, author, publisher, category, price or 0,
                            rating or 0, int(stock) if str(stock).isdigit() else 0,
                            tags, publish_date, location)

    def menu_delete_book(self):
        isbn = ask("要删除的图书 ISBN")
        confirm = ask("确认删除？(y/N)", "N")
        if str(confirm).lower() == "y":
            self.books.delete_book(isbn)
        else:
            print("[已取消]")

    def menu_add_reader(self):
        card = ask("借阅证号")
        if self.readers.get(card):
            print("[提示] 借阅证号已存在。")
            return
        name = ask("姓名")
        college = ask("学院")
        email = ask("邮箱（可空）", "")
        phone = ask("电话", "")
        level = ask("等级（普通/高级/教师）", "普通")
        date = ask("注册日期（YYYY-MM-DD）")
        raw_fav = ask("偏好类别（逗号分隔）").replace("，", ",").replace("、", ",")
        fav = [x.strip() for x in raw_fav.split(",") if x.strip()]
        self.readers.add_reader(card, name, college, email, phone, level, date, fav)

    def menu_delete_reader(self):
        card = ask("要删除的借阅证号")
        confirm = ask("确认删除？(y/N)", "N")
        if str(confirm).lower() == "y":
            self.readers.delete_reader(card)
        else:
            print("[已取消]")

    def menu_borrow(self):
        self.borrows.borrow(ask("借阅证号"), ask("图书 ISBN"))

    def menu_return(self):
        self.borrows.return_book(ask("借阅证号"), ask("图书 ISBN"))

    def run(self):
        actions = {
            "1": self.menu_category_price,
            "2": self.menu_tags,
            "3": self.menu_title,
            "4": self.menu_year,
            "5": self.menu_missing_tags,
            "6": self.menu_top_rated,
            "7": self.menu_category_stats,
            "8": self.menu_college_top5,
            "9": self.menu_monthly_trend,
            "10": self.menu_top_books,
            "11": self.menu_save_stats,
            "12": self.menu_export_stats,
            "13": self.menu_upload,
            "14": self.menu_download,
            "15": self.menu_list_files,
            "16": self.menu_audit,
            "17": self.menu_add_book,
            "18": self.menu_delete_book,
            "19": self.menu_borrow,
            "20": self.menu_return,
            "21": self.menu_add_reader,
            "22": self.menu_delete_reader,
        }
        while True:
            print(MENU)
            try:
                choice = input("请选择功能编号（0 退出）：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[退出]")
                break
            if choice in ("0", "q", "Q"):
                print("\n[退出] 正在关闭数据库连接 ...")
                break
            action = actions.get(choice)
            if not action:
                print("[提示] 无效编号。")
                continue
            try:
                action()
            except (EOFError, KeyboardInterrupt):
                print("\n[取消] 已返回主菜单。")
            except PyMongoError as exc:
                print("\n[数据库错误] %s" % exc)
            except Exception as exc:
                print("\n[运行错误] %s: %s" % (type(exc).__name__, exc))


def main():
    print("=" * 60)
    print("  智慧图书馆数字资源平台")
    print("=" * 60)
    print("[连接串] %s" % build_uri())
    ok, message = ping()
    print("[连接状态] %s" % message)
    if not ok:
        close()
        sys.exit(1)

    db = get_db()
    print("\n[数据概况]")
    for label, name in (("图书", "books"), ("读者", "readers"),
                        ("借阅流水", "borrow_logs"), ("分类统计", "category_stats"),
                        ("操作日志", "audit_logs")):
        print("  %-10s %5d 条" % (label, db[name].count_documents({})))
    print("  %-10s %5d 个" % ("GridFS 文件", db["fs.files"].count_documents({})))

    app = Application()
    try:
        app.run()
    finally:
        close()
        print("[完成] 数据库连接已关闭。")


if __name__ == "__main__":
    main()
