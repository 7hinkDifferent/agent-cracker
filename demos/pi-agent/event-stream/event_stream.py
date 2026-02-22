"""
EventStream — 异步事件流

复现 pi-agent 的 EventStream 模式：
  自定义 AsyncIterator + 事件队列，producer-consumer 解耦

核心设计：
  - push() 有 waiter 则直接唤醒，无则入队（demand-driven delivery）
  - async for 消费：队列有数据立即 yield，否则等待
  - end() 显式结束流，唤醒所有等待中的 consumer
  - result() 独立于迭代，等待聚合结果

原实现: packages/ai/src/utils/event-stream.ts
"""

import asyncio
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar("T")  # 事件类型
R = TypeVar("R")  # 结果类型


@dataclass
class AgentEvent:
    """简化的 Agent 事件"""
    type: str          # "thinking" | "tool_start" | "tool_end" | "text" | "agent_end"
    data: str = ""


class EventStream(Generic[T, R]):
    """异步事件流：producer push 事件，consumer 用 async for 消费

    核心模式来自 pi-agent：
    - queue + waiters 实现 demand-driven delivery
    - 有 consumer 等待时直接唤醒，避免不必要的排队
    - 支持完成条件检测和最终结果提取
    """

    def __init__(
        self,
        is_complete: Callable[[T], bool],
        extract_result: Callable[[T], R],
    ):
        self._is_complete = is_complete
        self._extract_result = extract_result
        self._queue: list[T] = []
        self._waiters: list[asyncio.Future[T | None]] = []
        self._done = False
        self._result_future: asyncio.Future[R] = asyncio.get_event_loop().create_future()

    def push(self, event: T) -> None:
        """推送事件：有 waiter 直接唤醒，否则入队"""
        if self._done:
            return

        # 检查是否为完成事件
        if self._is_complete(event):
            self._done = True
            if not self._result_future.done():
                self._result_future.set_result(self._extract_result(event))

        # demand-driven: 优先唤醒等待的 consumer
        if self._waiters:
            waiter = self._waiters.pop(0)
            if not waiter.done():
                waiter.set_result(event)
        else:
            self._queue.append(event)

    def end(self, result: R | None = None) -> None:
        """显式结束流，唤醒所有等待的 consumer"""
        self._done = True
        if result is not None and not self._result_future.done():
            self._result_future.set_result(result)
        # 唤醒所有 waiter，让它们退出
        for waiter in self._waiters:
            if not waiter.done():
                waiter.set_result(None)
        self._waiters.clear()

    async def result(self) -> R:
        """等待最终聚合结果（独立于迭代）"""
        return await self._result_future

    def __aiter__(self):
        return self

    async def __anext__(self) -> T:
        # 1. 队列有数据 → 立即返回
        if self._queue:
            return self._queue.pop(0)

        # 2. 已结束且队列空 → 停止迭代
        if self._done:
            raise StopAsyncIteration

        # 3. 等待 producer push
        waiter: asyncio.Future[T | None] = asyncio.get_event_loop().create_future()
        self._waiters.append(waiter)
        event = await waiter

        if event is None:
            raise StopAsyncIteration
        return event
