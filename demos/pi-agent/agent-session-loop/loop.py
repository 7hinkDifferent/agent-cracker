"""
Pi-Agent Session Loop 核心模块。

提供双层循环 + 消息队列架构，可被 mini-pi 导入复用。

核心接口:
  - EventStream: 异步事件迭代器
  - MessageQueue: Steering/Follow-up 双消息队列
  - SessionLoop: 双层循环主引擎
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Callable, Any


# ── 事件系统 ──────────────────────────────────────────────────────

class EventType(Enum):
    MESSAGE_START = "message_start"
    MESSAGE_END = "message_end"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    STEERING_INTERRUPT = "steering_interrupt"
    LOOP_END = "loop_end"
    ERROR = "error"


@dataclass
class Event:
    type: EventType
    data: dict = field(default_factory=dict)


class EventStream:
    """
    异步事件流，对应 pi-agent 的 EventStream async iterator。
    外部消费者通过 async for 遍历事件。
    """

    def __init__(self):
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()
        self._closed = False

    def emit(self, event: Event):
        if not self._closed:
            self._queue.put_nowait(event)

    def close(self):
        self._closed = True
        self._queue.put_nowait(None)  # sentinel

    def __aiter__(self) -> AsyncIterator[Event]:
        return self

    async def __anext__(self) -> Event:
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item


# ── 消息队列 ──────────────────────────────────────────────────────

@dataclass
class Message:
    role: str  # "user" | "assistant" | "tool"
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


class MessageQueue:
    """
    双消息队列，对应 pi-agent 的 steering/follow-up 队列。

    - Steering: 中断当前执行，立即影响 Agent 行为
    - Follow-up: 等 Agent 完成当前任务后再处理
    """

    def __init__(self):
        self._steering: list[Message] = []
        self._followup: list[Message] = []

    def add_steering(self, msg: Message):
        """添加 steering 消息（立即中断）。"""
        self._steering.append(msg)

    def add_followup(self, msg: Message):
        """添加 follow-up 消息（排队等待）。"""
        self._followup.append(msg)

    def dequeue_steering(self) -> list[Message]:
        """取出所有 steering 消息。"""
        msgs = self._steering[:]
        self._steering.clear()
        return msgs

    def dequeue_followup(self) -> list[Message]:
        """取出所有 follow-up 消息。"""
        msgs = self._followup[:]
        self._followup.clear()
        return msgs

    def has_steering(self) -> bool:
        return len(self._steering) > 0

    def has_followup(self) -> bool:
        return len(self._followup) > 0


# ── Tool 执行 ─────────────────────────────────────────────────────

@dataclass
class ToolDef:
    """工具定义。"""
    name: str
    description: str
    execute: Callable[[dict], str]  # args → result string


async def execute_tool_calls(
    tool_calls: list[dict],
    tools: dict[str, ToolDef],
    events: EventStream,
) -> list[Message]:
    """
    并行执行 tool calls，返回 tool result messages。
    对应 pi-agent 的 executeToolCalls()。
    """
    results = []
    for tc in tool_calls:
        tool_name = tc["name"]
        tool_id = tc["id"]
        args = tc.get("arguments", {})

        events.emit(Event(EventType.TOOL_START, {
            "tool": tool_name, "id": tool_id, "args": args,
        }))

        tool = tools.get(tool_name)
        if tool:
            try:
                result = tool.execute(args)
            except Exception as e:
                result = f"Error: {e}"
        else:
            result = f"Unknown tool: {tool_name}"

        events.emit(Event(EventType.TOOL_END, {
            "tool": tool_name, "id": tool_id, "result": result,
        }))

        results.append(Message(
            role="tool",
            content=result,
            tool_call_id=tool_id,
        ))

    return results


# ── Mock LLM ──────────────────────────────────────────────────────

class MockLlm:
    """
    Mock LLM，按预设脚本返回响应。
    用于无 API key 的演示。
    """

    def __init__(self, script: list[Message]):
        self._script = list(script)
        self._index = 0

    async def complete(self, messages: list[Message]) -> Message:
        """模拟 LLM 调用。"""
        await asyncio.sleep(0)  # 让出事件循环，模拟异步
        if self._index < len(self._script):
            response = self._script[self._index]
            self._index += 1
            return response
        # 默认：无 tool call 的结束响应
        return Message(role="assistant", content="Done.")


# ── 双层循环引擎 ───────────────────────────────────────────────────

class SessionLoop:
    """
    Pi-Agent 双层循环引擎。

    外层循环：处理 follow-up 消息（等 Agent 空闲后执行）
    内层循环：LLM → tool call → 结果回填，含 steering 中断检查

    对应 packages/agent/src/agent-loop.ts 的 runLoop()。
    """

    def __init__(
        self,
        llm: MockLlm,
        tools: dict[str, ToolDef],
        queue: MessageQueue,
        events: EventStream,
    ):
        self.llm = llm
        self.tools = tools
        self.queue = queue
        self.events = events
        self.messages: list[Message] = []
        self._aborted = False

    def abort(self):
        """中止循环（对应 agent.abort()）。"""
        self._aborted = True

    async def run(self, initial_message: Message):
        """
        运行双层循环。

        外层：处理初始消息 + follow-up 队列
        内层：LLM → tool → steering 检查 → 循环
        """
        self.messages.append(initial_message)

        # 外层循环：处理当前 + follow-up
        while True:
            if self._aborted:
                break

            # 内层循环：LLM ↔ tool
            await self._inner_loop()

            # 检查 follow-up 队列
            followups = self.queue.dequeue_followup()
            if not followups:
                break  # 无更多消息，退出

            # 有 follow-up → 注入并继续外层循环
            self.messages.extend(followups)

        self.events.emit(Event(EventType.LOOP_END, {
            "total_messages": len(self.messages),
        }))
        self.events.close()

    async def _inner_loop(self):
        """内层循环：LLM → tool call → 结果回填。"""
        while True:
            if self._aborted:
                break

            # 1. 调用 LLM
            self.events.emit(Event(EventType.MESSAGE_START, {}))
            response = await self.llm.complete(self.messages)
            self.messages.append(response)
            self.events.emit(Event(EventType.MESSAGE_END, {
                "content": response.content,
                "has_tool_calls": bool(response.tool_calls),
            }))

            # 2. 无 tool call → 退出内层循环
            if not response.tool_calls:
                break

            # 3. 执行 tool calls
            tool_results = await execute_tool_calls(
                response.tool_calls, self.tools, self.events,
            )

            # 4. 检查 steering 消息（中断）
            steering = self.queue.dequeue_steering()
            if steering:
                self.events.emit(Event(EventType.STEERING_INTERRUPT, {
                    "count": len(steering),
                    "skipped_results": len(tool_results),
                }))
                # 注入 steering 消息，跳过 tool results
                self.messages.extend(steering)
                continue  # 用新消息重新调 LLM

            # 5. 无 steering → 正常回填 tool 结果
            self.messages.extend(tool_results)
            # 继续内层循环 → LLM 看到 tool 结果后决定下一步
