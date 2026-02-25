"""
NanoClaw Channel Abstraction Demo

演示 NanoClaw 的通道抽象层机制：
  1. Channel 注册 — 创建多个消息通道，各自声明 JID 所有权
  2. JID 路由 — findChannel 按后缀/前缀模式匹配目标通道
  3. 消息收发 — 模拟收到消息 -> 存储 -> 路由回复到正确通道
  4. 多通道管理 — connect/disconnect/isConnected 生命周期

Run: uv run python main.py
Based on commit: bc05d5f
"""

from channel import (
    WhatsAppChannel,
    TelegramChannel,
    NewMessage,
    make_message,
    find_channel,
    route_outbound,
    Channel,
)


# ── Demo 1: Channel 注册 ─────────────────────────────────────

def demo_channel_registration():
    """创建 WhatsApp + Telegram 通道，验证 Protocol 兼容"""
    print("=" * 60)
    print("Demo 1: Channel 注册")
    print("=" * 60)

    wa = WhatsAppChannel()
    tg = TelegramChannel()

    # 验证两个实现都符合 Channel Protocol
    assert isinstance(wa, Channel), "WhatsAppChannel should satisfy Channel protocol"
    assert isinstance(tg, Channel), "TelegramChannel should satisfy Channel protocol"

    channels: list[Channel] = [wa, tg]

    print(f"\n  已注册 {len(channels)} 个通道:")
    for ch in channels:
        print(f"    - {ch.name} (connected={ch.is_connected()})")

    # 连接所有通道
    for ch in channels:
        ch.connect()

    print(f"\n  连接后:")
    for ch in channels:
        print(f"    - {ch.name} (connected={ch.is_connected()})")

    print("\n  [ok] Channel Protocol 运行时检查通过")
    return channels


# ── Demo 2: JID 路由 ─────────────────────────────────────────

def demo_jid_routing(channels: list[Channel]):
    """findChannel 按 JID 模式匹配到正确通道"""
    print("\n" + "=" * 60)
    print("Demo 2: JID 路由")
    print("=" * 60)

    test_jids = [
        # WhatsApp JIDs
        ("120363xxxx@g.us",              "WhatsApp 群组"),
        ("8613800001111@s.whatsapp.net",  "WhatsApp 私聊"),
        # Telegram JIDs
        ("tg:group:python-dev",           "Telegram 群组"),
        ("tg:user:42",                    "Telegram 私聊"),
        # Unknown JID
        ("unknown:abc123",                "未知平台"),
    ]

    print(f"\n  {'JID':<40} {'匹配通道':<12} {'说明'}")
    print(f"  {'─' * 40} {'─' * 12} {'─' * 15}")

    for jid, desc in test_jids:
        ch = find_channel(channels, jid)
        matched = ch.name if ch else "(none)"
        print(f"  {jid:<40} {matched:<12} {desc}")

    # 验证路由正确性
    assert find_channel(channels, "120363xxxx@g.us").name == "whatsapp"
    assert find_channel(channels, "tg:user:42").name == "telegram"
    assert find_channel(channels, "unknown:abc123") is None

    print("\n  [ok] JID 路由匹配验证通过")


# ── Demo 3: 消息收发 ─────────────────────────────────────────

def demo_message_flow(channels: list[Channel]):
    """模拟收到消息 -> 存储 -> 路由回复"""
    print("\n" + "=" * 60)
    print("Demo 3: 消息收发")
    print("=" * 60)

    # 简单消息存储（模拟 db.ts 的 messages 表）
    inbox: list[NewMessage] = []

    def on_message(chat_jid: str, msg: NewMessage):
        inbox.append(msg)

    # 重新创建带回调的通道
    wa = WhatsAppChannel(on_message=on_message)
    tg = TelegramChannel(on_message=on_message)
    wa.connect()
    tg.connect()
    ch_list: list[Channel] = [wa, tg]

    # 模拟 WhatsApp 群组收到消息
    wa_msg = make_message(
        chat_jid="120363xxxx@g.us",
        sender="8613800001111@s.whatsapp.net",
        sender_name="Alice",
        content="@nanoclaw 帮我写个 hello world",
    )
    wa.simulate_inbound(wa_msg)

    # 模拟 Telegram 收到消息
    tg_msg = make_message(
        chat_jid="tg:group:python-dev",
        sender="tg:user:42",
        sender_name="Bob",
        content="/ask 什么是 Protocol?",
    )
    tg.simulate_inbound(tg_msg)

    print(f"\n  收到 {len(inbox)} 条消息:")
    for msg in inbox:
        print(f"    [{msg.chat_jid}] {msg.sender_name}: {msg.content}")

    # 路由回复到对应通道
    print(f"\n  路由回复:")
    for msg in inbox:
        reply = f"收到你的消息: {msg.content[:20]}..."
        route_outbound(ch_list, msg.chat_jid, reply)
        ch = find_channel(ch_list, msg.chat_jid)
        print(f"    -> [{ch.name}] {msg.chat_jid}: {reply}")

    # 验证发送记录
    assert len(wa.sent_messages) == 1
    assert len(tg.sent_messages) == 1
    assert wa.sent_messages[0][0] == "120363xxxx@g.us"
    assert tg.sent_messages[0][0] == "tg:group:python-dev"

    print(f"\n  发送记录:")
    print(f"    WhatsApp: {len(wa.sent_messages)} 条")
    print(f"    Telegram: {len(tg.sent_messages)} 条")

    # 测试未知 JID 的错误处理
    print(f"\n  测试未知 JID 错误处理:")
    try:
        route_outbound(ch_list, "slack:channel:general", "hello")
    except ValueError as e:
        print(f"    [ok] 预期错误: {e}")

    print("\n  [ok] 消息收发验证通过")


# ── Demo 4: 多通道管理 ───────────────────────────────────────

def demo_lifecycle():
    """connect/disconnect/isConnected 生命周期管理"""
    print("\n" + "=" * 60)
    print("Demo 4: 多通道管理")
    print("=" * 60)

    wa = WhatsAppChannel()
    tg = TelegramChannel()
    channels: list[Channel] = [wa, tg]

    def show_status(label: str):
        parts = []
        for ch in channels:
            parts.append(f"{ch.name}={'on' if ch.is_connected() else 'off'}")
        status = ", ".join(parts)
        print(f"    {label}: [{status}]")

    # 初始状态
    show_status("初始")

    # 逐个连接
    wa.connect()
    show_status("WA 连接")

    tg.connect()
    show_status("TG 连接")

    # 测试断开后发送失败
    wa.disconnect()
    show_status("WA 断开")

    print(f"\n  测试断开后发送:")
    try:
        wa.send_message("120363xxxx@g.us", "should fail")
    except RuntimeError as e:
        print(f"    [ok] 预期错误: {e}")

    # 通过 route_outbound 也应失败（通道未连接）
    try:
        route_outbound(channels, "120363xxxx@g.us", "should also fail")
    except RuntimeError as e:
        print(f"    [ok] route_outbound 预期错误: {e}")

    # Telegram 仍然可用
    tg.send_message("tg:user:42", "still works")
    print(f"    [ok] Telegram 仍可发送 (sent={len(tg.sent_messages)})")

    # 全部断开
    for ch in channels:
        ch.disconnect()
    show_status("全部断开")

    print("\n  [ok] 生命周期管理验证通过")


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("NanoClaw Channel Abstraction Demo")
    print("复现通道抽象层：统一接口 + JID 路由 + 多平台管理\n")

    channels = demo_channel_registration()
    demo_jid_routing(channels)
    demo_message_flow(channels)
    demo_lifecycle()

    print("\n" + "=" * 60)
    print("All demos passed!")
    print("=" * 60)
