"""
Channel Abstraction Layer — 通道抽象层

复现 NanoClaw 的 Channel 接口设计：
  统一不同消息平台（WhatsApp/Telegram/...）的连接、收发、路由逻辑，
  Host Orchestrator 通过接口编程，无需感知底层平台差异。

核心设计：
  - Channel Protocol 定义统一接口（connect/send_message/owns_jid/disconnect）
  - 每个平台实现 owns_jid() 按 JID 模式匹配，声明自己负责哪些会话
  - find_channel() 遍历通道列表，找到第一个匹配的通道
  - NewMessage 统一消息格式，所有通道产出同一结构

原实现: src/types.ts (Channel interface), src/channels/whatsapp.ts, src/router.ts
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Optional, Callable


# ── NewMessage 统一消息格式 ───────────────────────────────────

@dataclass
class NewMessage:
    """统一消息结构（对应 types.ts 的 NewMessage 接口）"""
    id: str
    chat_jid: str
    sender: str
    sender_name: str
    content: str
    timestamp: str
    is_from_me: bool = False
    is_bot_message: bool = False


def make_message(
    chat_jid: str,
    sender: str,
    sender_name: str,
    content: str,
    is_from_me: bool = False,
) -> NewMessage:
    """便捷工厂：自动生成 id 和 timestamp"""
    return NewMessage(
        id=uuid.uuid4().hex[:12],
        chat_jid=chat_jid,
        sender=sender,
        sender_name=sender_name,
        content=content,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        is_from_me=is_from_me,
    )


# ── Channel Protocol ─────────────────────────────────────────

OnInboundMessage = Callable[[str, NewMessage], None]


@runtime_checkable
class Channel(Protocol):
    """通道抽象接口（对应 types.ts 的 Channel interface）"""
    name: str

    def connect(self) -> None: ...
    def send_message(self, jid: str, text: str) -> None: ...
    def is_connected(self) -> bool: ...
    def owns_jid(self, jid: str) -> bool: ...
    def disconnect(self) -> None: ...


# ── WhatsAppChannel ──────────────────────────────────────────

class WhatsAppChannel:
    """WhatsApp 通道（对应 src/channels/whatsapp.ts）

    JID 匹配规则：
      - 群组: xxx@g.us
      - 私聊: xxx@s.whatsapp.net
    """

    name = "whatsapp"

    def __init__(self, on_message: OnInboundMessage | None = None):
        self._connected = False
        self._on_message = on_message
        self._sent: list[tuple[str, str]] = []  # (jid, text) 记录

    def connect(self) -> None:
        self._connected = True

    def send_message(self, jid: str, text: str) -> None:
        if not self._connected:
            raise RuntimeError(f"[{self.name}] not connected")
        self._sent.append((jid, text))

    def is_connected(self) -> bool:
        return self._connected

    def owns_jid(self, jid: str) -> bool:
        return jid.endswith("@g.us") or jid.endswith("@s.whatsapp.net")

    def disconnect(self) -> None:
        self._connected = False

    # ── Mock helpers ──

    def simulate_inbound(self, msg: NewMessage) -> None:
        """模拟收到消息，触发回调"""
        if self._on_message:
            self._on_message(msg.chat_jid, msg)

    @property
    def sent_messages(self) -> list[tuple[str, str]]:
        return list(self._sent)


# ── TelegramChannel ──────────────────────────────────────────

class TelegramChannel:
    """Telegram 通道（NanoClaw 通过 skill 扩展支持 Telegram）

    JID 匹配规则：以 "tg:" 前缀标识
      - 群组: tg:group:12345
      - 私聊: tg:user:67890
    """

    name = "telegram"

    def __init__(self, on_message: OnInboundMessage | None = None):
        self._connected = False
        self._on_message = on_message
        self._sent: list[tuple[str, str]] = []

    def connect(self) -> None:
        self._connected = True

    def send_message(self, jid: str, text: str) -> None:
        if not self._connected:
            raise RuntimeError(f"[{self.name}] not connected")
        self._sent.append((jid, text))

    def is_connected(self) -> bool:
        return self._connected

    def owns_jid(self, jid: str) -> bool:
        return jid.startswith("tg:")

    def disconnect(self) -> None:
        self._connected = False

    def simulate_inbound(self, msg: NewMessage) -> None:
        if self._on_message:
            self._on_message(msg.chat_jid, msg)

    @property
    def sent_messages(self) -> list[tuple[str, str]]:
        return list(self._sent)


# ── Router ────────────────────────────────────────────────────

def find_channel(channels: list[Channel], jid: str) -> Channel | None:
    """按 JID 模式匹配找到对应通道（对应 router.ts 的 findChannel）"""
    for ch in channels:
        if ch.owns_jid(jid):
            return ch
    return None


def route_outbound(channels: list[Channel], jid: str, text: str) -> None:
    """路由出站消息：找到匹配且已连接的通道发送（对应 router.ts 的 routeOutbound）"""
    ch = find_channel(channels, jid)
    if ch is None:
        raise ValueError(f"No channel for JID: {jid}")
    if not ch.is_connected():
        raise RuntimeError(f"Channel \'{ch.name}\' is not connected for JID: {jid}")
    ch.send_message(jid, text)
