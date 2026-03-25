"""
Eigent — SSE 事件流协议 Demo

复现 eigent 的 Server-Sent Events 协议：
1. 多种事件类型：confirmed, decompose_text, activate_agent, deactivate_agent,
   activate_toolkit, deactivate_toolkit, task_state, end, error, wait_confirm
2. SSE 格式：event: <type>\ndata: <json>\n\n
3. 模拟 FastAPI 异步生成器 → 前端消费者的完整流程
4. 完整任务生命周期的事件序列演示

原实现: backend/app/model/chat.py (ChatEvent/ChatResponse)
       backend/app/controller/chat_controller.py (SSE endpoint)
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


# ─── SSE 事件类型枚举 ──────────────────────────────────────────

class EventType(str, Enum):
    """eigent 的所有 SSE 事件类型。

    原实现: backend/app/model/chat.py ChatEvent enum
    """
    CONFIRMED = "confirmed"                # 任务已确认，开始执行
    DECOMPOSE_TEXT = "decompose_text"      # Workforce 分解任务的文本流
    ACTIVATE_AGENT = "activate_agent"      # Agent 开始执行
    DEACTIVATE_AGENT = "deactivate_agent"  # Agent 执行完毕
    ACTIVATE_TOOLKIT = "activate_toolkit"  # Toolkit 方法开始
    DEACTIVATE_TOOLKIT = "deactivate_toolkit"  # Toolkit 方法结束
    TASK_STATE = "task_state"              # 任务状态变更
    END = "end"                            # 任务完成
    ERROR = "error"                        # 错误
    WAIT_CONFIRM = "wait_confirm"          # 等待用户确认


# ─── SSE 事件数据模型 ──────────────────────────────────────────

@dataclass
class ChatResponse:
    """SSE 事件载荷 — 对应 eigent 的 ChatResponse Pydantic 模型。

    原实现: backend/app/model/chat.py ChatResponse
    字段: event, message, agent_name, toolkit_name, method_name, data
    """
    event: EventType
    message: str = ""
    agent_name: str = ""
    toolkit_name: str = ""
    method_name: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """序列化为 SSE 格式 — event: <type>\ndata: <json>\n\n

        原实现: FastAPI StreamingResponse 的 media_type="text/event-stream"
        """
        payload = {
            "message": self.message,
            "agent_name": self.agent_name,
            "toolkit_name": self.toolkit_name,
            "method_name": self.method_name,
            **self.data,
        }
        # 过滤空值
        payload = {k: v for k, v in payload.items() if v}
        return f"event: {self.event.value}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ─── TaskLock 队列 — 后端事件缓冲 ─────────────────────────────

class TaskLock:
    """任务级事件队列 — Agent/Toolkit 把事件放入此队列。

    原实现: backend/app/utils/task_lock.py
    设计要点:
    - 每个任务一个 TaskLock 实例
    - Agent 执行时调用 queue.put() 推送事件
    - SSE endpoint 的 async generator 调用 queue.get() 消费事件
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.queue: asyncio.Queue[ChatResponse] = asyncio.Queue()
        self._finished = False

    async def put(self, event: ChatResponse) -> None:
        """Agent/Toolkit 推送事件到队列。"""
        await self.queue.put(event)

    async def stream(self) -> AsyncIterator[str]:
        """SSE endpoint 的异步生成器 — 消费队列并序列化为 SSE。

        原实现: chat_controller.py 的 streaming_response() 内部
        """
        while not self._finished:
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                yield event.to_sse()
                if event.event in (EventType.END, EventType.ERROR):
                    self._finished = True
            except asyncio.TimeoutError:
                # SSE 心跳（保持连接存活）
                yield ": heartbeat\n\n"

    async def finish(self) -> None:
        self._finished = True


# ─── 模拟 Agent 执行 — 产生事件序列 ───────────────────────────

async def simulate_task_execution(lock: TaskLock) -> None:
    """模拟完整任务生命周期 — 对应 eigent 的 TaskService.run_task()。

    事件序列:
    1. confirmed — 任务开始
    2. decompose_text — Workforce 分解子任务（流式文本）
    3. activate_agent → activate_toolkit → deactivate_toolkit → deactivate_agent（循环）
    4. task_state — 状态变更
    5. end — 任务完成
    """
    # 1. 任务确认
    await lock.put(ChatResponse(
        event=EventType.CONFIRMED,
        message="Task accepted, starting execution...",
        data={"task_id": lock.task_id},
    ))
    await asyncio.sleep(0.1)

    # 2. Workforce 分解任务（流式推送文本）
    decompose_chunks = [
        "Analyzing task complexity... ",
        "Decomposing into subtasks:\n",
        "  1. Research: Search for Python best practices\n",
        "  2. Development: Write the implementation\n",
        "  3. Documentation: Create README file\n",
    ]
    for chunk in decompose_chunks:
        await lock.put(ChatResponse(
            event=EventType.DECOMPOSE_TEXT,
            message=chunk,
        ))
        await asyncio.sleep(0.05)

    # 3. Agent 执行周期
    agents = [
        ("browser_agent", "SearchToolkit", "search_google", "Python best practices 2024"),
        ("developer_agent", "TerminalToolkit", "shell_exec", "python main.py"),
        ("developer_agent", "FileWriteToolkit", "write_to_file", "Writing README.md"),
    ]

    for agent_name, toolkit, method, message in agents:
        # activate_agent
        await lock.put(ChatResponse(
            event=EventType.ACTIVATE_AGENT,
            agent_name=agent_name,
            message=f"Starting: {message}",
        ))
        await asyncio.sleep(0.1)

        # activate_toolkit
        await lock.put(ChatResponse(
            event=EventType.ACTIVATE_TOOLKIT,
            agent_name=agent_name,
            toolkit_name=toolkit,
            method_name=method,
            message=message,
        ))
        await asyncio.sleep(0.15)

        # deactivate_toolkit
        await lock.put(ChatResponse(
            event=EventType.DEACTIVATE_TOOLKIT,
            agent_name=agent_name,
            toolkit_name=toolkit,
            method_name=method,
            message=f"Completed: {message}",
        ))
        await asyncio.sleep(0.05)

        # deactivate_agent
        await lock.put(ChatResponse(
            event=EventType.DEACTIVATE_AGENT,
            agent_name=agent_name,
            message=f"Agent finished subtask",
            data={"tokens": 150},
        ))
        await asyncio.sleep(0.1)

    # 4. 状态变更
    await lock.put(ChatResponse(
        event=EventType.TASK_STATE,
        message="All subtasks completed",
        data={"state": "completed", "progress": "3/3"},
    ))

    # 5. 任务完成
    await lock.put(ChatResponse(
        event=EventType.END,
        message="Task completed successfully",
        data={"total_tokens": 450, "duration_s": 1.2},
    ))


# ─── 模拟前端消费者 ───────────────────────────────────────────

async def frontend_consumer(lock: TaskLock) -> list[dict]:
    """模拟前端 EventSource 消费 SSE 流。

    原实现: 前端 JavaScript 通过 EventSource API 消费
    这里解析 SSE 文本，还原为结构化事件
    """
    received_events: list[dict] = []
    decompose_buffer = ""

    async for sse_text in lock.stream():
        # 跳过心跳
        if sse_text.startswith(":"):
            continue

        # 解析 SSE 格式
        lines = sse_text.strip().split("\n")
        event_type = ""
        data_str = ""
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data_str = line[6:]

        if not event_type or not data_str:
            continue

        data = json.loads(data_str)
        received_events.append({"event": event_type, **data})

        # 前端处理逻辑
        icon = {
            "confirmed": "[START]",
            "decompose_text": "[PLAN]",
            "activate_agent": "[>>]",
            "deactivate_agent": "[<<]",
            "activate_toolkit": "[>T]",
            "deactivate_toolkit": "[<T]",
            "task_state": "[STATE]",
            "end": "[DONE]",
            "error": "[ERR]",
            "wait_confirm": "[?]",
        }.get(event_type, "[?]")

        if event_type == "decompose_text":
            decompose_buffer += data.get("message", "")
        else:
            # 先 flush decompose buffer
            if decompose_buffer:
                print(f"  [PLAN]  {decompose_buffer.rstrip()}")
                decompose_buffer = ""

            agent = data.get("agent_name", "")
            toolkit = data.get("toolkit_name", "")
            method = data.get("method_name", "")
            msg = data.get("message", "")

            if toolkit:
                print(f"  {icon}  {agent} / {toolkit}.{method}(): {msg}")
            elif agent:
                print(f"  {icon}  {agent}: {msg}")
            else:
                print(f"  {icon}  {msg}")

    return received_events


# ─── Demo ────────────────────────────────────────────────────

async def async_main():
    print("=" * 60)
    print("Eigent SSE 事件流协议 Demo")
    print("=" * 60)

    # 创建任务锁
    lock = TaskLock("task-001")

    # 并发：后端产生事件 + 前端消费事件
    print("\n--- SSE 事件流 ---\n")
    producer = asyncio.create_task(simulate_task_execution(lock))
    events = await frontend_consumer(lock)
    await producer

    # 事件统计
    print(f"\n{'=' * 60}")
    print(f"事件统计 (共 {len(events)} 个)")
    print("=" * 60)
    from collections import Counter
    counts = Counter(e["event"] for e in events)
    for event_type, count in counts.most_common():
        print(f"  {event_type}: {count}")

    # 演示 SSE 原始格式
    print(f"\n{'─' * 40}")
    print("SSE 原始格式示例:")
    print("─" * 40)
    sample = ChatResponse(
        event=EventType.ACTIVATE_TOOLKIT,
        agent_name="developer_agent",
        toolkit_name="TerminalToolkit",
        method_name="shell_exec",
        message="python main.py",
    )
    print(sample.to_sse())

    print("Demo 完成")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
