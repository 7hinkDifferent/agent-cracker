# sqlite-persistence — SQLite 持久化层

## 目标

复现 NanoClaw 的 SQLite 持久化层核心机制：7 张表 schema + 增量 ALTER TABLE 迁移 + Bot 消息双重过滤 + KV 存储 + JSON 迁移。

## 平台机制角色

SQLite 是 NanoClaw 的**持久化心脏**。所有跨重启状态——消息历史、轮询游标、session ID、注册群组、定时任务——都存储在单一 `messages.db` 文件中。Host Orchestrator 通过 db 层读写数据，容器内 Agent 无法直接访问。

## 原理

```
Host Orchestrator
  │
  ├── storeChatMetadata()      → chats 表 (元数据)
  ├── storeMessage()           → messages 表 (全文消息)
  ├── getNewMessages()         → 双重 bot 过滤 + 时间戳游标
  │     └── WHERE is_bot_message=0 AND content NOT LIKE 'Andy:%'
  │
  ├── get/setRouterState()     → router_state 表 (KV 存储)
  │     └── last_timestamp, last_agent_timestamp
  │
  ├── get/setSession()         → sessions 表 (group→session)
  ├── get/setRegisteredGroup() → registered_groups 表
  └── createTask/getDueTasks() → scheduled_tasks + task_run_logs 表

初始化流程:
  1. createSchema()      → CREATE TABLE IF NOT EXISTS (7 张)
  2. ALTER TABLE 迁移    → try/catch 添加新列 + backfill
  3. migrateJsonState()  → JSON 文件 → SQLite + .migrated 重命名
```

**增量迁移**: 原实现用 `try { ALTER TABLE } catch { /* exists */ }` 模式，每次启动都安全运行。
**Bot 双重过滤**: `is_bot_message` flag + `content NOT LIKE 'Andy:%'` backstop，兼容迁移前的旧消息。

## 运行

```bash
uv run python main.py
```

无外部依赖（使用 Python 内置 `sqlite3`）。

## 文件结构

```
sqlite-persistence/
├── README.md          # 本文件
├── persistence.py     # 可复用模块: NanoClawDB + 7 表 CRUD + 迁移
└── main.py            # Demo: 6 个演示场景
```

## 关键代码解读

### 双重 Bot 消息过滤

```python
# 对应 db.ts getNewMessages() — 双重过滤确保 bot 消息不被轮询
rows = conn.execute("""
    SELECT * FROM messages
    WHERE timestamp > ? AND chat_jid IN (...)
      AND is_bot_message = 0        -- Flag 过滤
      AND content NOT LIKE 'Andy:%'  -- Content backstop (兼容旧数据)
      AND content != '' AND content IS NOT NULL
    ORDER BY timestamp
""", params)
```

### 增量 ALTER TABLE 迁移

```python
# 对应 db.ts createSchema() 中的 try/catch ALTER 模式
def run_migrations(self):
    if not self._column_exists("chats", "channel"):
        conn.execute("ALTER TABLE chats ADD COLUMN channel TEXT")
        # Backfill from JID patterns
        conn.execute("UPDATE chats SET channel='whatsapp' WHERE jid LIKE '%@g.us'")
        conn.execute("UPDATE chats SET channel='telegram' WHERE jid LIKE 'tg:%'")
```

### JSON → SQLite 一次性迁移

```python
# 对应 db.ts migrateJsonState() — 读取 → 写入 SQLite → 重命名 .migrated
path = Path(data_dir) / "router_state.json"
data = json.loads(path.read_text())
db.set_router_state("last_timestamp", data["last_timestamp"])
path.rename(str(path) + ".migrated")  # 标记已迁移
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| SQLite 库 | `better-sqlite3` (同步) | Python 内置 `sqlite3` |
| WAL 模式 | 未显式设置 | `PRAGMA journal_mode=WAL` |
| 迁移检测 | try { ALTER } catch | `PRAGMA table_info` 检测列 |
| 输入校验 | `isValidGroupFolder()` | 未实现（简化） |
| 日志 | pino logger | 无日志 |
| 事务 | 隐式（同步 API） | 显式 `conn.commit()` |

## 相关文档

- 分析文档: [docs/nanoclaw.md — D10 记忆与持久化](../../docs/nanoclaw.md#10-记忆与持久化平台维度)
- 原始源码: `projects/nanoclaw/src/db.ts` (664 行)
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
