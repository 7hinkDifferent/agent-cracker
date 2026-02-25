# cursor-rollback — 消息游标推进与失败回滚

## 目标

复现 NanoClaw 的双游标消息投递系统：全局游标（已读水位）+ 每组游标（已处理水位），实现 at-least-once delivery 语义。

## MVP 角色

Cursor Rollback 是消息可靠投递的核心保障。它确保 agent 处理失败时消息不会丢失，而是在下次轮询时自动重新投递。

## 原理

```
消息 DB                    全局游标              组群游标
  │                        (lastTimestamp)     (lastAgentTimestamp[group])
  │                           │                    │
  │  Poll 轮询                │                    │
  │◄──────────────────────────│                    │
  │  返回 timestamp > cursor  │                    │
  │  的所有新消息              │                    │
  │──────────────────────────►│                    │
  │                     立即推进                    │
  │                  (不等 agent)                   │
  │                           │                    │
  │  Agent 处理               │                    │
  │                           │        ┌───────────┤
  │                           │        │ 乐观推进   │
  │                           │        │ (保存旧值) │
  │                           │        └───────────┤
  │                           │                    │
  │                           │   ┌── 成功? ──┐    │
  │                           │   │           │    │
  │                           │  YES         NO    │
  │                           │   │           │    │
  │                           │   │      回滚到旧值 │
  │                           │   │           │    │
  │                           │   ▼           ▼    │
  │                           │  游标停在     游标回到│
  │                           │  新位置      旧位置  │
  │                           │                    │
  │  下次 Poll                │                    │
  │  全局: 无新消息            │                    │
  │  组群: 失败的消息          │  ← 重新投递!       │
  │       重新出现             │                    │
```

**失败回滚场景详解**:

```
时间线:
  T1: 消息 m1, m2 到达 group-A
  T2: Poll 读取 → global_cursor = T1 (立即推进)
  T3: Agent 开始处理 m1, m2
      → 乐观推进 group_cursor["group-A"] = T1
      → 保存 previous_cursor = ""
  T4: Agent 失败!
      → 检查: 是否已发送输出给用户?
      → NO  → group_cursor["group-A"] = previous_cursor ("")  (回滚)
      → YES → 不回滚 (防止用户看到重复消息)
  T5: 下次 Poll
      → get_new_messages: 无新消息 (global_cursor 已在 T1)
      → 但 recoverPendingMessages / enqueueMessageCheck 发现:
         getMessagesSince(group-A, "") 返回 m1, m2
      → 重新投递!
```

**部分输出保护**: 若 agent 已经向用户发送了部分结果（`outputSentToUser = true`），即使后续执行失败也不回滚游标。原因是回滚会导致消息被重新处理，用户收到重复输出。

## 运行

```bash
uv run python main.py
```

无外部依赖。

## 文件结构

```
cursor-rollback/
├── README.md      # 本文件
├── main.py        # Demo 入口（5 个演示场景）
└── cursor.py      # 可复用模块: CursorManager (双游标 + 状态持久化)
```

## 关键代码解读

### 双游标分离（cursor.py）

```python
class CursorManager:
    def __init__(self):
        self.global_cursor: str = ""          # lastTimestamp
        self.group_cursors: dict[str, str] = {}  # lastAgentTimestamp

    def advance_global(self, new_ts):
        # 读取后立即推进，不等 agent
        self.global_cursor = new_ts

    def advance_group(self, group, new_ts):
        # 仅在 agent 成功后推进
        self.group_cursors[group] = new_ts

    def rollback_group(self, group, previous_cursor):
        # 失败时回滚到之前的位置
        self.group_cursors[group] = previous_cursor
```

全局游标和组群游标分离是实现 at-least-once 的关键：全局游标保证不重复读取，组群游标保证失败消息被重新投递。

### 乐观推进 + 回滚（原实现模式）

```typescript
// src/index.ts:processGroupMessages (line 160-224)
const previousCursor = lastAgentTimestamp[chatJid] || '';
lastAgentTimestamp[chatJid] = missedMessages[...].timestamp;  // 乐观推进
saveState();

// ... agent 执行 ...

if (output === 'error' || hadError) {
    if (outputSentToUser) {
        // 已发送输出，不回滚（防止重复）
        return true;
    }
    lastAgentTimestamp[chatJid] = previousCursor;  // 回滚
    saveState();
    return false;
}
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 存储 | SQLite `router_state` 表 | Python dict + JSON 序列化 |
| 消息源 | SQLite `messages` 表 + SQL 查询 | 内存列表 + 列表过滤 |
| 时间戳比较 | SQL `WHERE timestamp > ?` | Python 字符串比较 (ISO 8601 可直接比较) |
| 部分输出保护 | `outputSentToUser` flag | 未实现（概念在 README 说明） |
| 恢复扫描 | `recoverPendingMessages()` 启动时扫描 | Demo 4 模拟 |
| 并发控制 | `GroupQueue` 串行化处理 | 同步执行模拟 |
| IPC 管道路径 | `queue.sendMessage()` 管道到活跃容器 | 未实现 |

## 相关文档

- 分析文档: [docs/nanoclaw.md — D2 Agent Loop](../../docs/nanoclaw.md#2-agent-loop主循环机制)
- 错误恢复: [docs/nanoclaw.md — D6 错误处理](../../docs/nanoclaw.md#6-错误处理与恢复)
- 原始源码: `projects/nanoclaw/src/index.ts` (498 行，startMessageLoop + processGroupMessages)
- 数据库层: `projects/nanoclaw/src/db.ts` (663 行，getNewMessages + getMessagesSince + getRouterState/setRouterState)
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
