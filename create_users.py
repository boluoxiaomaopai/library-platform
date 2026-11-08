
import getpass
import os
import sys

from pymongo.errors import OperationFailure, PyMongoError

from config import MONGO_DB
from db import get_client

PASSWORD = os.getenv("LIB_PASSWORD", "")
CREATE_ROOT = os.getenv("CREATE_ROOT", "0") == "1"


def create_or_update(db, name, password, roles):
    try:
        db.command("createUser", name, pwd=password, roles=roles)
        print("  [已创建] %-12s %s" % (name, roles))
    except OperationFailure as exc:
        if exc.code == 51003 or "already exists" in str(exc):
            db.command("updateUser", name, pwd=password, roles=roles)
            print("  [已更新] %-12s %s" % (name, roles))
        else:
            raise


def main():
    password = PASSWORD
    if not password:
        password = getpass.getpass("请设置三个平台账号的统一密码：")
        confirm = getpass.getpass("请再次输入：")
        if password != confirm:
            print("[错误] 两次密码不一致。")
            sys.exit(1)
    if len(password) < 6:
        print("[错误] 密码至少 6 位。")
        sys.exit(1)

    client = get_client()
    try:
        client.admin.command("ping")
        print("连接成功，开始创建账号：")
        db = client[MONGO_DB]
        create_or_update(db, "lib_reader", password,
                         [{"role": "read", "db": MONGO_DB}])
        create_or_update(db, "lib_writer", password,
                         [{"role": "readWrite", "db": MONGO_DB}])
        create_or_update(db, "lib_admin", password,
                         [{"role": "readWrite", "db": MONGO_DB},
                          {"role": "dbAdmin", "db": MONGO_DB},
                          {"role": "userAdmin", "db": MONGO_DB}])
        if CREATE_ROOT:
            create_or_update(client["admin"], "admin", password,
                             [{"role": "root", "db": "admin"}])

        print("\n连接示例（启用认证后）：")
        print('  mongosh "mongodb://lib_reader:%s@127.0.0.1:27017/%s?authSource=%s"'
              % (password, MONGO_DB, MONGO_DB))
        print('  mongosh "mongodb://lib_writer:%s@127.0.0.1:27017/%s?authSource=%s"'
              % (password, MONGO_DB, MONGO_DB))
        print("\nPython 程序使用读写账号：")
        print("  export MONGO_USERNAME=lib_writer")
        print("  export MONGO_PASSWORD=%s" % password)
    except PyMongoError as exc:
        print("[数据库错误] %s" % exc)
        print("如果已经启用认证，请先在 mongosh 中用管理员账号登录，再执行 createUser。")
        sys.exit(1)


if __name__ == "__main__":
    main()
