# Demo: NanoClaw — Task Scheduler

## 目标

用最简代码复现 NanoClaw 的定时任务调度机制：cron/interval/once 三种调度类型 + group/isolated 双 context mode + 60s 轮询循环。

## 平台维度角色

任务调度器是 NanoClaw 平台层的**自治能力**核心组件（D11）。它让 Agent 不依赖用户消息触发，能按计划自主执行任务——例如定时检查 CI 状态、每小时生成报告、某个时间点执行一次性部署。调度器通过 GroupQueue 将任务排入组群队列，与消息驱动的请求共享同一套并发控制和容器调度基础设施。

## 原理

### 三种调度类型

```
schedule_type  │  schedule_value 示例    │  next_run 计算逻辑
───────────────┼─────────────────────────┼──────────────────────────
cron           │  "*/5 * * * *"          │  cron-parser 算下一匹配时间
interval       │  "300000"               │  Date.now() + parseInt(value)
once           │  "2026-02-25T10:00:00Z" │  无（运行后 status→completed）
```

### 双 Context Mode

```
context_mode │  行为
─────────────┼────────────────────────────────────
group        │  复用组群 session（sessions[group_folder]）
             │  Agent 能看到之前的对话历史
─────────────┼────────────────────────────────────
isolated     │  sessionId = undefined
             │  每次运行创建全新 session，无历史
```

### 轮询循环（60s）

```
setTimeout(loop, 60000)
  ├─ getDueTasks()          # SQL: status='active' AND next_run <= NOW
  ├─ for task of dueTasks:
  │   ├─ re-check status    # 可能在轮询间隙被 pause/cancel
  │   └─ queue.enqueueTask()# 加入 GroupQueue，复用并发控制
  └─ runTask()
      ├─ runContainerAgent()# 启动容器执行
      ├─ updateTaskAfterRun()
      │   ├─ cron:  next = parser.next()
      │   ├─ interval: next = now + ms
      │   └─ once:  next = null → status='completed'
      └─ logTaskRun()       # 记录执行日志
```

## 运行

```bash
cd demos/nanoclaw/task-scheduler
uv run --with croniter python main.py
```

依赖 `croniter`（纯 Python cron 表达式解析器），通过 `uv run --with` 自动安装。

## 文件结构

```
demos/nanoclaw/task-scheduler/
├── README.md       # 本文件
├── scheduler.py    # 可复用模块：ScheduledTask / TaskStore / SchedulerLoop
└── main.py         # Demo 入口：5 个场景演示
```

## 关键代码解读

### 数据模型（scheduler.py）

`ScheduledTask` dataclass 精确映射原实现 `types.ts` 的接口定义：

```python
@dataclass
class ScheduledTask:
    id: str
    group_folder: str
    chat_jid: str
    prompt: str
    schedule_type: ScheduleType    # cron | interval | once
    schedule_value: str            # cron expression / ms / ISO timestamp
    context_mode: ContextMode      # group | isolated
    status: TaskStatus             # active | paused | completed
    next_run: Optional[str]        # ISO 8601, None = no more runs
    last_run: Optional[str]
    last_result: Optional[str]
```

### next_run 计算（scheduler.py）

三种类型的 next_run 计算逻辑，对应原实现 `task-scheduler.ts:162-173`：

```python
def calculate_next_run(schedule_type, schedule_value):
    if schedule_type == ScheduleType.CRON:
        # croniter 等价于 JS 的 cron-parser
        return croniter(schedule_value, now).get_next(datetime)
    elif schedule_type == ScheduleType.INTERVAL:
        return now + timedelta(milliseconds=int(schedule_value))
    elif schedule_type == ScheduleType.ONCE:
        return None  # 触发 status -> completed
```

### 到期任务扫描（scheduler.py TaskStore.get_due_tasks）

Python 列表过滤等价于原实现的 SQL 查询：

```python
# 原实现 SQL: WHERE status='active' AND next_run IS NOT NULL AND next_run <= ?
due = [t for t in tasks
       if t.status == ACTIVE and t.next_run is not None and t.next_run <= now]
```

### 任务生命周期（scheduler.py TaskStore.update_after_run）

运行后自动更新状态，`once` 任务通过 `next_run=None` 触发自动完成：

```python
# 原实现 SQL: status = CASE WHEN ? IS NULL THEN 'completed' ELSE status END
if next_run is None:
    task.status = TaskStatus.COMPLETED
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 语言 | TypeScript | Python |
| 存储 | SQLite (better-sqlite3) | 内存 dict |
| Cron 解析 | cron-parser (JS) | croniter (Python) |
| 任务执行 | Docker 容器 + Claude Agent SDK | Mock runner 函数 |
| 轮询 | setTimeout 真实 60s 循环 | 单次 poll() 调用 |
| 队列集成 | GroupQueue.enqueueTask() | 直接同步执行 |
| 结果转发 | sendMessage() ���过 WhatsApp 发送 | 打印结果 |
| 错误处理 | 无效 group_folder 自动 pause | 省略（无文件系统校验） |
| 任务快照 | writeTasksSnapshot() 写入容器 | 省略 |

## 相关文档

- 分析文档: [docs/nanoclaw.md](../../../docs/nanoclaw.md) (D11: 安全与自治)
- 原项目: https://github.com/qwibitai/nanoclaw
- 基于 commit: `bc05d5f`
- 核心源码: `src/task-scheduler.ts`, `src/db.ts` (getDueTasks/updateTaskAfterRun), `src/types.ts` (ScheduledTask)
