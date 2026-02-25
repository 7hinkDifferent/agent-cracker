"""消息轮询主循环 — NanoClaw Host 层核心编排

基于 src/index.ts 的 startMessageLoop (line 309-397) 和 processGroupMessages (line 131-227)。

核心流程:
  while True:
    1. 从 MessageStore 拉取注册组群的新消息
    2. 按 chat_jid 分组
    3. 触发词检查（非 main 组需要 @Andy）
    4. 拉取累积消息 → 格式化为 XML
    5. 管道到活跃容器 或 入队等待新容器
    6. sleep(poll_interval)
"""

from __future__ import annotations

import asyncio
import re
import xml.sax.saxutils as saxutils
from dataclasses import dataclass, field
from typing import Protocol


# ---------------------------------------------------------------------------
# Data models (mirrors src/types.ts)
# ---------------------------------------------------------------------------

@dataclass
class Message:
    id: str
    chat_jid: str
    sender: str
    sender_name: str
    content: str
    timestamp: str  # ISO 8601, lexicographic order = chronological
    is_from_me: bool = False


@dataclass
class RegisteredGroup:
    name: str
    folder: str
    requires_trigger: bool = True  # non-main groups need trigger word


# ---------------------------------------------------------------------------
# Message store (in-memory, replaces SQLite db.ts)
# ---------------------------------------------------------------------------

class MessageStore:
    """In-memory message store, mirrors db.ts getNewMessages / getMessagesSince."""

    def __init__(self) -> None:
        self._messages: list[Message] = []

    def store(self, msg: Message) -> None:
        self._messages.append(msg)

    def get_new_messages(
        self, jids: list[str], since: str, assistant_name: str
    ) -> tuple[list[Message], str]:
        """Return messages newer than `since` for registered JIDs."""
        jid_set = set(jids)
        result = [
            m for m in self._messages
            if m.chat_jid in jid_set
            and m.timestamp > since
            and not m.is_from_me
        ]
        new_ts = result[-1].timestamp if result else since
        return result, new_ts

    def get_messages_since(
        self, chat_jid: str, since: str, assistant_name: str
    ) -> list[Message]:
        """Return all messages for a group since timestamp (accumulated context)."""
        return [
            m for m in self._messages
            if m.chat_jid == chat_jid
            and m.timestamp > since
            and not m.is_from_me
        ]


# ---------------------------------------------------------------------------
# Message formatting (mirrors router.ts:formatMessages)
# ---------------------------------------------------------------------------

def format_messages(messages: list[Message]) -> str:
    """Format messages as XML, matching NanoClaw's XML envelope."""
    lines = ["<messages>"]
    for m in messages:
        escaped = saxutils.escape(m.content)
        lines.append(
            f'<message sender="{saxutils.escape(m.sender_name)}" '
            f'time="{m.timestamp}">{escaped}</message>'
        )
    lines.append("</messages>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Queue protocol (GroupQueue must implement this)
# ---------------------------------------------------------------------------

class GroupQueueProtocol(Protocol):
    def send_message(self, chat_jid: str, text: str) -> bool:
        """Pipe message to active container. Return True if sent."""
        ...

    def enqueue_message_check(self, chat_jid: str) -> None:
        """Enqueue group for new container spawn."""
        ...


# ---------------------------------------------------------------------------
# MessagePollLoop — the heart of NanoClaw host layer
# ---------------------------------------------------------------------------

class MessagePollLoop:
    """消息轮询主循环，对应 src/index.ts:startMessageLoop。

    关键机制:
    - 双游标: last_timestamp (全局已读水位) + last_agent_timestamp (每组处理水位)
    - 触发词过滤: 非 main 群需要 @Andy 触发，非触发消息在 DB 中累积
    - 管道优先: 活跃容器直接管道消息，否则入队等新容器
    - 启动恢复: recover_pending() 扫描未处理消息
    """

    def __init__(
        self,
        store: MessageStore,
        groups: dict[str, RegisteredGroup],
        queue: GroupQueueProtocol,
        *,
        trigger_pattern: re.Pattern[str] = re.compile(r"(?:^|\s)@Andy\b", re.IGNORECASE),
        main_folder: str = "main",
        poll_interval: float = 2.0,
        assistant_name: str = "Andy",
        on_poll: None | callable = None,
    ) -> None:
        self.store = store
        self.groups = groups
        self.queue = queue
        self.trigger_pattern = trigger_pattern
        self.main_folder = main_folder
        self.poll_interval = poll_interval
        self.assistant_name = assistant_name
        self.on_poll = on_poll  # callback for demo observability

        # Cursor state (persisted to SQLite in original, in-memory here)
        self.last_timestamp: str = ""
        self.last_agent_timestamp: dict[str, str] = {}

    async def run(self, max_iterations: int | None = None) -> None:
        """Main polling loop. Set max_iterations for demo/testing."""
        iteration = 0
        while max_iterations is None or iteration < max_iterations:
            iteration += 1
            actions = self._poll_once()
            if self.on_poll:
                self.on_poll(iteration, actions)
            await asyncio.sleep(self.poll_interval)

    def _poll_once(self) -> list[dict]:
        """Single poll iteration. Returns list of actions taken (for observability)."""
        jids = list(self.groups.keys())
        messages, new_ts = self.store.get_new_messages(
            jids, self.last_timestamp, self.assistant_name
        )
        if not messages:
            return []

        # Advance global "seen" cursor
        self.last_timestamp = new_ts

        # Group by chat_jid
        by_group: dict[str, list[Message]] = {}
        for msg in messages:
            by_group.setdefault(msg.chat_jid, []).append(msg)

        actions: list[dict] = []
        for chat_jid, group_msgs in by_group.items():
            group = self.groups.get(chat_jid)
            if not group:
                continue

            is_main = group.folder == self.main_folder
            needs_trigger = not is_main and group.requires_trigger

            # Trigger check: non-main groups need @Andy
            if needs_trigger:
                has_trigger = any(
                    self.trigger_pattern.search(m.content) for m in group_msgs
                )
                if not has_trigger:
                    actions.append({
                        "group": group.name, "action": "skipped",
                        "reason": "no trigger word",
                    })
                    continue

            # Pull accumulated messages since last agent processing
            all_pending = self.store.get_messages_since(
                chat_jid,
                self.last_agent_timestamp.get(chat_jid, ""),
                self.assistant_name,
            )
            to_send = all_pending if all_pending else group_msgs
            formatted = format_messages(to_send)

            # Try piping to active container, else enqueue
            if self.queue.send_message(chat_jid, formatted):
                self.last_agent_timestamp[chat_jid] = to_send[-1].timestamp
                actions.append({
                    "group": group.name, "action": "piped",
                    "count": len(to_send),
                })
            else:
                self.queue.enqueue_message_check(chat_jid)
                actions.append({
                    "group": group.name, "action": "enqueued",
                    "count": len(to_send),
                })

        return actions

    def recover_pending(self) -> list[str]:
        """Startup recovery: enqueue groups with unprocessed messages.

        Mirrors src/index.ts:recoverPendingMessages (line 404-416).
        """
        recovered = []
        for chat_jid, group in self.groups.items():
            since = self.last_agent_timestamp.get(chat_jid, "")
            pending = self.store.get_messages_since(
                chat_jid, since, self.assistant_name
            )
            if pending:
                self.queue.enqueue_message_check(chat_jid)
                recovered.append(group.name)
        return recovered
