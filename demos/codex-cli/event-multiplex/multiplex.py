"""
Codex CLI Event Multiplex 核心模块。

提供 tokio::select! 风格的多通道事件调度，可被 mini-codex 导入复用。

核心接口:
  - EventMultiplexer: 多通道事件循环
  - Channel: 异步事件通道
  - TurnLoop: 内层 turn 执行循环
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── 事件类型 ──────────────────────────────────────────────────────

class ChannelType(Enum):
    APP_EVENT = "app_event"          # 内部事件（tool 完成、compaction）
    LLM_RESPONSE = "llm_response"    # LLM 响应流
    USER_INPUT = "user_input"        # 用户键盘输入
    THREAD_CREATED = "thread_created" # 子线程通知


@dataclass
class Event:
    channel: ChannelType
    data: Any = None


# ── 异步通道 ──────────────────────────────────────────────────────

class Channel:
    """单个异步事件通道，模拟 tokio mpsc channel。"""

    def __init__(self, name: ChannelType):
        self.name = name
        self._closed = False
        self._shared_queue: asyncio.Queue | None = None

    def send(self, data: Any = None):
        if not self._closed and self._shared_queue:
            self._shared_queue.put_nowait(Event(channel=self.name, data=data))

    def close(self):
        self._closed = True


# ── 多路复用器 ────────────────────────────────────────────────────

class EventMultiplexer:
    """
    多通道事件多路复用，对应 codex-cli 的 tokio::select! 模式。

    所有通道的事件汇入一个共享队列，按到达顺序处理。
    对应 tui/src/app.rs 的 App::run()。
    """

    def __init__(self):
        self.channels: dict[ChannelType, Channel] = {}
        self._handlers: dict[ChannelType, Any] = {}
        self._running = False
        self._shared_queue: asyncio.Queue[Event | None] = asyncio.Queue()

    def add_channel(self, channel_type: ChannelType) -> Channel:
        ch = Channel(channel_type)
        ch._shared_queue = self._shared_queue  # 共享队列
        self.channels[channel_type] = ch
        return ch

    def on(self, channel_type: ChannelType, handler):
        """注册事件处理器。"""
        self._handlers[channel_type] = handler

    async def run(self):
        """
        运行多路复用循环。
        模拟 tokio::select! — 从共享队列消费事件。
        """
        self._running = True

        while self._running:
            event = await self._shared_queue.get()
            if event is None:
                break

            handler = self._handlers.get(event.channel)
            if handler:
                result = handler(event)
                if result == "stop":
                    self._running = False

    def stop(self):
        self._running = False
        self._shared_queue.put_nowait(None)


# ── Turn 执行循环 ─────────────────────────────────────────────────

@dataclass
class TurnResult:
    """一轮执行的结果。"""
    needs_follow_up: bool = False
    tool_calls: list[dict] = field(default_factory=list)
    content: str = ""
    token_usage: int = 0


class TurnLoop:
    """
    内层 turn 执行循环，对应 codex.rs 的 run_turn()。

    loop {
      1. 收集待处理输入
      2. 构建 sampling input
      3. 调用 LLM + 执行 tool calls
      4. 检查 token 超限 → auto-compact
      5. needs_follow_up == false → break
    }
    """

    def __init__(
        self,
        llm_fn,  # async (messages) -> TurnResult
        tool_fn,  # async (tool_call) -> str
        compact_fn=None,  # async (messages) -> messages
        token_limit: int = 128000,
    ):
        self.llm_fn = llm_fn
        self.tool_fn = tool_fn
        self.compact_fn = compact_fn
        self.token_limit = token_limit
        self.messages: list[dict] = []
        self.total_tokens: int = 0
        self._aborted = False

    def abort(self):
        self._aborted = True

    async def run(self, user_input: str) -> list[dict]:
        """运行一次完整的 turn 循环。"""
        self.messages.append({"role": "user", "content": user_input})
        events = []

        while True:
            if self._aborted:
                events.append({"type": "turn_aborted"})
                break

            # 3. 调用 LLM
            result = await self.llm_fn(self.messages)
            self.total_tokens += result.token_usage
            self.messages.append({"role": "assistant", "content": result.content})
            events.append({
                "type": "llm_response",
                "content": result.content,
                "tool_calls": len(result.tool_calls),
            })

            # 执行 tool calls
            for tc in result.tool_calls:
                tool_result = await self.tool_fn(tc)
                self.messages.append({"role": "tool", "content": tool_result})
                events.append({"type": "tool_result", "tool": tc.get("name", "?")})

            # 4. 检查 token 超限
            if self.total_tokens >= self.token_limit and result.needs_follow_up:
                if self.compact_fn:
                    self.messages = await self.compact_fn(self.messages)
                    self.total_tokens = self.total_tokens // 2  # 简化
                    events.append({"type": "auto_compact", "tokens_after": self.total_tokens})
                    continue

            # 5. ��成检查
            if not result.needs_follow_up:
                events.append({"type": "turn_complete"})
                break

        return events
