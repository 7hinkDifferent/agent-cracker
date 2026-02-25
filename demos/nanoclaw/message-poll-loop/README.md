# message-poll-loop — 消息轮询主循环

## 目标

复现 NanoClaw Host 层的核心编排逻辑：轮询注册组群的新消息 → 触发词过滤 → 消息累积 → 管道到活跃容器或入队等待新容器。

## MVP 角色

这是 NanoClaw 双层架构中 Host 层的心脏。所有消息从通道进入后，由此循环决定"何时、为谁、启动/复用哪个容器"。

## 原理

NanoClaw 的消息处理采用**双游标 + 轮询**模式：

```
              2s 轮询
                │
    ┌───────────▼───────────┐
    │  从 DB 拉新消息          │  ← getNewMessages(jids, lastTimestamp)
    │  (全局游标: lastTimestamp)│
    └───────────┬───────────┘
                │
    ┌───────────▼───────────┐
    │  按 chat_jid 分组       │
    └───────────┬───────────┘
                │
    ┌───────────▼───────────┐
    │  触发词检查              │  ← 非 main 群需要 @Andy
    │  无触发 → 累积在 DB      │
    └───────────┬───────────┘
                │ 有触发
    ┌───────────▼───────────┐
    │  拉取累积消息             │  ← getMessagesSince(jid, lastAgentTimestamp)
    │  + 格式化为 XML          │
    └───────────┬───────────┘
                │
        ┌───────┴───────┐
        ▼               ▼
   活跃容器？        无活跃容器
   send_message()    enqueue()
   (IPC 管道)       (等待新容器)
```

**关键设计决策**:
- **双游标**: `lastTimestamp`（全局已读水位）和 `lastAgentTimestamp[jid]`（每组处理水位），确保消息不遗漏
- **消息累积**: 非触发消息不被丢弃，而是在 DB 中累积，等触发词到达时一次性拉取作为上下文
- **管道优先**: 如果组群已有活跃容器，通过 IPC 文件管道消息，避免重启容器
- **启动恢复**: `recoverPendingMessages()` 在进程重启时扫描未处理消息

## 运行

```bash
uv run python main.py
```

无外部依赖，纯 Python 标准库。

## 文件结构

```
message-poll-loop/
├── README.md       # 本文件
├── main.py         # Demo 入口（5 个演示场景）
└── loop.py         # 可复用模块: MessagePollLoop + MessageStore + format_messages
```

## 关键代码解读

### 双游标机制（loop.py）

```python
# 全局游标: 推进到最新消息
self.last_timestamp = new_ts

# 每组游标: 仅在成功管道/入队后推进
if self.queue.send_message(chat_jid, formatted):
    self.last_agent_timestamp[chat_jid] = to_send[-1].timestamp
```

全局游标立即推进（标记"已看到"），每组游标只在确认处理后推进。这是 at-least-once 语义的基础。

### 触发词过滤 + 累积（loop.py）

```python
if needs_trigger:
    has_trigger = any(self.trigger_pattern.search(m.content) for m in group_msgs)
    if not has_trigger:
        continue  # 消息留在 DB 中累积

# 拉取自上次处理后的全部消息（包括非触发消息）
all_pending = self.store.get_messages_since(chat_jid, ...)
```

非触发消息不被丢弃，而是在 DB 中"沉默累积"，等下一次触发时作为上下文一起发送。

### XML 消息格式（loop.py）

```python
def format_messages(messages: list[Message]) -> str:
    lines = ["<messages>"]
    for m in messages:
        lines.append(f'<message sender="{m.sender_name}" time="{m.timestamp}">{escaped}</message>')
    lines.append("</messages>")
```

XML 格式让 LLM 能清晰区分多条消息的发送者和时间。

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 消息存储 | SQLite (`db.ts`) | 内存 `MessageStore` |
| 游标持久化 | SQLite `router_state` 表 | 内存 dict |
| 通道 | WhatsApp (`channels/whatsapp.ts`) | 无（直接操作 store） |
| 容器调度 | `GroupQueue` + Docker 容器 | Mock `GroupQueue` |
| 消息格式 | `router.ts:formatMessages` | 等价的 Python 实现 |
| XML 转义 | 手写 `escapeXml` | `xml.sax.saxutils.escape` |
| 日志 | pino 结构化日志 | print |

## 相关文档

- 分析文档: [docs/nanoclaw.md — D2 Agent Loop](../../docs/nanoclaw.md#2-agent-loop主循环机制)
- 原始源码: `projects/nanoclaw/src/index.ts` (line 309-397, `startMessageLoop`)
- 消息格式: `projects/nanoclaw/src/router.ts` (line 1-44, `formatMessages`)
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
