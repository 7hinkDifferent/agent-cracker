"""
NanoClaw SQLite Persistence — Reusable Module

复现 NanoClaw 的 SQLite 持久化层核心机制:
  1. 6 张表 schema (chats/messages/scheduled_tasks/task_run_logs/router_state/sessions/registered_groups)
  2. 增量 ALTER TABLE 迁移 (schema migration)
  3. Bot 消息过滤 (双重过滤: is_bot_message flag + content prefix)
  4. 路由状态 KV 存储 (router_state)
  5. JSON → SQLite 一次性迁移

对应原实现: src/db.ts (664 行)
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Data Models ─────────────────────────────────────────────────

@dataclass
class NewMessage:
    id: str
    chat_jid: str
    sender: str
    sender_name: str
    content: str
    timestamp: str
    is_from_me: bool = False
    is_bot_message: bool = False


@dataclass
class ChatInfo:
    jid: str
    name: str
    last_message_time: str
    channel: Optional[str] = None
    is_group: bool = False


@dataclass
class ScheduledTask:
    id: str
    group_folder: str
    chat_jid: str
    prompt: str
    schedule_type: str
    schedule_value: str
    context_mode: str = "isolated"
    status: str = "active"
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    last_result: Optional[str] = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass
class RegisteredGroup:
    name: str
    folder: str
    trigger: str
    added_at: str
    container_config: Optional[dict] = None
    requires_trigger: bool = True


# ── NanoClawDB ──────────────────────────────────────────────────

ASSISTANT_NAME = "Andy"

# Core schema — 对应 db.ts createSchema()
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chats (
    jid TEXT PRIMARY KEY,
    name TEXT,
    last_message_time TEXT,
    channel TEXT,
    is_group INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT,
    chat_jid TEXT,
    sender TEXT,
    sender_name TEXT,
    content TEXT,
    timestamp TEXT,
    is_from_me INTEGER,
    is_bot_message INTEGER DEFAULT 0,
    PRIMARY KEY (id, chat_jid),
    FOREIGN KEY (chat_jid) REFERENCES chats(jid)
);
CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    group_folder TEXT NOT NULL,
    chat_jid TEXT NOT NULL,
    prompt TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    schedule_value TEXT NOT NULL,
    context_mode TEXT DEFAULT 'isolated',
    next_run TEXT,
    last_run TEXT,
    last_result TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_next_run ON scheduled_tasks(next_run);
CREATE INDEX IF NOT EXISTS idx_status ON scheduled_tasks(status);

CREATE TABLE IF NOT EXISTS task_run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    run_at TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    error TEXT,
    FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id)
);
CREATE INDEX IF NOT EXISTS idx_task_run_logs ON task_run_logs(task_id, run_at);

CREATE TABLE IF NOT EXISTS router_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    group_folder TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS registered_groups (
    jid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    folder TEXT NOT NULL UNIQUE,
    trigger_pattern TEXT NOT NULL,
    added_at TEXT NOT NULL,
    container_config TEXT,
    requires_trigger INTEGER DEFAULT 1
);
"""


class NanoClawDB:
    """
    SQLite 持久化层，对应原实现 db.ts 的全部功能。

    支持文件数据库和内存数据库（:memory:）。
    内存模式用于测试，对应原实现的 _initTestDatabase()。
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self) -> None:
        """创建表结构。对应 db.ts createSchema()。"""
        self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        self._conn.close()

    # ── Migration: ALTER TABLE ──────────────────────────────────

    def run_migrations(self) -> list[str]:
        """
        增量 ALTER TABLE 迁移。对应 db.ts createSchema() 中的 try/catch ALTER。

        原实现模式：用 try { ALTER TABLE } catch { /* column already exists */ }
        这里用 PRAGMA table_info 检测列是否存在，更 Pythonic。
        """
        applied: list[str] = []

        # Migration 1: scheduled_tasks.context_mode
        if not self._column_exists("scheduled_tasks", "context_mode"):
            self._conn.execute(
                "ALTER TABLE scheduled_tasks ADD COLUMN context_mode TEXT DEFAULT 'isolated'"
            )
            applied.append("scheduled_tasks.context_mode")

        # Migration 2: messages.is_bot_message + backfill
        if not self._column_exists("messages", "is_bot_message"):
            self._conn.execute(
                "ALTER TABLE messages ADD COLUMN is_bot_message INTEGER DEFAULT 0"
            )
            self._conn.execute(
                "UPDATE messages SET is_bot_message = 1 WHERE content LIKE ?",
                (f"{ASSISTANT_NAME}:%",),
            )
            applied.append("messages.is_bot_message (with backfill)")

        # Migration 3: chats.channel + chats.is_group + backfill from JID patterns
        if not self._column_exists("chats", "channel"):
            self._conn.execute("ALTER TABLE chats ADD COLUMN channel TEXT")
            self._conn.execute("ALTER TABLE chats ADD COLUMN is_group INTEGER DEFAULT 0")
            self._conn.execute(
                "UPDATE chats SET channel='whatsapp', is_group=1 WHERE jid LIKE '%@g.us'"
            )
            self._conn.execute(
                "UPDATE chats SET channel='whatsapp', is_group=0 WHERE jid LIKE '%@s.whatsapp.net'"
            )
            self._conn.execute(
                "UPDATE chats SET channel='telegram', is_group=1 WHERE jid LIKE 'tg:%'"
            )
            applied.append("chats.channel + chats.is_group (with JID backfill)")

        self._conn.commit()
        return applied

    def _column_exists(self, table: str, column: str) -> bool:
        cursor = self._conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    # ── Chat operations ─────────────────────────────────────────

    def store_chat_metadata(
        self, jid: str, timestamp: str,
        name: str | None = None, channel: str | None = None, is_group: bool | None = None,
    ) -> None:
        """存储/更新 chat 元数据。对应 db.ts storeChatMetadata()。"""
        group_val = None if is_group is None else (1 if is_group else 0)
        display_name = name or jid

        self._conn.execute(
            """INSERT INTO chats (jid, name, last_message_time, channel, is_group)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(jid) DO UPDATE SET
                 name = CASE WHEN ? IS NOT NULL THEN excluded.name ELSE chats.name END,
                 last_message_time = MAX(chats.last_message_time, excluded.last_message_time),
                 channel = COALESCE(excluded.channel, chats.channel),
                 is_group = COALESCE(excluded.is_group, chats.is_group)""",
            (jid, display_name, timestamp, channel, group_val, name),
        )
        self._conn.commit()

    def get_all_chats(self) -> list[ChatInfo]:
        """获取所有 chat，按最近活跃排序。对应 db.ts getAllChats()。"""
        rows = self._conn.execute(
            "SELECT jid, name, last_message_time, channel, is_group FROM chats ORDER BY last_message_time DESC"
        ).fetchall()
        return [ChatInfo(r["jid"], r["name"], r["last_message_time"], r["channel"], bool(r["is_group"])) for r in rows]

    # ── Message operations ──────────────────────────────────────

    def store_message(self, msg: NewMessage) -> None:
        """存储消息。对应 db.ts storeMessage() / storeMessageDirect()。"""
        self._conn.execute(
            """INSERT OR REPLACE INTO messages
               (id, chat_jid, sender, sender_name, content, timestamp, is_from_me, is_bot_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg.id, msg.chat_jid, msg.sender, msg.sender_name,
             msg.content, msg.timestamp, 1 if msg.is_from_me else 0,
             1 if msg.is_bot_message else 0),
        )
        self._conn.commit()

    def get_new_messages(self, jids: list[str], last_timestamp: str) -> tuple[list[NewMessage], str]:
        """
        获取新消息（双重过滤 bot 消息）。对应 db.ts getNewMessages()。

        原实现双重过滤:
          1. is_bot_message = 0 (flag)
          2. content NOT LIKE 'Andy:%' (content prefix backstop)
        """
        if not jids:
            return [], last_timestamp

        placeholders = ",".join("?" for _ in jids)
        rows = self._conn.execute(
            f"""SELECT id, chat_jid, sender, sender_name, content, timestamp
                FROM messages
                WHERE timestamp > ? AND chat_jid IN ({placeholders})
                  AND is_bot_message = 0 AND content NOT LIKE ?
                  AND content != '' AND content IS NOT NULL
                ORDER BY timestamp""",
            [last_timestamp, *jids, f"{ASSISTANT_NAME}:%"],
        ).fetchall()

        messages = [
            NewMessage(r["id"], r["chat_jid"], r["sender"], r["sender_name"],
                       r["content"], r["timestamp"])
            for r in rows
        ]
        new_ts = last_timestamp
        for m in messages:
            if m.timestamp > new_ts:
                new_ts = m.timestamp
        return messages, new_ts

    # ── Router state KV ─────────────────────────────────────────

    def get_router_state(self, key: str) -> str | None:
        """KV 读取。对应 db.ts getRouterState()。"""
        row = self._conn.execute(
            "SELECT value FROM router_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_router_state(self, key: str, value: str) -> None:
        """KV 写入。对应 db.ts setRouterState()。"""
        self._conn.execute(
            "INSERT OR REPLACE INTO router_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    # ── Session management ──────────────────────────────────────

    def get_session(self, group_folder: str) -> str | None:
        """获取组群 session ID。对应 db.ts getSession()。"""
        row = self._conn.execute(
            "SELECT session_id FROM sessions WHERE group_folder = ?", (group_folder,)
        ).fetchone()
        return row["session_id"] if row else None

    def set_session(self, group_folder: str, session_id: str) -> None:
        """设置组群 session ID。对应 db.ts setSession()。"""
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions (group_folder, session_id) VALUES (?, ?)",
            (group_folder, session_id),
        )
        self._conn.commit()

    def get_all_sessions(self) -> dict[str, str]:
        """获取所有 session。对应 db.ts getAllSessions()。"""
        rows = self._conn.execute("SELECT group_folder, session_id FROM sessions").fetchall()
        return {r["group_folder"]: r["session_id"] for r in rows}

    # ── Registered groups ───────────────────────────────────────

    def set_registered_group(self, jid: str, group: RegisteredGroup) -> None:
        """注册群组。对应 db.ts setRegisteredGroup()。"""
        self._conn.execute(
            """INSERT OR REPLACE INTO registered_groups
               (jid, name, folder, trigger_pattern, added_at, container_config, requires_trigger)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (jid, group.name, group.folder, group.trigger, group.added_at,
             json.dumps(group.container_config) if group.container_config else None,
             1 if group.requires_trigger else 0),
        )
        self._conn.commit()

    def get_registered_group(self, jid: str) -> RegisteredGroup | None:
        """查询注册群组。对应 db.ts getRegisteredGroup()。"""
        row = self._conn.execute(
            "SELECT * FROM registered_groups WHERE jid = ?", (jid,)
        ).fetchone()
        if not row:
            return None
        return RegisteredGroup(
            name=row["name"], folder=row["folder"], trigger=row["trigger_pattern"],
            added_at=row["added_at"],
            container_config=json.loads(row["container_config"]) if row["container_config"] else None,
            requires_trigger=bool(row["requires_trigger"]),
        )

    def get_all_registered_groups(self) -> dict[str, RegisteredGroup]:
        """获取所有注册群组。对应 db.ts getAllRegisteredGroups()。"""
        rows = self._conn.execute("SELECT * FROM registered_groups").fetchall()
        result: dict[str, RegisteredGroup] = {}
        for r in rows:
            result[r["jid"]] = RegisteredGroup(
                name=r["name"], folder=r["folder"], trigger=r["trigger_pattern"],
                added_at=r["added_at"],
                container_config=json.loads(r["container_config"]) if r["container_config"] else None,
                requires_trigger=bool(r["requires_trigger"]),
            )
        return result

    # ── Task operations ─────────────────────────────────────────

    def create_task(self, task: ScheduledTask) -> None:
        """创建定时任务。对应 db.ts createTask()。"""
        self._conn.execute(
            """INSERT INTO scheduled_tasks
               (id, group_folder, chat_jid, prompt, schedule_type, schedule_value,
                context_mode, next_run, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.group_folder, task.chat_jid, task.prompt,
             task.schedule_type, task.schedule_value, task.context_mode,
             task.next_run, task.status, task.created_at),
        )
        self._conn.commit()

    def get_due_tasks(self) -> list[ScheduledTask]:
        """获取到期任务。对应 db.ts getDueTasks()。"""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rows = self._conn.execute(
            """SELECT * FROM scheduled_tasks
               WHERE status = 'active' AND next_run IS NOT NULL AND next_run <= ?
               ORDER BY next_run""",
            (now,),
        ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task_after_run(self, task_id: str, next_run: str | None, last_result: str) -> None:
        """运行后更新。对应 db.ts updateTaskAfterRun()。"""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._conn.execute(
            """UPDATE scheduled_tasks
               SET next_run = ?, last_run = ?, last_result = ?,
                   status = CASE WHEN ? IS NULL THEN 'completed' ELSE status END
               WHERE id = ?""",
            (next_run, now, last_result, next_run, task_id),
        )
        self._conn.commit()

    def _row_to_task(self, row: sqlite3.Row) -> ScheduledTask:
        return ScheduledTask(
            id=row["id"], group_folder=row["group_folder"], chat_jid=row["chat_jid"],
            prompt=row["prompt"], schedule_type=row["schedule_type"],
            schedule_value=row["schedule_value"], context_mode=row["context_mode"],
            status=row["status"], next_run=row["next_run"], last_run=row["last_run"],
            last_result=row["last_result"], created_at=row["created_at"],
        )

    # ── JSON Migration ──────────────────────────────────────────

    def migrate_from_json(self, data_dir: str) -> list[str]:
        """
        从 JSON 文件迁移数据。对应 db.ts migrateJsonState()。

        原实现迁移 3 种 JSON 文件:
          1. router_state.json → router_state 表
          2. sessions.json → sessions 表
          3. registered_groups.json → registered_groups 表
        迁移后将原文件重命名为 .migrated。
        """
        migrated: list[str] = []

        # 1. router_state.json
        rs_path = Path(data_dir) / "router_state.json"
        if rs_path.exists():
            try:
                data = json.loads(rs_path.read_text())
                if "last_timestamp" in data:
                    self.set_router_state("last_timestamp", data["last_timestamp"])
                if "last_agent_timestamp" in data:
                    self.set_router_state("last_agent_timestamp", json.dumps(data["last_agent_timestamp"]))
                rs_path.rename(str(rs_path) + ".migrated")
                migrated.append("router_state.json")
            except Exception:
                pass

        # 2. sessions.json
        sess_path = Path(data_dir) / "sessions.json"
        if sess_path.exists():
            try:
                sessions = json.loads(sess_path.read_text())
                for folder, session_id in sessions.items():
                    self.set_session(folder, session_id)
                sess_path.rename(str(sess_path) + ".migrated")
                migrated.append("sessions.json")
            except Exception:
                pass

        # 3. registered_groups.json
        groups_path = Path(data_dir) / "registered_groups.json"
        if groups_path.exists():
            try:
                groups = json.loads(groups_path.read_text())
                for jid, g in groups.items():
                    self.set_registered_group(jid, RegisteredGroup(
                        name=g["name"], folder=g["folder"],
                        trigger=g["trigger"], added_at=g.get("added_at", ""),
                    ))
                groups_path.rename(str(groups_path) + ".migrated")
                migrated.append("registered_groups.json")
            except Exception:
                pass

        return migrated
