"""
database.py 是 IssuePilot M3 的持久化层，使用 SQLite保存：
    Agent任务信息
    任务状态
    最终结果或错误
    每一次工具调用事件
    创建和更新时间
它让任务数据不会因为 HTTP请求结束而消失，也可以在服务重启后继续查询之前的记录。

整体关系：
    API / TaskService
        ↓
    TaskDatabase
        ↓
    SQLite数据库文件
    ├─ tasks表
    └─ events表
两个表的关系：
    tasks
    一条记录代表一个Agent任务
            │
            │ 一个任务可以有多个事件
            ▼
    events
    每条记录代表一次工具调用
"""

# 并发设计
    # M3 可能同时存在
        # HTTP线程查询任务
        # 后台线程写任务状态
        # 后台线程写事件
        # 另一个请求查询事件
    # 当前代码采用
        # 每次操作创建独立连接
        # 30秒锁等待
        # WAL日志模式
        # 每个方法使用短事务
    # 这比多个线程共享一个连接更稳妥。但 SQLite仍然不是高并发大型服务器数据库。同一时刻通常只能有一个写事务。
    # 对于本地工具或小规模服务足够；若需要大量并发任务，可能需要 PostgreSQL等服务器数据库。
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime # 用于生成 UTC时间。
from pathlib import Path
from typing import Any

# 生成UTC时间 返回当前 UTC时间的 ISO 8601字符串。 统一使用UTC后：
    # 不受服务器时区影响
    # 更容易排序
    # 更容易在多个系统间交换
    # 前端可以转换成用户本地时间
def utc_now() -> str:
    return datetime.now(UTC).isoformat() # isoformat:把 datetime 对象转换为标准字符串,数据库中使用 TEXT 保存时间，而不是SQLite专用日期类型。方便排序

# 封装了对 SQLite的全部操作
class TaskDatabase:
    # 初始化数据库对象
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve() # 解析数据库路径
        self.path.parent.mkdir(parents=True, exist_ok=True) # 创建父目录，父目录存在不报错
        self._initialize() # 初始化标，创建数据库表和索引。SQLite文件不存在时，第一次连接会自动创建文件。

    # 创建数据库连接
    def _connect(self) -> sqlite3.Connection: # 每次数据库操作都会创建一个新的连接
        # 连接数据库，如果数据库当前被其他写操作锁住，这个连接最多等待30s
        connection = sqlite3.connect(self.path, timeout=30)
        # 设置行工厂，默认结果是元组
        connection.row_factory = sqlite3.Row
        # 开启WAL模式 预写日志模式 它会让数据库通常具有更好的读写并发能力： 与默认日志模式相比，WAL通常更适合Web服务。
            # 一个线程正在写任务状态
            # +
            # 另一个请求可以查询任务
        # 数据库目录中可能出现： 这是正常现象，不要在服务运行过程中随意删除。
            # issuepilot.db
            # issuepilot.db-wal
            # issuepilot.db-shm
        connection.execute("PRAGMA journal_mode=WAL")
        """
        为什么每次操作创建新连接？
            代码没有长期保存self.connection 而是每次调用self._connect()
            优点：
                不同线程不会共享同一个SQLite连接
                减少跨线程连接错误
                每次操作边界清晰
                with 块结束后事务会提交或回滚
            适合 TaskService 使用线程执行Agent任务
            需要注意：sqlite3.Connection 的上下文管理器主要管理事务；连接对象生命周期结束后最终会被释放。若要求非常严格的即时关闭，可以额外显式关闭连接。
        """
        return connection

    # 建表 创建 TaskDatabase 时自动执行。
    def _initialize(self) -> None:
        # with 的事务行为 正常结束->提交事务  发生异常->回滚事务 
        # executescript()：允许一次执行多条SQL语句。
            # 创建 tasks 表
            # 创建 events 表
            # 创建索引
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    max_steps INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    step INTEGER NOT NULL,
                    tool TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_task_id ON events(task_id, id);
                """
            )

    # 创建任务
    def create_task(self, task_id: str, repository: str, prompt: str, max_steps: int) -> None:
        # 生成时间 
        timestamp = utc_now() 
        # 插入任务 ?->参数占位符
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks(id, repository, prompt, max_steps, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """, 
                (task_id, repository, prompt, max_steps, timestamp, timestamp),
            )

    # 更新状态
    def set_status(
        self,
        task_id: str,
        status: str,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as connection:
            # 更新 每次调用都会同时覆盖 result error
            connection.execute(
                "UPDATE tasks SET status=?, result=?, error=?, updated_at=? WHERE id=?",
                (status, result, error, utc_now(), task_id),
            )

    # 保存工具事件
    def add_event(self, task_id: str, event: dict[str, Any]) -> None:
        # 插入事件
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO events(task_id, step, tool, arguments_json, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    event["step"],
                    event["tool"],
                    json.dumps(event["arguments"], ensure_ascii=False), # 序列化参数
                    json.dumps(event["result"], ensure_ascii=False), # 序列化结果
                    utc_now(),
                ),
            )

    # 查询一个任务
    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    # 查询事件
    def get_events(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,)
            ).fetchall() # 取出所有匹配记录
        return [
            {
                "id": row["id"],
                "task_id": row["task_id"],
                "step": row["step"],
                "tool": row["tool"],
                "arguments": json.loads(row["arguments_json"]),
                "result": json.loads(row["result_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # 处理服务重启 把数据库中仍处于pending/running 的任务标记为失败 服务重启时，之前尚未完成的任务已经中断，因此不能继续显示为等待中或运行中。
    def interrupt_running_tasks(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status='failed', error='Service restarted while task was running', updated_at=?
                WHERE status IN ('pending', 'running')
                """,
                (utc_now(),),
            )

