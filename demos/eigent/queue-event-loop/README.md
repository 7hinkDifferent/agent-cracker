# Demo: eigent — queue-event-loop

## 目标

用最简代码复现 eigent 的**队列驱动异步事件循环**机制 — 通过 `asyncio.Queue` 解耦事件分发，支持多种 Action 类型路由和多轮对话。

## MVP 角色

**主循环** — 这是 eigent 的核心骨架。所有 Agent 执行、Workforce 编排、SSE 流式响应都围绕这个事件循环展开。对应 D2（Agent Loop）。

## 原理

Eigent 的主循环与传统 `while True: think → act → observe` 不同，采用**队列驱动的事件分发**模式：

1. **TaskLock** 持有一个 `asyncio.Queue`，所有状态变更（用户输入、Agent 事件、任务完成）都通过入队/出队传递
2. **step_solve()** 是一个无限循环，每次迭代从队列取出一个 `ActionData`，根据 `action` 类型分发处理
3. 20+ 种 Action 类型覆盖完整生命周期：`improve`（新问题）→ `confirmed`（确认）→ `start`（执行）→ `activate_agent`/`deactivate_agent`（Agent 事件）→ `end`（完成）→ `stop`（停止）
4. 关键特性：任务完成后循环**不退出**，继续等待追问（`Action.improve`），实现多轮对话

这种设计的优势是**完全解耦** — Agent 执行、Toolkit 事件、前端交互都通过同一个队列通信，互不阻塞。

## 运行

```bash
cd demos/eigent/queue-event-loop
export OPENAI_API_KEY="sk-..."    # 或其他 LLM provider 的 key
uv run --with litellm python main.py
```

可通过 `DEMO_MODEL` 环境变量切换模型（默认 `gpt-4o-mini`）。

## 文件结构

```
demos/eigent/queue-event-loop/
├── README.md           # 本文件
└── main.py             # 完整 demo: Action/TaskLock/step_solve/模拟会话
```

## 关键代码解读

### 1. Action 枚举 — 事件类型定义

```python
class Action(str, Enum):
    improve = "improve"            # 用户 → 后端: 新问题
    start = "start"                # 用户 → 后端: 确认执行
    activate_agent = "activate_agent"    # 后端 → 用户: Agent 开始工作
    deactivate_agent = "deactivate_agent"  # 后端 → 用户: Agent 完成工作
    end = "end"                    # 后端 → 用户: 任务完成
    stop = "stop"                  # 用户 → 后端: 停止
```

原实现有 20+ 种 Action，这里保留核心 6 种。注意 Action 有**方向性** — 有些是用户→后端，有些是后端→用户。

### 2. TaskLock — 任务状态容器

```python
class TaskLock:
    def __init__(self, task_id: str) -> None:
        self.queue: asyncio.Queue[ActionData] = asyncio.Queue()
        self.conversation_history: list[dict] = []
        self.status = "idle"
```

原实现中 `TaskLock` 还包含 `human_input`（人机交互队列）、`background_tasks`（后台任务集合）等，这里简化为 queue + history。

### 3. step_solve — 队列事件循环

```python
async def step_solve(task_lock):
    while True:
        item = await task_lock.get_queue()   # 阻塞等待事件

        if item.action == Action.improve:
            is_complex = await check_complexity(question)
            if not is_complex:
                answer = await run_simple_answer(question)
                yield sse_json("wait_confirm", {...})  # 简单回答
            else:
                yield sse_json("confirmed", {...})
                await task_lock.put_queue(ActionData(action=Action.start))

        elif item.action == Action.start:
            result = await run_workforce(question)
            await task_lock.put_queue(ActionData(action=Action.end, data={...}))

        elif item.action == Action.end:
            yield sse_json("end", {...})
            # 循环不退出！等待下一个 improve

        elif item.action == Action.stop:
            break  # 唯一的正常退出点
```

这就是 eigent 主循环的精髓 — **队列驱动 + Action 分发 + 多轮不退出**。

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| Action 类型 | 20+ 种（含 pause/resume/supplement 等） | 6 种核心类型 |
| 复杂度判断 | LLM Agent（question_confirm_agent） | 关键词规则匹配 |
| Workforce 执行 | CAMEL Workforce + TaskChannel 并行 | 串行 LLM 调用模拟 |
| SSE 传输 | FastAPI StreamingResponse | print + yield 字符串 |
| 连接管理 | request.is_disconnected() 检测 | 无 |
| 超时处理 | 60 分钟 SSE 超时 + 30 分钟 step 超时 | 无 |
| 对话历史 | 200k 字符上限检查 | 无限制 |
| 客户端 | Electron React 应用 | 模拟函数调用 |

**保留的核心**：队列驱动事件循环、Action 分发机制、复杂度分流、多轮对话支持、SSE 事件格式。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/service/chat_service.py`, `backend/app/service/task.py`
