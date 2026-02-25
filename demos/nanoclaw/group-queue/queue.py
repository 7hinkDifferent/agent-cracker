"""每组消息队列 + 全局并发控制 + 指数退避重试

基于 src/group-queue.ts (339 行)。

核心机制:
  - GroupState: 每组维护 active/idle/pending/retry 等状态
  - 全局并发限制: MAX_CONCURRENT_CONTAINERS (默认 5)
  - 指数退避: BASE_RETRY_MS * 2^(retryCount-1), 最多 MAX_RETRIES 次
  - 排水机制: 容器结束后 drain → 优先 task → 然后 message → 然后 waiting queue
  - IPC 管道: 活跃容器可通过 send_message 接收后续消息
  - _close sentinel: 空闲超时后写入 _close 文件通知容器退出
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable


MAX_CONCURRENT = 5
MAX_RETRIES = 5
BASE_RETRY_MS = 5000


@dataclass
class QueuedTask:
    id: str
    group_jid: str
    fn: Callable[[], Awaitable[None]]


@dataclass
class GroupState:
    active: bool = False
    idle_waiting: bool = False
    is_task_container: bool = False
    pending_messages: bool = False
    pending_tasks: list[QueuedTask] = field(default_factory=list)
    group_folder: str | None = None
    retry_count: int = 0


class GroupQueue:
    """每组消息队列 + 全局并发控制。

    关键设计:
    1. 每组独立状态 → 组间不互相阻塞
    2. 全局并发上限 → 防止资源耗尽
    3. Task 优先于 Message → task 不会被 rediscover
    4. 指数退避 → 失败后逐步延迟重试
    5. 管道机制 → 活跃容器可接收后续消息而无需重启
    """

    def __init__(
        self,
        max_concurrent: int = MAX_CONCURRENT,
        process_messages_fn: Callable[[str], Awaitable[bool]] | None = None,
        on_event: Callable[[dict], None] | None = None,
    ) -> None:
        self._groups: dict[str, GroupState] = {}
        self._active_count = 0
        self._waiting: list[str] = []
        self._process_fn = process_messages_fn
        self._max_concurrent = max_concurrent
        self._shutting_down = False
        self._on_event = on_event  # observability callback

    def _emit(self, event: dict) -> None:
        if self._on_event:
            self._on_event(event)

    def _get(self, jid: str) -> GroupState:
        if jid not in self._groups:
            self._groups[jid] = GroupState()
        return self._groups[jid]

    def set_process_messages_fn(self, fn: Callable[[str], Awaitable[bool]]) -> None:
        self._process_fn = fn

    # ------------------------------------------------------------------
    # Public API: enqueue / send / close
    # ------------------------------------------------------------------

    def enqueue_message_check(self, group_jid: str) -> None:
        """Enqueue group for container processing."""
        if self._shutting_down:
            return
        state = self._get(group_jid)

        if state.active:
            state.pending_messages = True
            self._emit({"type": "queued", "group": group_jid, "reason": "container active"})
            return

        if self._active_count >= self._max_concurrent:
            state.pending_messages = True
            if group_jid not in self._waiting:
                self._waiting.append(group_jid)
            self._emit({"type": "queued", "group": group_jid, "reason": "at limit"})
            return

        asyncio.ensure_future(self._run_for_group(group_jid, "messages"))

    def enqueue_task(self, group_jid: str, task: QueuedTask) -> None:
        """Enqueue a scheduled task."""
        if self._shutting_down:
            return
        state = self._get(group_jid)

        if any(t.id == task.id for t in state.pending_tasks):
            return  # deduplicate

        if state.active:
            state.pending_tasks.append(task)
            if state.idle_waiting:
                self.close_stdin(group_jid)
            self._emit({"type": "task_queued", "group": group_jid, "task": task.id})
            return

        if self._active_count >= self._max_concurrent:
            state.pending_tasks.append(task)
            if group_jid not in self._waiting:
                self._waiting.append(group_jid)
            return

        asyncio.ensure_future(self._run_task(group_jid, task))

    def send_message(self, group_jid: str, text: str) -> bool:
        """Pipe message to active container. Returns True if sent."""
        state = self._get(group_jid)
        if not state.active or state.is_task_container:
            return False
        state.idle_waiting = False
        self._emit({"type": "piped", "group": group_jid, "length": len(text)})
        return True

    def close_stdin(self, group_jid: str) -> None:
        """Signal container to wind down (write _close sentinel)."""
        state = self._get(group_jid)
        if not state.active:
            return
        self._emit({"type": "close_stdin", "group": group_jid})

    def notify_idle(self, group_jid: str) -> None:
        """Mark container as idle-waiting. Preempt if tasks pending."""
        state = self._get(group_jid)
        state.idle_waiting = True
        if state.pending_tasks:
            self.close_stdin(group_jid)

    # ------------------------------------------------------------------
    # Internal: run / retry / drain
    # ------------------------------------------------------------------

    async def _run_for_group(self, group_jid: str, reason: str) -> None:
        state = self._get(group_jid)
        state.active = True
        state.idle_waiting = False
        state.is_task_container = False
        state.pending_messages = False
        self._active_count += 1

        self._emit({
            "type": "start", "group": group_jid, "reason": reason,
            "active_count": self._active_count,
        })

        try:
            if self._process_fn:
                success = await self._process_fn(group_jid)
                if success:
                    state.retry_count = 0
                else:
                    self._schedule_retry(group_jid, state)
        except Exception as e:
            self._emit({"type": "error", "group": group_jid, "error": str(e)})
            self._schedule_retry(group_jid, state)
        finally:
            state.active = False
            state.group_folder = None
            self._active_count -= 1
            self._emit({
                "type": "finish", "group": group_jid,
                "active_count": self._active_count,
            })
            await self._drain_group(group_jid)

    async def _run_task(self, group_jid: str, task: QueuedTask) -> None:
        state = self._get(group_jid)
        state.active = True
        state.idle_waiting = False
        state.is_task_container = True
        self._active_count += 1

        self._emit({"type": "task_start", "group": group_jid, "task": task.id})

        try:
            await task.fn()
        except Exception as e:
            self._emit({"type": "task_error", "group": group_jid, "error": str(e)})
        finally:
            state.active = False
            state.is_task_container = False
            self._active_count -= 1
            await self._drain_group(group_jid)

    def _schedule_retry(self, group_jid: str, state: GroupState) -> None:
        """Exponential backoff: 5s → 10s → 20s → 40s → 80s, then give up."""
        state.retry_count += 1
        if state.retry_count > MAX_RETRIES:
            self._emit({
                "type": "retry_exhausted", "group": group_jid,
                "retries": state.retry_count,
            })
            state.retry_count = 0
            return

        delay_s = (BASE_RETRY_MS * (2 ** (state.retry_count - 1))) / 1000
        self._emit({
            "type": "retry_scheduled", "group": group_jid,
            "retry": state.retry_count, "delay_s": delay_s,
        })

        async def _retry():
            await asyncio.sleep(delay_s)
            if not self._shutting_down:
                self.enqueue_message_check(group_jid)

        asyncio.ensure_future(_retry())

    async def _drain_group(self, group_jid: str) -> None:
        """After container finishes: tasks first → messages → waiting queue."""
        if self._shutting_down:
            return
        state = self._get(group_jid)

        # Tasks first (won't be re-discovered from DB like messages)
        if state.pending_tasks:
            task = state.pending_tasks.pop(0)
            asyncio.ensure_future(self._run_task(group_jid, task))
            return

        if state.pending_messages:
            asyncio.ensure_future(self._run_for_group(group_jid, "drain"))
            return

        # Nothing pending — let other waiting groups run
        await self._drain_waiting()

    async def _drain_waiting(self) -> None:
        """Let waiting groups claim freed slots."""
        while self._waiting and self._active_count < self._max_concurrent:
            jid = self._waiting.pop(0)
            state = self._get(jid)
            if state.pending_tasks:
                task = state.pending_tasks.pop(0)
                asyncio.ensure_future(self._run_task(jid, task))
            elif state.pending_messages:
                asyncio.ensure_future(self._run_for_group(jid, "drain"))

    async def shutdown(self, grace_ms: int = 10000) -> None:
        self._shutting_down = True
        self._emit({
            "type": "shutdown",
            "active_count": self._active_count,
            "waiting": len(self._waiting),
        })
