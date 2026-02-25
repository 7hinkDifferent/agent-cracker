"""NanoClaw 组群队列 — Demo

演示 GroupQueue 的核心机制：
  1. 全局并发控制（MAX_CONCURRENT=3，demo 缩小）
  2. 指数退避重试（5s → 10s → 20s → 40s → 80s）
  3. 排水机制（task 优先 → message → waiting queue）
  4. 管道机制（活跃容器接收后续消息）
  5. Shutdown 优雅关闭

运行: uv run python main.py
"""

from __future__ import annotations

import asyncio
import time

from queue import GroupQueue, QueuedTask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

events: list[dict] = []


def event_logger(event: dict) -> None:
    events.append(event)
    tag = event.get("type", "?")
    group = event.get("group", "")
    extra = {k: v for k, v in event.items() if k not in ("type", "group")}
    print(f"    [{tag:18s}] {group}  {extra if extra else ''}")


async def mock_process(group_jid: str, delay: float = 0.1, fail: bool = False) -> bool:
    """Simulate container processing."""
    await asyncio.sleep(delay)
    return not fail


# ---------------------------------------------------------------------------
# Demo 1: 全局并发控制
# ---------------------------------------------------------------------------

async def demo_concurrency():
    print("=" * 60)
    print("Demo 1: 全局并发控制 — 同时最多 3 个容器")
    print("=" * 60)

    events.clear()
    q = GroupQueue(
        max_concurrent=3,
        process_messages_fn=lambda jid: mock_process(jid, delay=0.2),
        on_event=event_logger,
    )

    # Enqueue 5 groups with event loop yields between each.
    # This lets _run_for_group start and increment active_count
    # before the next enqueue, so the concurrency limit takes effect.
    for i in range(5):
        q.enqueue_message_check(f"group-{i}@g.us")
        await asyncio.sleep(0)  # yield so scheduled coroutine starts

    await asyncio.sleep(0.5)  # Let all complete + drain
    starts = [e for e in events if e["type"] == "start"]
    queued = [e for e in events if e["type"] == "queued"]
    print(f"\n  前 3 个组立即启动，后 2 个进入等待队列")
    print(f"  start 事件: {len(starts)}, queued 事件: {len(queued)}")
    print(f"  最终全部 5 个组完成处理")
    print()


# ---------------------------------------------------------------------------
# Demo 2: 指数退避重试
# ---------------------------------------------------------------------------

async def demo_retry():
    print("=" * 60)
    print("Demo 2: 指数退避重试 — 失败后 delay 翻倍")
    print("=" * 60)

    events.clear()
    call_count = 0

    async def failing_process(jid: str) -> bool:
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return False  # Fail first 3 times
        return True

    q = GroupQueue(
        max_concurrent=5,
        process_messages_fn=failing_process,
        on_event=event_logger,
    )

    q.enqueue_message_check("retry-test@g.us")

    # Wait for retries (demo uses real delays, but they're scaled by BASE_RETRY_MS)
    # In the real implementation: 5s → 10s → 20s
    # For demo we just show the scheduling events
    await asyncio.sleep(0.3)

    retries = [e for e in events if e["type"] == "retry_scheduled"]
    print(f"\n  重试调度事件:")
    for r in retries:
        print(f"    第 {r['retry']} 次, 延迟 {r['delay_s']}s")
    print()


# ---------------------------------------------------------------------------
# Demo 3: 排水机制 — Task 优先于 Message
# ---------------------------------------------------------------------------

async def demo_drain():
    print("=" * 60)
    print("Demo 3: 排水机制 — Task 优先于 Message")
    print("=" * 60)

    events.clear()
    q = GroupQueue(
        max_concurrent=1,  # Force serialization
        process_messages_fn=lambda jid: mock_process(jid, delay=0.1),
        on_event=event_logger,
    )

    jid = "drain-test@g.us"
    # Start first container
    q.enqueue_message_check(jid)

    # While first is running, queue a task AND a message
    await asyncio.sleep(0.01)

    async def my_task():
        await asyncio.sleep(0.05)

    q.enqueue_task(jid, QueuedTask(id="task-1", group_jid=jid, fn=my_task))
    q.enqueue_message_check(jid)

    await asyncio.sleep(0.5)

    # Verify: task ran before drain message
    order = [e["type"] for e in events if e["type"] in ("start", "task_start", "finish")]
    print(f"\n  执行顺序: {' → '.join(order)}")
    print("  （task_start 在第二个 start 之前 = task 优先）")
    print()


# ---------------------------------------------------------------------------
# Demo 4: 管道机制 — 活跃容器接收后续消息
# ---------------------------------------------------------------------------

async def demo_pipe():
    print("=" * 60)
    print("Demo 4: 管道机制 — 活跃容器直接接收后续消息")
    print("=" * 60)

    events.clear()
    q = GroupQueue(max_concurrent=5, on_event=event_logger)

    jid = "pipe-test@g.us"

    # No active container → send_message returns False
    result1 = q.send_message(jid, "<messages>first</messages>")
    print(f"\n  无活跃容器: send_message → {result1}")

    # Simulate active container
    state = q._get(jid)
    state.active = True
    state.group_folder = "pipe-test"

    result2 = q.send_message(jid, "<messages>second</messages>")
    print(f"  有活跃容器: send_message → {result2}")

    # Task container rejects messages
    state.is_task_container = True
    result3 = q.send_message(jid, "<messages>third</messages>")
    print(f"  Task 容器: send_message → {result3} (task 容器拒绝管道)")
    state.active = False
    print()


# ---------------------------------------------------------------------------
# Demo 5: idle 通知 + close sentinel
# ---------------------------------------------------------------------------

async def demo_idle():
    print("=" * 60)
    print("Demo 5: Idle 通知 — 空闲容器被 pending task 抢占")
    print("=" * 60)

    events.clear()
    q = GroupQueue(max_concurrent=5, on_event=event_logger)

    jid = "idle-test@g.us"
    state = q._get(jid)
    state.active = True
    state.group_folder = "idle-test"

    # Notify idle (no pending tasks → just mark)
    q.notify_idle(jid)
    print(f"\n  notify_idle (无 pending task): idle_waiting={state.idle_waiting}")

    # Now add a pending task and notify idle → should trigger close
    async def task_fn():
        pass
    state.pending_tasks.append(QueuedTask(id="t1", group_jid=jid, fn=task_fn))
    q.notify_idle(jid)
    close_events = [e for e in events if e["type"] == "close_stdin"]
    print(f"  notify_idle (有 pending task): close_stdin 事件={len(close_events)}")
    state.active = False
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("NanoClaw 组群队列 — 机制 Demo\n")
    await demo_concurrency()
    await demo_retry()
    await demo_drain()
    await demo_pipe()
    await demo_idle()
    print("✓ 所有 demo 完成")


if __name__ == "__main__":
    asyncio.run(main())
