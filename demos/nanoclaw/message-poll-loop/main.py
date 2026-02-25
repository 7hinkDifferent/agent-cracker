"""NanoClaw 消息轮询主循环 — Demo

演示 NanoClaw Host 层的核心编排逻辑：
  1. 轮询注册组群的新消息
  2. 触发词过滤（非 main 群需要 @Andy）
  3. 消息累积与 XML 格式化
  4. 管道到活跃容器 vs 入队等待新容器
  5. 启动恢复（扫描未处理消息）

运行: uv run python main.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loop import (
    Message,
    MessagePollLoop,
    MessageStore,
    RegisteredGroup,
    format_messages,
)


# ---------------------------------------------------------------------------
# Mock queue (simulates GroupQueue interface)
# ---------------------------------------------------------------------------

class MockQueue:
    """模拟 GroupQueue，记录操作供 demo 展示。"""

    def __init__(self) -> None:
        self.log: list[str] = []
        self._active: set[str] = set()

    def send_message(self, chat_jid: str, text: str) -> bool:
        if chat_jid in self._active:
            self.log.append(f"  → 管道到活跃容器 [{chat_jid}]: {len(text)} chars")
            return True
        return False

    def enqueue_message_check(self, chat_jid: str) -> None:
        self.log.append(f"  → 入队等待新容器 [{chat_jid}]")

    def set_active(self, chat_jid: str) -> None:
        self._active.add(chat_jid)


def ts(minute: int) -> str:
    """Generate ISO timestamp for demo messages."""
    return f"2026-02-25T10:{minute:02d}:00.000Z"


# ---------------------------------------------------------------------------
# Demo 1: 基本轮询 — main 群无需触发词
# ---------------------------------------------------------------------------

def demo_basic_polling():
    print("=" * 60)
    print("Demo 1: 基本轮询 — main 群直接处理，非 main 群需要触发词")
    print("=" * 60)

    store = MessageStore()
    queue = MockQueue()
    groups = {
        "main@g.us": RegisteredGroup(name="Main", folder="main", requires_trigger=False),
        "team@g.us": RegisteredGroup(name="Team", folder="team", requires_trigger=True),
    }

    loop = MessagePollLoop(store, groups, queue, poll_interval=0.01)

    # 添加消息
    store.store(Message("1", "main@g.us", "user1", "Alice", "帮我查天气", ts(0)))
    store.store(Message("2", "team@g.us", "user2", "Bob", "今天开会吗？", ts(1)))  # 无触发词
    store.store(Message("3", "team@g.us", "user3", "Carol", "@Andy 帮我写代码", ts(2)))  # 有触发词

    actions = loop._poll_once()
    for a in actions:
        print(f"  [{a['group']}] {a['action']}" +
              (f" — {a.get('reason', '')}" if 'reason' in a else f" ({a.get('count', 0)} msgs)"))
    for log in queue.log:
        print(log)

    print(f"\n  游标状态: last_timestamp={loop.last_timestamp}")
    print(f"  agent 游标: {loop.last_agent_timestamp}")
    print()


# ---------------------------------------------------------------------------
# Demo 2: 消息累积 — 非触发消息累积后一次性发送
# ---------------------------------------------------------------------------

def demo_accumulation():
    print("=" * 60)
    print("Demo 2: 消息累积 — 非触发消息在 DB 中累积，触发时一次性拉取")
    print("=" * 60)

    store = MessageStore()
    queue = MockQueue()
    groups = {
        "team@g.us": RegisteredGroup(name="Team", folder="team", requires_trigger=True),
    }
    loop = MessagePollLoop(store, groups, queue, poll_interval=0.01)

    # 第一轮：只有普通消息，不触发
    store.store(Message("1", "team@g.us", "u1", "Alice", "新需求讨论", ts(0)))
    store.store(Message("2", "team@g.us", "u2", "Bob", "我看了一下可以做", ts(1)))
    actions = loop._poll_once()
    print("  第一轮（无触发词）:")
    for a in actions:
        print(f"    [{a['group']}] {a['action']} — {a.get('reason', '')}")

    # 第二轮：触发消息到达，累积的普通消息一起发送
    store.store(Message("3", "team@g.us", "u1", "Alice", "@Andy 帮忙实现一下", ts(2)))
    actions = loop._poll_once()
    print("  第二轮（有触发词，拉取累积消息）:")
    for a in actions:
        print(f"    [{a['group']}] {a['action']} ({a.get('count', 0)} msgs)")
    for log in queue.log:
        print(log)
    print()


# ---------------------------------------------------------------------------
# Demo 3: 管道 vs 入队 — 活跃容器直接管道
# ---------------------------------------------------------------------------

def demo_pipe_vs_enqueue():
    print("=" * 60)
    print("Demo 3: 管道 vs 入队 — 活跃容器直接管道，否则入队等新容器")
    print("=" * 60)

    store = MessageStore()
    queue = MockQueue()
    groups = {
        "main@g.us": RegisteredGroup(name="Main", folder="main", requires_trigger=False),
        "team@g.us": RegisteredGroup(name="Team", folder="team", requires_trigger=False),
    }
    loop = MessagePollLoop(store, groups, queue, poll_interval=0.01)

    # main 已有活跃容器
    queue.set_active("main@g.us")

    store.store(Message("1", "main@g.us", "u1", "Alice", "继续上一个任务", ts(0)))
    store.store(Message("2", "team@g.us", "u2", "Bob", "新任务", ts(1)))

    actions = loop._poll_once()
    print("  main 有活跃容器 → 管道; team 无活跃容器 → 入队:")
    for a in actions:
        print(f"    [{a['group']}] {a['action']} ({a.get('count', 0)} msgs)")
    for log in queue.log:
        print(log)
    print()


# ---------------------------------------------------------------------------
# Demo 4: 启动恢复
# ---------------------------------------------------------------------------

def demo_recovery():
    print("=" * 60)
    print("Demo 4: 启动恢复 — 进程重启后扫描未处理消息并入队")
    print("=" * 60)

    store = MessageStore()
    queue = MockQueue()
    groups = {
        "main@g.us": RegisteredGroup(name="Main", folder="main", requires_trigger=False),
        "team@g.us": RegisteredGroup(name="Team", folder="team", requires_trigger=False),
    }

    # 模拟崩溃前的状态：main 处理到 ts(5)，team 只处理到 ts(2)
    store.store(Message("1", "team@g.us", "u1", "Alice", "消息1", ts(3)))
    store.store(Message("2", "team@g.us", "u2", "Bob", "消息2", ts(4)))

    loop = MessagePollLoop(store, groups, queue, poll_interval=0.01)
    loop.last_agent_timestamp["main@g.us"] = ts(5)
    loop.last_agent_timestamp["team@g.us"] = ts(2)

    print("  崩溃前游标: main→ts(5), team→ts(2)")
    print("  team 有 2 条未处理消息...")
    recovered = loop.recover_pending()
    print(f"  恢复结果: {recovered}")
    for log in queue.log:
        print(log)
    print()


# ---------------------------------------------------------------------------
# Demo 5: XML 消息格式
# ---------------------------------------------------------------------------

def demo_xml_format():
    print("=" * 60)
    print("Demo 5: XML 消息格式 — router.ts:formatMessages")
    print("=" * 60)

    messages = [
        Message("1", "g@g.us", "u1", "Alice", "@Andy 帮我查 <script> 注入", ts(0)),
        Message("2", "g@g.us", "u2", "Bob", '附加信息: "引号测试"', ts(1)),
    ]
    xml = format_messages(messages)
    print(xml)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("NanoClaw 消息轮询主循环 — 机制 Demo\n")
    demo_basic_polling()
    demo_accumulation()
    demo_pipe_vs_enqueue()
    demo_recovery()
    demo_xml_format()
    print("✓ 所有 demo 完成")
