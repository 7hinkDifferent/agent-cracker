"""
NanoClaw SQLite Persistence — 机制 Demo

复现 NanoClaw 的 SQLite 持久化层核心机制:
  1. Schema 创建 (7 张表 + 索引)
  2. 增量 ALTER TABLE 迁移
  3. 消息存储 + Bot 消息双重过滤
  4. Router state KV 存储 + Session 管理
  5. JSON → SQLite 一次性迁移
  6. 注册群组 CRUD

基于 src/db.ts (664 行)

运行: uv run python main.py
"""

import json
import os
import tempfile
import time

from persistence import (
    NanoClawDB, NewMessage, ScheduledTask, RegisteredGroup, ChatInfo,
)


def demo_schema_creation():
    print("=" * 60)
    print("Demo 1: Schema 创建 — 7 张表 + 索引")
    print("=" * 60)

    db = NanoClawDB(":memory:")

    # Query all tables
    tables = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t["name"] for t in tables]

    print(f"\n  创建的表 ({len(table_names)}):")
    for name in table_names:
        # Count columns
        cols = db._conn.execute(f"PRAGMA table_info({name})").fetchall()
        col_names = [c[1] for c in cols]
        print(f"    {name:25s} ({len(cols)} 列): {', '.join(col_names)}")

    # Query all indexes
    indexes = db._conn.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    print(f"\n  索引 ({len(indexes)}):")
    for idx in indexes:
        print(f"    {idx['name']:30s} → {idx['tbl_name']}")

    db.close()
    print()


def demo_migration():
    print("=" * 60)
    print("Demo 2: 增量 ALTER TABLE 迁移")
    print("=" * 60)

    # Simulate an old schema (without newer columns)
    import sqlite3
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    # Create minimal old schema (before migrations)
    conn.executescript("""
        CREATE TABLE chats (jid TEXT PRIMARY KEY, name TEXT, last_message_time TEXT);
        CREATE TABLE messages (id TEXT, chat_jid TEXT, sender TEXT, sender_name TEXT,
            content TEXT, timestamp TEXT, is_from_me INTEGER, PRIMARY KEY (id, chat_jid));
        CREATE TABLE scheduled_tasks (id TEXT PRIMARY KEY, group_folder TEXT NOT NULL,
            chat_jid TEXT NOT NULL, prompt TEXT NOT NULL, schedule_type TEXT NOT NULL,
            schedule_value TEXT NOT NULL, next_run TEXT, last_run TEXT, last_result TEXT,
            status TEXT DEFAULT 'active', created_at TEXT NOT NULL);
        CREATE TABLE router_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE sessions (group_folder TEXT PRIMARY KEY, session_id TEXT NOT NULL);
        CREATE TABLE registered_groups (jid TEXT PRIMARY KEY, name TEXT NOT NULL,
            folder TEXT NOT NULL UNIQUE, trigger_pattern TEXT NOT NULL, added_at TEXT NOT NULL,
            container_config TEXT, requires_trigger INTEGER DEFAULT 1);
    """)
    # Insert some old-format data for backfill demo
    conn.execute("INSERT INTO chats VALUES ('team@g.us', 'Team', '2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO chats VALUES ('tg:group:123', 'TG Group', '2026-01-02T00:00:00Z')")
    conn.execute(
        "INSERT INTO messages VALUES ('m1', 'team@g.us', 's1', 'User', 'Andy: 已处理', '2026-01-01T00:00:00Z', 0)"
    )
    conn.execute(
        "INSERT INTO messages VALUES ('m2', 'team@g.us', 's2', 'User', '普通消息', '2026-01-01T00:01:00Z', 0)"
    )
    conn.commit()
    conn.close()

    print(f"\n  旧数据库: {tmp}")
    print("  旧 schema: chats 缺少 channel/is_group, messages 缺少 is_bot_message, tasks 缺少 context_mode")

    # Open with NanoClawDB (will NOT auto-migrate, schema already exists)
    # We need to call run_migrations explicitly
    db = NanoClawDB(tmp)
    applied = db.run_migrations()

    print(f"\n  迁移应用: {len(applied)} 项")
    for m in applied:
        print(f"    ✓ {m}")

    # Verify backfill
    chats = db.get_all_chats()
    print("\n  Backfill 验证:")
    for chat in chats:
        print(f"    {chat.jid:20s} → channel={chat.channel}, is_group={chat.is_group}")

    # Verify bot message backfill
    rows = db._conn.execute(
        "SELECT id, content, is_bot_message FROM messages"
    ).fetchall()
    print("\n  Bot 消息 backfill:")
    for r in rows:
        print(f"    {r['id']}: \"{r['content'][:30]}\" → is_bot_message={r['is_bot_message']}")

    db.close()
    os.unlink(tmp)
    print()


def demo_message_filtering():
    print("=" * 60)
    print("Demo 3: 消息存储 + Bot 消息双重过滤")
    print("=" * 60)

    db = NanoClawDB(":memory:")

    # Store chat first
    db.store_chat_metadata("team@g.us", "2026-01-01T00:00:00Z", "Team Chat", "whatsapp", True)

    # Store messages
    messages = [
        NewMessage("m1", "team@g.us", "u1", "Alice", "大家好", "2026-01-01T10:00:00Z"),
        NewMessage("m2", "team@g.us", "u2", "Bob", "帮我查天气", "2026-01-01T10:01:00Z"),
        NewMessage("m3", "team@g.us", "bot", "Andy", "Andy: 北京 25°C", "2026-01-01T10:02:00Z", is_bot_message=True),
        NewMessage("m4", "team@g.us", "u1", "Alice", "谢谢!", "2026-01-01T10:03:00Z"),
        NewMessage("m5", "team@g.us", "bot", "Andy", "", "2026-01-01T10:04:00Z"),  # empty
    ]
    for msg in messages:
        db.store_message(msg)

    print(f"\n  存储 {len(messages)} 条消息 (含 1 条 bot, 1 条空)")

    # Query with bot filtering
    result, new_ts = db.get_new_messages(["team@g.us"], "2026-01-01T00:00:00Z")

    print(f"\n  双重过滤查询结果 ({len(result)} 条):")
    for m in result:
        print(f"    [{m.id}] {m.sender_name}: {m.content}")

    print(f"\n  过滤规则:")
    print(f"    1. is_bot_message = 0          → 排除 flag 标记的 bot 消息")
    print(f"    2. content NOT LIKE 'Andy:%'   → backstop: 排除旧格式 bot 消息")
    print(f"    3. content != '' AND NOT NULL   → 排除空消息")
    print(f"  新 timestamp: {new_ts}")

    db.close()
    print()


def demo_router_state():
    print("=" * 60)
    print("Demo 4: Router State KV + Session 管理")
    print("=" * 60)

    db = NanoClawDB(":memory:")

    # Router state — 轮询游标存储
    db.set_router_state("last_timestamp", "2026-01-01T10:00:00Z")
    db.set_router_state("last_agent_timestamp", json.dumps({
        "main": "2026-01-01T10:00:00Z",
        "team": "2026-01-01T09:55:00Z",
    }))

    print("\n  Router State (KV 存储):")
    print(f"    last_timestamp = {db.get_router_state('last_timestamp')}")
    agent_ts = json.loads(db.get_router_state("last_agent_timestamp") or "{}")
    print(f"    last_agent_timestamp = {json.dumps(agent_ts, indent=6)}")
    print(f"    unknown_key = {db.get_router_state('nonexistent')}")

    # Session management
    db.set_session("main", "sess-abc123")
    db.set_session("team", "sess-def456")
    db.set_session("family", "sess-ghi789")

    print(f"\n  Session 管理:")
    print(f"    main → {db.get_session('main')}")
    print(f"    team → {db.get_session('team')}")
    all_sessions = db.get_all_sessions()
    print(f"    all sessions ({len(all_sessions)}): {all_sessions}")

    # Update session (agent restart → new session)
    db.set_session("main", "sess-new-xyz")
    print(f"\n  Session 更新 (agent restart):")
    print(f"    main → {db.get_session('main')}  (UPSERT)")

    db.close()
    print()


def demo_json_migration():
    print("=" * 60)
    print("Demo 5: JSON → SQLite 一次性迁移")
    print("=" * 60)

    tmpdir = tempfile.mkdtemp(prefix="nanoclaw-migration-")

    # Create legacy JSON files
    json_files = {
        "router_state.json": {
            "last_timestamp": "2026-01-01T08:00:00Z",
            "last_agent_timestamp": {"main": "2026-01-01T08:00:00Z"},
        },
        "sessions.json": {
            "main": "sess-legacy-main",
            "team": "sess-legacy-team",
        },
        "registered_groups.json": {
            "120363xxxx@g.us": {
                "name": "Main Group",
                "folder": "main",
                "trigger": "@Andy",
                "added_at": "2026-01-01T00:00:00Z",
            },
        },
    }
    for filename, data in json_files.items():
        with open(os.path.join(tmpdir, filename), "w") as f:
            json.dump(data, f, indent=2)

    print(f"\n  Legacy JSON 文件:")
    for name in json_files:
        print(f"    {name}")

    db = NanoClawDB(":memory:")
    migrated = db.migrate_from_json(tmpdir)

    print(f"\n  迁移结果: {len(migrated)} 个文件")
    for m in migrated:
        print(f"    ✓ {m}")

    # Verify migrated data
    print(f"\n  验证迁移数据:")
    print(f"    router_state.last_timestamp = {db.get_router_state('last_timestamp')}")
    print(f"    sessions = {db.get_all_sessions()}")
    groups = db.get_all_registered_groups()
    for jid, g in groups.items():
        print(f"    group: {jid} → {g.name} (folder={g.folder}, trigger={g.trigger})")

    # Check .migrated files
    remaining = [f for f in os.listdir(tmpdir) if not f.endswith(".migrated")]
    migrated_files = [f for f in os.listdir(tmpdir) if f.endswith(".migrated")]
    print(f"\n  文件重命名:")
    print(f"    .migrated 文件: {migrated_files}")
    print(f"    未迁移文件: {remaining or '(无)'}")

    db.close()
    import shutil
    shutil.rmtree(tmpdir)
    print()


def demo_registered_groups():
    print("=" * 60)
    print("Demo 6: 注册群组 CRUD + container_config")
    print("=" * 60)

    db = NanoClawDB(":memory:")

    # Register groups
    db.set_registered_group("120363xxxx@g.us", RegisteredGroup(
        name="Main Group", folder="main", trigger="@Andy",
        added_at="2026-01-01T00:00:00Z",
        container_config={"memory": "512m", "timeout": 300},
        requires_trigger=False,
    ))
    db.set_registered_group("120363yyyy@g.us", RegisteredGroup(
        name="Team Group", folder="team", trigger="@Andy",
        added_at="2026-01-02T00:00:00Z",
    ))

    print("\n  注册 2 个群组:")
    groups = db.get_all_registered_groups()
    for jid, g in groups.items():
        config_str = json.dumps(g.container_config) if g.container_config else "null"
        print(f"    {jid}")
        print(f"      name={g.name}, folder={g.folder}, trigger={g.trigger}")
        print(f"      requires_trigger={g.requires_trigger}, config={config_str}")

    # Query single group
    main = db.get_registered_group("120363xxxx@g.us")
    unknown = db.get_registered_group("nonexistent@g.us")
    print(f"\n  查询:")
    print(f"    120363xxxx@g.us → {main.name if main else None}")
    print(f"    nonexistent → {unknown}")

    # Update group (UPSERT)
    db.set_registered_group("120363xxxx@g.us", RegisteredGroup(
        name="Main Group (Updated)", folder="main", trigger="@Bot",
        added_at="2026-01-01T00:00:00Z",
    ))
    updated = db.get_registered_group("120363xxxx@g.us")
    print(f"\n  UPSERT 更新:")
    print(f"    name → {updated.name}")
    print(f"    trigger → {updated.trigger}")
    print(f"    config → {updated.container_config}  (UPSERT 覆盖了旧的 config)")

    db.close()
    print()


def main():
    print("NanoClaw SQLite Persistence — 机制 Demo\n")
    demo_schema_creation()
    demo_migration()
    demo_message_filtering()
    demo_router_state()
    demo_json_migration()
    demo_registered_groups()
    print("✓ 所有 demo 完成")


if __name__ == "__main__":
    main()
