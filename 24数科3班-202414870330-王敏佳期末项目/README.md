# 智慧图书馆数字资源平台



项目在单机 MongoDB 上完成馆藏、读者、借阅流水、统计、GridFS 电子书存储和 Python 菜单程序，并进一步部署三节点副本集与两分片分片集群，验证高可用和水平扩展。

## 一、目录结构

```
smart_library/
├── data/                    配套数据（50 本书、30 位读者、3000 条流水、6 个 GridFS 文件）
│   └── gridfs_files/        ebook_1~3.pdf、cover_1~3.png、files_manifest.txt
├── config.py                连接参数、TTL、路径
├── db.py                    统一 MongoDB 连接模块
├── utils.py                 日期与表格工具
├── audit.py                 audit_logs 操作日志
├── book_manager.py          图书检索、排行、增删
├── reader_manager.py        读者管理
├── borrow_manager.py        借阅、归还、逾期
├── stat_manager.py          分类统计、学院 Top5、月度趋势、热门图书、统计落库/导出
├── gridfs_manager.py        GridFS 上传、下载、字节校验、清单
├── main.py                  菜单式主程序（22 项）
├── init_db.py               建库、建集合、导入、索引、GridFS 初始化
├── create_users.py          只读/读写/管理账号
├── requirements.txt         Python 依赖
└── docs/                    项目文档
```

## 二、环境要求

| 软件 | 版本 |
|---|---|
| MongoDB Server | 本机验证 8.3.11|
| mongosh | 2.x |
| Python | 3.9 及以上 |
| pymongo | 4.x（含 gridfs） |
| Compass | 1.40 及以上 |
| Xshell | SSH 远程连接 Linux 虚拟机 |

## 三、快速开始（单机）

```bash
cd smart_library
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 启动 MongoDB（自定义数据目录，27017）
mongod --dbpath /data/smart_library/standalone/data --port 27017 \
       --bind_ip 0.0.0.0 --logpath /data/smart_library/standalone/mongod.log \
       --logappend --fork

# 初始化：建库、建集合、导入 50/30/3000、创建索引、上传 6 个文件
python3 init_db.py --reset

# 自检
python3 db.py

# 运行菜单程序
python3 main.py
```

## 四、连接配置

所有参数从环境变量读取，不写死地址、账号和密码：

```bash
export MONGO_HOST=127.0.0.1
export MONGO_PORT=27017
export MONGO_DB=smart_library
export MONGO_USERNAME=lib_writer      # 启用认证后
export MONGO_PASSWORD=你的密码
export MONGO_AUTH_SOURCE=smart_library
export MONGO_REPLICA_SET=rs0          # 连接副本集时
export MONGO_READ_PREFERENCE=secondaryPreferred
```

## 五、borrow_logs 的两种模式

- 单机/副本集：`python3 init_db.py`，`borrow_logs` 为**时间序列集合**，`timeField=borrow_date`，`granularity=hours`，`expireAfterSeconds=157680000`（5 年）；
- 分片集群：`python3 init_db.py --mode sharded`，`borrow_logs` 为**普通集合 + borrow_date TTL 索引**，因为 MongoDB 的时间序列集合不支持分片，任务六必须用普通集合。

两种模式字段完全一致，程序查询、统计代码不需要修改；归还逻辑统一为“删除原借出流水 + 插入已归还流水”。

## 六、任务对应

| 任务 | 实现 |
|---|---|
| 一 技术选型 | docs/项目文档 第2章 |
| 二 数据建模 | config、init_db、docs/项目文档 第3章 |
| 三 单机实现 | init_db.py、book/reader/borrow/stat_manager、create_users.py |
| 四 应用与文件存储 | main.py、gridfs_manager.py、audit.py |
| 五 副本集 | 项目文档第 6 章 |
| 六 分片集群 | 项目文档第 6 章 |
| 七 验收 | docs/项目文档 |

