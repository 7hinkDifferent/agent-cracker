"""
OpenClaw — Channel Dock 机制复现

复现 OpenClaw 的统一通道能力抽象接口：
- ChannelDock 接口定义（capabilities / commands / streaming / threading）
- 多通道能力差异抽象
- 消息格式标准化

对应源码: src/channels/dock.ts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── 能力声明 ──────────────────────────────────────────────────────

@dataclass
class ChannelCapabilities:
    """通道能力声明"""
    text: bool = True
    media: bool = False           # 图片/视频/文件
    threading: bool = False       # 线程回复
    mentions: bool = False        # @提及
    reactions: bool = False       # 表情反应
    inline_buttons: bool = False  # 内联按钮
    voice: bool = False           # 语音消息
    typing_indicator: bool = False
    message_edit: bool = False    # 编辑已发消息
    message_delete: bool = False


@dataclass
class StreamingConfig:
    """流式回复配置"""
    block_reply_coalescing: bool = False  # 分块合并
    chunk_size: int = 2000                # 每块最大字符数
    typing_during_stream: bool = True


@dataclass
class GroupConfig:
    """群组消息配置"""
    mention_required: bool = False  # 群聊中必须 @bot 才响应
    group_message_handling: str = "reply"  # "reply" / "thread" / "ignore"


@dataclass
class ThreadingConfig:
    """线程配置"""
    reply_context_depth: int = 3  # 回复链追溯深度
    inherit_parent_binding: bool = True  # 线程继承父消息的路由绑定


# ── Channel Dock 接口 ────────────────────────────────────────────

@dataclass
class ChannelDock:
    """
    OpenClaw Channel Dock 复现

    统一抽象不同通道的能力差异：
    - capabilities: 该通道支持什么
    - streaming: 流式回复行为
    - groups: 群组消息处理
    - threading: 线程行为
    - max_message_length: 单条消息最大长度
    """
    channel_id: str
    display_name: str
    capabilities: ChannelCapabilities
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    groups: GroupConfig = field(default_factory=GroupConfig)
    threading: ThreadingConfig = field(default_factory=ThreadingConfig)
    max_message_length: int = 4096

    def format_message(self, text: str) -> list[str]:
        """按通道限制分块消息"""
        if len(text) <= self.max_message_length:
            return [text]

        chunks = []
        remaining = text
        while remaining:
            chunk = remaining[:self.max_message_length]
            # 尝试在自然断点处分割
            if len(remaining) > self.max_message_length:
                last_newline = chunk.rfind("\n")
                if last_newline > self.max_message_length // 2:
                    chunk = remaining[:last_newline + 1]
            chunks.append(chunk)
            remaining = remaining[len(chunk):]

        return chunks

    def should_respond(self, is_group: bool, is_mentioned: bool) -> bool:
        """判断是否应该响应消息"""
        if not is_group:
            return True
        if self.groups.mention_required and not is_mentioned:
            return False
        return True


# ── 预定义通道 ────────────────────────────────────────────────────

CHANNEL_DOCKS: dict[str, ChannelDock] = {
    "discord": ChannelDock(
        channel_id="discord",
        display_name="Discord",
        capabilities=ChannelCapabilities(
            text=True, media=True, threading=True, mentions=True,
            reactions=True, inline_buttons=True, typing_indicator=True,
            message_edit=True, message_delete=True,
        ),
        streaming=StreamingConfig(block_reply_coalescing=True, chunk_size=2000),
        groups=GroupConfig(mention_required=True, group_message_handling="thread"),
        threading=ThreadingConfig(reply_context_depth=5),
        max_message_length=2000,
    ),

    "telegram": ChannelDock(
        channel_id="telegram",
        display_name="Telegram",
        capabilities=ChannelCapabilities(
            text=True, media=True, threading=True, mentions=True,
            reactions=True, inline_buttons=True, typing_indicator=True,
            message_edit=True, message_delete=True,
        ),
        streaming=StreamingConfig(block_reply_coalescing=True, chunk_size=4096),
        groups=GroupConfig(mention_required=True, group_message_handling="reply"),
        max_message_length=4096,
    ),

    "slack": ChannelDock(
        channel_id="slack",
        display_name="Slack",
        capabilities=ChannelCapabilities(
            text=True, media=True, threading=True, mentions=True,
            reactions=True, typing_indicator=True,
            message_edit=True, message_delete=True,
        ),
        streaming=StreamingConfig(block_reply_coalescing=True, chunk_size=3000),
        groups=GroupConfig(mention_required=False, group_message_handling="thread"),
        threading=ThreadingConfig(reply_context_depth=10),
        max_message_length=3000,
    ),

    "whatsapp": ChannelDock(
        channel_id="whatsapp",
        display_name="WhatsApp",
        capabilities=ChannelCapabilities(
            text=True, media=True, voice=True, typing_indicator=True,
        ),
        streaming=StreamingConfig(block_reply_coalescing=False),
        max_message_length=65536,
    ),

    "imessage": ChannelDock(
        channel_id="imessage",
        display_name="iMessage",
        capabilities=ChannelCapabilities(
            text=True, media=True, reactions=True, typing_indicator=True,
        ),
        max_message_length=20000,
    ),

    "cli": ChannelDock(
        channel_id="cli",
        display_name="CLI (Terminal)",
        capabilities=ChannelCapabilities(text=True),
        streaming=StreamingConfig(block_reply_coalescing=False, typing_during_stream=False),
        max_message_length=999999,  # 无实际限制
    ),
}


# ── Demo ──────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("OpenClaw Channel Dock Demo")
    print("=" * 72)

    # ── 1. 能力矩阵 ──
    print("\n── 1. 通道能力矩阵 ──")
    caps_fields = ["text", "media", "threading", "mentions", "reactions",
                   "inline_buttons", "voice", "typing_indicator", "message_edit"]

    header = f"  {'':12s}" + "".join(f"{f:10s}" for f in caps_fields)
    print(header)
    print(f"  {'─'*12}" + "─" * (10 * len(caps_fields)))

    for dock in CHANNEL_DOCKS.values():
        row = f"  {dock.display_name:12s}"
        for f in caps_fields:
            val = getattr(dock.capabilities, f)
            row += f"{'  ✓':10s}" if val else f"{'  ·':10s}"
        print(row)

    # ── 2. 消息分块 ──
    print("\n── 2. 消息分块（长消息处理）──")
    long_message = "这是一段很长的消息。\n" * 100 + "结束。"
    for name, dock in [("discord", CHANNEL_DOCKS["discord"]), ("whatsapp", CHANNEL_DOCKS["whatsapp"])]:
        chunks = dock.format_message(long_message)
        print(f"  {name}: {len(long_message)} chars → {len(chunks)} chunks (max {dock.max_message_length}/chunk)")

    # ── 3. 群组响应策略 ──
    print("\n── 3. 群组消息响应策略 ──")
    for name, dock in CHANNEL_DOCKS.items():
        dm_respond = dock.should_respond(is_group=False, is_mentioned=False)
        group_no_mention = dock.should_respond(is_group=True, is_mentioned=False)
        group_mentioned = dock.should_respond(is_group=True, is_mentioned=True)
        print(
            f"  {dock.display_name:12s}: "
            f"DM={'✓' if dm_respond else '✗'}  "
            f"群聊(无@)={'✓' if group_no_mention else '✗'}  "
            f"群聊(@)={'✓' if group_mentioned else '✗'}  "
            f"mention_required={dock.groups.mention_required}"
        )

    # ── 4. 流式配置 ──
    print("\n── 4. 流式回复配置 ──")
    for name, dock in CHANNEL_DOCKS.items():
        s = dock.streaming
        print(
            f"  {dock.display_name:12s}: "
            f"coalescing={'✓' if s.block_reply_coalescing else '✗'}  "
            f"chunk_size={s.chunk_size:5d}  "
            f"typing={s.typing_during_stream}"
        )


if __name__ == "__main__":
    main()
