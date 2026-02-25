"""
Mini-NanoClaw — 串联 MVP + 平台组件的最小完整 WhatsApp Agent

通过 import 兄弟 MVP/平台 demo 模块实现组合：
1. channel-abstraction  → WhatsAppChannel (通道接收/发送)
2. sqlite-persistence   → NanoClawDB (持久化层)
3. message-poll-loop    → MessagePollLoop (消息轮询编排)
4. group-queue          → GroupQueue (并发控制)
5. container-spawn      → spawn_mock_agent (容器生命周期)
6. task-scheduler       → TaskStore + SchedulerLoop (定时任务)

演示完整链路：
  Channel → Store → Poll → Queue → Container → Parse → Respond

Run: uv run --with croniter python main.py
"""

import asyncio
import json
import os
import sys
import time
import uuid

# ── 添加兄弟 demo 目录到 import 路径 ─────────────────────────────

_DEMO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _subdir in (
    "channel-abstraction",
    "sqlite-persistence",
    "message-poll-loop",
    "group-queue",
    "container-spawn",
    "task-scheduler",
):
    _path = os.path.join(_DEMO_DIR, _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)

# ── 从兄弟 demo 导入组件 ────────────────────────────────────────

# 组件 1: Channel 通道层
from channel import WhatsAppChannel, NewMessage as ChanMessage, route_outbound

# 组件 2: SQLite 持久化层
from persistence import NanoClawDB, NewMessage as DbMessage

# 组件 3: 消息轮询主循环
from loop import MessagePollLoop, MessageStore, Message as PollMessage, RegisteredGroup

# 组件 4: 组群并发队列
from queue import GroupQueue

# 组件 5: 容器启动与输出解析
from spawner import spawn_mock_agent, ContainerInput, ContainerOutput, SentinelParser

# 组件 6: 定时任务调度
from scheduler import TaskStore, SchedulerLoop, ScheduledTask, ScheduleType, ContextMode

# ── 配置 ────────────────────────────────────────────────────────

ASSISTANT_NAME = "Andy"
POLL_INTERVAL = 0.3  # Demo: 300ms (原实现: 2000ms)
TRIGGER_PATTERN = r"(?:^|\s)@Andy\b"


# ── 桥接层: 连接各组件的数据类型转换 ─────────────────────────────

def chan_to_db_msg(msg: ChanMessage) -> DbMessage:
    """Channel 消息 → DB 消息"""
    return DbMessage(
        id=msg.id, chat_jid=msg.chat_jid, sender=msg.sender,
        sender_name=msg.sender_name, content=msg.content,
        timestamp=msg.timestamp, is_from_me=msg.is_from_me,
        is_bot_message=msg.is_bot_message,
    )


def db_to_poll_msg(msg: DbMessage) -> PollMessage:
    """DB 消息 → Poll 消息"""
    return PollMessage(
        id=msg.id, chat_jid=msg.chat_jid, sender=msg.sender,
        sender_name=msg.sender_name, content=msg.content,
        timestamp=msg.timestamp, is_from_me=msg.is_from_me,
    )


# ── NanoClaw Orchestrator: 组合所有组件 ─────────────────────────

class MiniNanoClaw:
    """最小 NanoClaw 编排器，组合 6 个 MVP/平台组件。

    对应原实现 src/index.ts (498 行) 中的状态管理和组件连接。
    """

    def __init__(self):
        # 组件 1: Channel
        self.channel = WhatsAppChannel(on_message=self._on_inbound)
        self.channel.connect()

        # 组件 2: SQLite
        self.db = NanoClawDB(":memory:")

        # 组件 3: Poll loop 的 MessageStore (桥接到 DB)
        self.msg_store = MessageStore()

        # 组件 4: Group queue
        self.group_queue = GroupQueue(
            max_concurrent=3,
            process_messages_fn=self._process_group,
            on_event=self._on_queue_event,
        )

        # 组件 5: Container spawning (handled in _process_group)

        # 组件 6: Task scheduler
        self.task_store = TaskStore()
        self.scheduler = SchedulerLoop(
            store=self.task_store,
            runner=lambda task: f"Executed: {task.prompt[:50]}",
        )

        # Registered groups
        self.groups: dict[str, RegisteredGroup] = {}

        # Session tracking
        self.sessions: dict[str, str] = {}

        # Event log for demo observability
        self.events: list[str] = []

    def register_group(self, jid: str, name: str, folder: str, is_main: bool = False):
        """注册群组"""
        self.groups[jid] = RegisteredGroup(
            name=name, folder=folder,
            requires_trigger=not is_main,
        )
        self.db.store_chat_metadata(jid, "1970-01-01T00:00:00Z", name, "whatsapp", True)
        self._log(f"注册群组: {name} ({jid}), main={is_main}")

    def _log(self, text: str):
        self.events.append(text)

    # ── Channel 回调 ─────────────────────────────────────────────

    def _on_inbound(self, chat_jid: str, msg: ChanMessage):
        """Channel 收到消息 → 存储 DB + Poll Store"""
        # 存入 SQLite
        self.db.store_message(chan_to_db_msg(msg))

        # 存入 Poll store (内存)
        self.msg_store.store(db_to_poll_msg(
            DbMessage(id=msg.id, chat_jid=msg.chat_jid, sender=msg.sender,
                      sender_name=msg.sender_name, content=msg.content,
                      timestamp=msg.timestamp, is_from_me=msg.is_from_me)
        ))
        self._log(f"收到消息: [{msg.sender_name}] {msg.content[:40]}")

    # ── Queue 回调 ───────────────────────────────────────────────

    def _on_queue_event(self, event: dict):
        etype = event.get("type", "")
        group = event.get("group", "?")
        if etype in ("start", "finish", "piped"):
            self._log(f"Queue: {etype} group={group}")

    # ── 容器处理 ─────────────────────────────────────────────────

    async def _process_group(self, group_jid: str) -> bool:
        """处理一个组群的消息 — 启动 mock 容器。

        对应原实现的 processGroupMessages → runAgent → runContainerAgent 链路。
        """
        group = self.groups.get(group_jid)
        if not group:
            return False

        # 获取待处理消息
        msgs, _ = self.db.get_new_messages(
            [group_jid],
            self.db.get_router_state(f"cursor:{group_jid}") or "1970-01-01T00:00:00Z",
        )
        if not msgs:
            return True  # No messages to process

        # 构造 prompt
        prompt_parts = [f"[{m.sender_name}] {m.content}" for m in msgs]
        prompt = "\n".join(prompt_parts)

        self._log(f"处理 {group.name}: {len(msgs)} 条消息")

        # Mock 容器执行 (不实际 spawn, 直接模拟结果)
        session_id = self.sessions.get(group.folder)
        container_input = ContainerInput(
            prompt=prompt,
            group_folder=group.folder,
            chat_jid=group_jid,
            is_main=not group.requires_trigger,
            session_id=session_id,
        )

        # 模拟容器响应
        response = f"{ASSISTANT_NAME}: 已处理 {len(msgs)} 条消息。最新的是: {msgs[-1].content[:30]}"

        # 更新 session
        new_session = f"sess-{uuid.uuid4().hex[:8]}"
        self.sessions[group.folder] = new_session

        # 更新游标
        if msgs:
            self.db.set_router_state(f"cursor:{group_jid}", msgs[-1].timestamp)

        # 通过 Channel 发送回复
        try:
            self.channel.send_message(group_jid, response)
            self._log(f"回复 {group.name}: {response[:50]}")
        except Exception as e:
            self._log(f"发送失败: {e}")

        # 存储 bot 响应到 DB
        self.db.store_message(DbMessage(
            id=uuid.uuid4().hex[:12], chat_jid=group_jid,
            sender="bot", sender_name=ASSISTANT_NAME,
            content=response,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            is_from_me=True, is_bot_message=True,
        ))

        return True

    # ── 主循环 ───────────────────────────────────────────────────

    async def run_poll_cycle(self, iterations: int = 1):
        """运行 N 次轮询周期"""
        poll_loop = MessagePollLoop(
            store=self.msg_store,
            groups=self.groups,
            queue=self.group_queue,
            poll_interval=POLL_INTERVAL,
            assistant_name=ASSISTANT_NAME,
        )
        await poll_loop.run(max_iterations=iterations)


# ── Demo 场景 ────────────────────────────────────────────────────

async def demo_full_pipeline():
    """Demo 1: 完整消息处理链路 Channel → Store → Poll → Queue → Container → Respond"""
    print("=" * 60)
    print("Demo 1: 完整消息处理链路")
    print("=" * 60)

    claw = MiniNanoClaw()

    # 注册群组
    claw.register_group("main@g.us", "Main Group", "main", is_main=True)
    claw.register_group("team@g.us", "Team Group", "team", is_main=False)

    # 模拟 WhatsApp 收到消息
    from channel import make_message
    msg1 = make_message("main@g.us", "user1", "Alice", "帮我写个函数")
    msg1.timestamp = "2026-01-01T10:00:01Z"
    claw.channel.simulate_inbound(msg1)

    msg2 = make_message("team@g.us", "user2", "Bob", "@Andy 查一下天气")
    msg2.timestamp = "2026-01-01T10:00:02Z"
    claw.channel.simulate_inbound(msg2)

    # 运行一次轮询
    await claw.run_poll_cycle(iterations=1)
    # 让 queue 处理完成
    await asyncio.sleep(0.5)

    # 打印事件日志
    print("\n  事件链:")
    for i, event in enumerate(claw.events, 1):
        print(f"    {i:2d}. {event}")

    # 验证回复
    sent = claw.channel.sent_messages
    print(f"\n  Channel 发送的回复 ({len(sent)}):")
    for jid, text in sent:
        print(f"    → {jid}: {text[:60]}")

    # 验证 DB 状态
    chats = claw.db.get_all_chats()
    print(f"\n  DB 中的 chat ({len(chats)}):")
    for c in chats:
        print(f"    {c.jid}: {c.name}")

    print()


async def demo_trigger_filter():
    """Demo 2: 触发词过滤 — 非 main 群需要 @Andy"""
    print("=" * 60)
    print("Demo 2: 触发词过滤 — 非 main 群需要 @Andy")
    print("=" * 60)

    claw = MiniNanoClaw()
    claw.register_group("main@g.us", "Main", "main", is_main=True)
    claw.register_group("team@g.us", "Team", "team", is_main=False)

    from channel import make_message

    # main 群: 无需触发词
    m1 = make_message("main@g.us", "u1", "Alice", "直接对话无需触发词")
    m1.timestamp = "2026-01-01T10:00:01Z"
    claw.channel.simulate_inbound(m1)

    # team 群: 没有 @Andy → 应该跳过
    m2 = make_message("team@g.us", "u2", "Bob", "普通聊天不触发")
    m2.timestamp = "2026-01-01T10:00:02Z"
    claw.channel.simulate_inbound(m2)

    await claw.run_poll_cycle(iterations=1)
    await asyncio.sleep(0.5)

    sent_count = len(claw.channel.sent_messages)
    print(f"\n  发送回复数: {sent_count} (预期 1: 只有 main 群)")

    # 现在 team 群发带 @Andy 的消息
    m3 = make_message("team@g.us", "u2", "Bob", "@Andy 帮我查天气")
    m3.timestamp = "2026-01-01T10:00:03Z"
    claw.channel.simulate_inbound(m3)

    await claw.run_poll_cycle(iterations=1)
    await asyncio.sleep(0.5)

    sent_count_2 = len(claw.channel.sent_messages)
    print(f"  第二轮回复数: {sent_count_2} (预期 2: main + team 各一)")

    print("\n  事件:")
    for e in claw.events:
        print(f"    {e}")
    print()


async def demo_concurrent_groups():
    """Demo 3: 并发控制 — 多个群组同时处理"""
    print("=" * 60)
    print("Demo 3: 并发控制 — max_concurrent=2")
    print("=" * 60)

    claw = MiniNanoClaw()
    claw.group_queue._max_concurrent = 2  # 限制并发为 2

    # 注册 4 个群组
    for i in range(4):
        jid = f"group{i}@g.us"
        claw.register_group(jid, f"Group-{i}", f"group{i}", is_main=True)

    from channel import make_message

    # 所有群组同时收到消息
    for i in range(4):
        jid = f"group{i}@g.us"
        msg = make_message(jid, f"u{i}", f"User{i}", f"消息来自 Group-{i}")
        msg.timestamp = f"2026-01-01T10:00:0{i+1}Z"
        claw.channel.simulate_inbound(msg)

    # 运行轮询
    await claw.run_poll_cycle(iterations=1)
    await asyncio.sleep(1.0)

    # 检查事件
    starts = [e for e in claw.events if "Queue: start" in e]
    finishes = [e for e in claw.events if "Queue: finish" in e]
    sent = claw.channel.sent_messages

    print(f"\n  注册群组: 4")
    print(f"  并发上限: 2")
    print(f"  Queue starts: {len(starts)}")
    print(f"  Queue finishes: {len(finishes)}")
    print(f"  回复发送: {len(sent)}")
    print(f"\n  事件链:")
    for e in claw.events:
        if "Queue" in e or "处理" in e or "回复" in e:
            print(f"    {e}")
    print()


async def demo_persistence():
    """Demo 4: 持久化验证 — 消息、游标、session 都持久化"""
    print("=" * 60)
    print("Demo 4: 持久化 — SQLite 状态验证")
    print("=" * 60)

    claw = MiniNanoClaw()
    claw.register_group("main@g.us", "Main", "main", is_main=True)

    from channel import make_message

    # 发送几条消息
    for i in range(3):
        msg = make_message("main@g.us", "u1", "Alice", f"消息 {i+1}")
        msg.timestamp = f"2026-01-01T10:00:0{i+1}Z"
        claw.channel.simulate_inbound(msg)

    await claw.run_poll_cycle(iterations=1)
    await asyncio.sleep(0.5)

    # 验证 DB 持久化状态
    print("\n  消息存储:")
    user_msgs, _ = claw.db.get_new_messages(["main@g.us"], "1970-01-01T00:00:00Z")
    bot_count = claw.db._conn.execute(
        "SELECT COUNT(*) as c FROM messages WHERE is_bot_message = 1"
    ).fetchone()["c"]
    print(f"    用户消息 (过滤后): {len(user_msgs)}")
    print(f"    Bot 消息 (被过滤): {bot_count}")

    # 游标状态
    cursor = claw.db.get_router_state("cursor:main@g.us")
    print(f"\n  游标状态:")
    print(f"    cursor:main@g.us = {cursor}")

    # Session 状态
    session = claw.sessions.get("main")
    print(f"\n  Session 状态:")
    print(f"    main → {session}")

    print()


async def demo_scheduled_task():
    """Demo 5: 定时任务 — 从创建到执行的完整流程"""
    print("=" * 60)
    print("Demo 5: 定时任务 — Scheduler + Queue 联动")
    print("=" * 60)

    claw = MiniNanoClaw()
    claw.register_group("main@g.us", "Main", "main", is_main=True)

    # 创建一个已过期的 once 任务 (立即触发)
    from scheduler import make_task_id
    task = ScheduledTask(
        id=make_task_id(),
        group_folder="main",
        chat_jid="main@g.us",
        prompt="每日天气汇报",
        schedule_type=ScheduleType.ONCE,
        schedule_value="2026-01-01T00:00:00Z",
        context_mode=ContextMode.ISOLATED,
        next_run="2026-01-01T00:00:00Z",  # 已过期 → 立即执行
    )
    claw.task_store.add_task(task)

    # 创建一个 interval 任务
    task2 = ScheduledTask(
        id=make_task_id(),
        group_folder="main",
        chat_jid="main@g.us",
        prompt="代码审查提醒",
        schedule_type=ScheduleType.INTERVAL,
        schedule_value="3600000",  # 1 hour
        context_mode=ContextMode.GROUP,
        next_run="2025-01-01T00:00:00Z",  # 已过期
    )
    claw.task_store.add_task(task2)

    # 运行一次 scheduler poll
    results = claw.scheduler.poll()

    print(f"\n  创建任务: 2 (once + interval)")
    print(f"  Scheduler poll 结果: {len(results)} 个任务执行")
    for task_id, result in results:
        t = claw.task_store.get_task(task_id)
        status = t.status.value if t else "?"
        next_run = t.next_run[:19] if t and t.next_run else "None"
        print(f"    {task_id}: status={status}, next_run={next_run}")
        print(f"      result: {result[:60]}")

    # 验证 once 任务已完成
    once_task = claw.task_store.get_task(task.id)
    interval_task = claw.task_store.get_task(task2.id)
    print(f"\n  Once 任务: status={once_task.status.value} (预期: completed)")
    print(f"  Interval 任务: status={interval_task.status.value}, 下次运行已更新")
    print()


# ── 主入口 ───────────────────────────────────────────────────────

async def main():
    print("Mini-NanoClaw — 串联 6 个组件的最小完整 WhatsApp Agent\n")
    print("  组件:")
    print("    1. channel-abstraction  → WhatsAppChannel (通道)")
    print("    2. sqlite-persistence   → NanoClawDB (持久化)")
    print("    3. message-poll-loop    → MessagePollLoop (轮询)")
    print("    4. group-queue          → GroupQueue (并发)")
    print("    5. container-spawn      → ContainerInput/Output (容器)")
    print("    6. task-scheduler       → TaskStore + Scheduler (调度)")
    print()

    await demo_full_pipeline()
    await demo_trigger_filter()
    await demo_concurrent_groups()
    await demo_persistence()
    await demo_scheduled_task()

    print("=" * 60)
    print("✓ Mini-NanoClaw 所有 demo 完成")
    print("=" * 60)
    print()
    print("  完整链路验证:")
    print("    Channel → DB → Poll → Queue → Container → Response → Channel")
    print("  平台机制验证:")
    print("    SQLite 持久化 | 触发词过滤 | 并发控制 | 定时任务")


if __name__ == "__main__":
    asyncio.run(main())
