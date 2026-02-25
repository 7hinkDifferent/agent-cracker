# group-queue — 组群消息队列

## 目标

复现 NanoClaw 的 GroupQueue：每组独立状态 + 全局并发控制 + 指数退避重试 + 排水机制（task 优先）。

## MVP 角色

GroupQueue 是 Host 层的"交通警察"，决定哪个组群的容器何时启动、何时排队、何时重试。它确保系统不会被过多并发容器压垮，同时保证消息不丢失。

## 原理

```
            enqueue_message_check(jid)
                    │
        ┌───────────┴───────────┐
        │ active?                │ active_count >= MAX?
        │   → pending_messages   │   → waiting queue
        │                        │
        └───────┬────────────────┘
                │ 可以运行
                ▼
        _run_for_group(jid)
            active_count++
            process_messages_fn(jid)
            ┌─────┬─────┐
            │ ok  │ fail│
            │     │     ▼
            │     │ schedule_retry()
            │     │ delay = 5s * 2^(n-1)
            ▼     ▼
        active_count--
        drain_group(jid)
            │
    ┌───────┼───────┐
    │       │       │
    ▼       ▼       ▼
  tasks?  msgs?   drain_waiting()
  (优先)  (其次)  (释放全局槽位)
```

**核心设计**:
- **每组独立状态**: `GroupState` 追踪 active/idle/pending/retry，组间不互相阻塞
- **全局并发上限**: `MAX_CONCURRENT_CONTAINERS = 5`，防止资源耗尽
- **指数退避**: `5s → 10s → 20s → 40s → 80s`，超过 5 次放弃本轮
- **排水优先级**: Task > Message > Waiting Queue（task 不会被 DB 重新发现）
- **管道机制**: `send_message()` 直接写 IPC 文件到活跃容器，避免重启
- **Idle 抢占**: 容器空闲时如有 pending task，立即发 `_close` sentinel

## 运行

```bash
uv run python main.py
```

无外部依赖，纯 Python asyncio。

## 文件结构

```
group-queue/
├── README.md       # 本文件
├── main.py         # Demo 入口（5 个演示场景）
└── queue.py        # 可复用模块: GroupQueue + GroupState + QueuedTask
```

## 关键代码解读

### 全局并发控制（queue.py）

```python
def enqueue_message_check(self, group_jid: str) -> None:
    state = self._get(group_jid)
    if state.active:                                    # 已有容器 → 标记 pending
        state.pending_messages = True
        return
    if self._active_count >= self._max_concurrent:      # 达到上限 → 进入等待队列
        state.pending_messages = True
        self._waiting.append(group_jid)
        return
    asyncio.ensure_future(self._run_for_group(...))     # 有空位 → 立即启动
```

### 指数退避（queue.py）

```python
def _schedule_retry(self, group_jid, state):
    state.retry_count += 1
    if state.retry_count > MAX_RETRIES:     # 超过 5 次 → 放弃
        state.retry_count = 0
        return
    delay_s = (BASE_RETRY_MS * 2 ** (state.retry_count - 1)) / 1000
    # 5s → 10s → 20s → 40s → 80s
    asyncio.ensure_future(_retry_after(delay_s))
```

### 排水机制（queue.py）

```python
async def _drain_group(self, group_jid):
    state = self._get(group_jid)
    if state.pending_tasks:         # 1. Task 最优先
        task = state.pending_tasks.pop(0)
        run_task(task)
    elif state.pending_messages:    # 2. 然后是 Message
        run_for_group("drain")
    else:
        drain_waiting()             # 3. 释放全局槽位给等待队列
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| IPC 管道 | 写 JSON 文件到 `data/ipc/{group}/input/` | 仅返回 True/False（无文件 IO） |
| _close sentinel | 写空文件 `_close` 到 IPC 目录 | 仅发送事件通知 |
| 进程管理 | `ChildProcess` 引用 + `containerName` | 无进程管理（mock 函数） |
| 容器停止 | `docker stop` 命令 | 无 |
| 优雅关闭 | 分离活跃容器（不 kill） | 仅设 `_shutting_down` 标志 |
| 并发数 | 默认 5 | Demo 中用 3 演示（可配置） |
| 重试延迟 | 真实 5s-80s | 真实延迟（demo 只观察调度事件） |

## 相关文档

- 分析文档: [docs/nanoclaw.md — D2 Agent Loop](../../docs/nanoclaw.md#2-agent-loop主循环机制)
- 错误处理: [docs/nanoclaw.md — D6 错误处理](../../docs/nanoclaw.md#6-错误处理与恢复)
- 原始源码: `projects/nanoclaw/src/group-queue.ts` (339 行)
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
