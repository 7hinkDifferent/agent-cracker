# mini-nanoclaw — 串联 6 个组件的最小完整 WhatsApp Agent

## 目标

组合 MVP + 平台组件的最小完整 NanoClaw，验证端到端消息处理链路。

## 组件引用

通过 `sys.path` 导入兄弟 demo 的可复用模块：

| # | 组件 | 来源 | 导入 |
|---|------|------|------|
| 1 | Channel 通道 | `channel-abstraction/channel.py` | `WhatsAppChannel`, `route_outbound` |
| 2 | SQLite 持久化 | `sqlite-persistence/persistence.py` | `NanoClawDB`, `NewMessage` |
| 3 | 消息轮询 | `message-poll-loop/loop.py` | `MessagePollLoop`, `MessageStore` |
| 4 | 并发队列 | `group-queue/queue.py` | `GroupQueue` |
| 5 | 容器启动 | `container-spawn/spawner.py` | `ContainerInput`, `ContainerOutput` |
| 6 | 定时调度 | `task-scheduler/scheduler.py` | `TaskStore`, `SchedulerLoop` |

## 原理

```
WhatsApp Channel
  │ simulate_inbound()
  ▼
MiniNanoClaw._on_inbound()
  │ 1. store → NanoClawDB (持久化)
  │ 2. store → MessageStore (轮询用)
  ▼
MessagePollLoop._poll_once()
  │ 1. 从 MessageStore 拉取新消息
  │ 2. 按 chat_jid 分组
  │ 3. 触发词检查 (非 main 群需要 @Andy)
  │ 4. 调用 GroupQueue
  ▼
GroupQueue._run_for_group()
  │ 并发控制 (max_concurrent)
  ▼
MiniNanoClaw._process_group()
  │ 1. 从 DB 读取待处理消息 (含游标)
  │ 2. 构造 ContainerInput
  │ 3. Mock 容器执行
  │ 4. 更新游标 + session
  │ 5. Channel.send_message() 回复
  ▼
WhatsApp Channel → 用户
```

## 运行

```bash
uv run --with croniter python main.py
```

依赖 `croniter`（task-scheduler 模块需要）。

## 演示场景

| # | 场景 | 验证内容 |
|---|------|----------|
| 1 | 完整消息链路 | Channel → Store → Poll → Queue → Container → Respond |
| 2 | 触发词过滤 | 非 main 群无 @Andy → 跳过, 有 @Andy → 处理 |
| 3 | 并发控制 | 4 个群组 + max_concurrent=2 → 排队执行 |
| 4 | 持久化验证 | 消息/游标/session 存入 SQLite |
| 5 | 定时任务 | once 自动完成 + interval 更新 next_run |

## 文件结构

```
mini-nanoclaw/
├── README.md       # 本文件
└── main.py         # 串联 6 个组件, 5 个演示场景
```

## 与原实现的差异

| 方面 | 原实现 | Mini |
|------|--------|------|
| 容器 | Docker + Claude SDK | Mock (直接返回) |
| Channel | WhatsApp Baileys SDK | Mock WhatsAppChannel |
| IPC | 文件系统 JSON 管道 | 函数调用 |
| 持久化 | better-sqlite3 文件数据库 | Python sqlite3 内存数据库 |
| 轮询间隔 | 2000ms | 300ms (demo 加速) |

## 相关文档

- 分析文档: [docs/nanoclaw.md](../../docs/nanoclaw.md)
- 各组件 demo: `demos/nanoclaw/` 下的兄弟目录
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
