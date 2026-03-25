# Demo: eigent — sse-streaming

## 目标

用最简代码复现 eigent 的 **SSE 事件流协议** — 多种事件类型的序列化、TaskLock 队列缓冲、异步生成器推送、前端消费者解析。

## 平台角色

**通道层事件协议**（D9）— SSE 是 eigent 前后端通信的核心协议。Agent/Toolkit 执行时产生的事件通过 TaskLock 队列缓冲，由 FastAPI StreamingResponse 以 `text/event-stream` 格式推送到前端 EventSource。

## 原理

Eigent 的 SSE 事件流分三层：

1. **事件模型**（`chat.py`）：`ChatResponse` Pydantic 模型定义 10 种事件类型（confirmed → decompose_text → activate_agent → activate_toolkit → deactivate_toolkit → deactivate_agent → task_state → end），每种事件携带不同字段（agent_name、toolkit_name、method_name 等）
2. **队列缓冲**（`task_lock.py`）：`TaskLock` 为每个任务维护一个 asyncio.Queue，Agent 执行时 `put()` 推送事件，SSE endpoint 的 async generator 调用 `get()` 消费
3. **流式推送**（`chat_controller.py`）：FastAPI 的 `StreamingResponse` 消费 TaskLock 的异步生成器，序列化为标准 SSE 格式 `event: <type>\ndata: <json>\n\n`

关键设计：事件类型决定前端 UI 行为 — `activate_agent` 显示 Agent 状态面板，`decompose_text` 流式渲染任务分解过程，`wait_confirm` 弹出确认对话框。

## 运行

```bash
cd demos/eigent/sse-streaming
uv run python main.py
```

无需 API key — 此 demo 不调用 LLM，完全模拟事件序列。

## 文件结构

```
demos/eigent/sse-streaming/
├── README.md           # 本文件
└── main.py             # EventType/ChatResponse/TaskLock/simulate_task_execution/frontend_consumer
```

## 关键代码解读

### ChatResponse.to_sse() — SSE 序列化

```python
def to_sse(self) -> str:
    payload = {"message": self.message, "agent_name": self.agent_name, ...}
    payload = {k: v for k, v in payload.items() if v}  # 过滤空值
    return f"event: {self.event.value}\ndata: {json.dumps(payload)}\n\n"
```

### TaskLock.stream() — 异步生成器

```python
async def stream(self) -> AsyncIterator[str]:
    while not self._finished:
        try:
            event = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            yield event.to_sse()
            if event.event in (EventType.END, EventType.ERROR):
                self._finished = True
        except asyncio.TimeoutError:
            yield ": heartbeat\n\n"  # SSE 心跳保活
```

### 任务生命周期事件序列

```
confirmed → decompose_text(n) → [activate_agent → activate_toolkit →
deactivate_toolkit → deactivate_agent](n) → task_state → end
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 事件模型 | Pydantic BaseModel + 序列化 | dataclass + 手动 JSON |
| 传输层 | FastAPI StreamingResponse | asyncio.Queue + async generator |
| 前端消费 | JavaScript EventSource API | Python 异步解析 |
| 心跳机制 | SSE 标准注释行 | 相同（`: heartbeat\n\n`） |
| 事件来源 | ListenChatAgent + Workforce 实际执行 | 模拟固定序列 |
| wait_confirm | 阻塞等待用户前端确认 | 仅定义类型，未演示阻塞 |

**保留的核心**：10 种事件类型定义、SSE 序列化格式、TaskLock 异步队列缓冲、生产者-消费者并发模型、完整任务生命周期事件序列。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/model/chat.py`, `backend/app/controller/chat_controller.py`
