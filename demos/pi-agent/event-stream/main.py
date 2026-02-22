"""
Pi-Agent EventStream Demo

演示 pi-agent 的异步事件流模式：
  producer 后台生成事件，consumer 用 async for 实时消费

场景：模拟 Agent 执行一个编码任务
  1. Producer 推送一系列事件（thinking → tool_start → tool_end → text → agent_end）
  2. Consumer 逐个消费事件并打印
  3. 最后通过 result() 获取聚合结果

原实现: packages/ai/src/utils/event-stream.ts
运行: python main.py
"""

import asyncio
from event_stream import EventStream, AgentEvent


async def agent_producer(stream: EventStream[AgentEvent, str]) -> None:
    """模拟 Agent 执行：按步骤推送事件"""
    steps = [
        AgentEvent("thinking", "分析用户需求：需要实现一个排序函数..."),
        AgentEvent("tool_start", "read src/utils.py"),
        AgentEvent("tool_end", "文件内容已读取（42 行）"),
        AgentEvent("thinking", "发现已有 bubble_sort，需要替换为 quick_sort..."),
        AgentEvent("tool_start", "edit src/utils.py"),
        AgentEvent("tool_end", "已将 bubble_sort 替换为 quick_sort"),
        AgentEvent("text", "我已经将 `bubble_sort` 替换为更高效的 `quick_sort` 实现。"),
        AgentEvent("tool_start", "bash python -m pytest tests/"),
        AgentEvent("tool_end", "所有 12 个测试通过"),
        AgentEvent("text", "测试全部通过，排序函数优化完成。"),
        AgentEvent("agent_end", "任务完成"),
    ]

    for step in steps:
        await asyncio.sleep(0.3)  # 模拟处理耗时
        stream.push(step)


async def main():
    print("=" * 60)
    print("Pi-Agent EventStream Demo")
    print("异步事件流：producer-consumer 解耦 + demand-driven delivery")
    print("=" * 60)

    # ── 场景 1：基本 async for 消费 ─────────────────────────

    print("\n── 场景 1：async for 实时消费事件 ──\n")

    stream: EventStream[AgentEvent, str] = EventStream(
        is_complete=lambda e: e.type == "agent_end",
        extract_result=lambda e: e.data,
    )

    # 启动 producer（后台运行）
    producer_task = asyncio.create_task(agent_producer(stream))

    # Consumer：用 async for 逐个消费
    event_count = 0
    async for event in stream:
        event_count += 1
        icon = {
            "thinking": "🧠",
            "tool_start": "🔧",
            "tool_end": "✅",
            "text": "💬",
            "agent_end": "🏁",
        }.get(event.type, "·")
        print(f"  {icon} [{event.type:>10}] {event.data}")

    await producer_task

    # 获取聚合结果
    result = await stream.result()
    print(f"\n  共消费 {event_count} 个事件，最终结果: {result}")

    # ── 场景 2：producer 先完成，consumer 后消费 ──────────────

    print("\n── 场景 2：producer 先 push 完毕，consumer 后消费（队列缓冲）──\n")

    stream2: EventStream[AgentEvent, str] = EventStream(
        is_complete=lambda e: e.type == "agent_end",
        extract_result=lambda e: e.data,
    )

    # Producer 同步 push 全部事件（无 consumer 等待，全部入队）
    stream2.push(AgentEvent("thinking", "快速分析..."))
    stream2.push(AgentEvent("text", "已完成分析"))
    stream2.push(AgentEvent("agent_end", "done"))

    # Consumer 后消费（从队列取）
    count = 0
    async for event in stream2:
        count += 1
        print(f"  [{event.type:>10}] {event.data}")

    print(f"\n  消费了 {count} 个缓冲事件")

    # ── 场景 3：演示 end() 强制终止 ───────────────────────────

    print("\n── 场景 3：end() 强制终止流 ──\n")

    stream3: EventStream[AgentEvent, str] = EventStream(
        is_complete=lambda e: e.type == "agent_end",
        extract_result=lambda e: e.data,
    )

    async def slow_producer(s: EventStream[AgentEvent, str]) -> None:
        for i in range(10):
            await asyncio.sleep(0.2)
            s.push(AgentEvent("text", f"消息 #{i+1}"))

    async def abort_after(s: EventStream[AgentEvent, str], delay: float) -> None:
        await asyncio.sleep(delay)
        print("  ⛔ 调用 end()，强制终止流")
        s.end("用户中断")

    producer = asyncio.create_task(slow_producer(stream3))
    aborter = asyncio.create_task(abort_after(stream3, 0.7))

    async for event in stream3:
        print(f"  [{event.type:>10}] {event.data}")

    result3 = await stream3.result()
    print(f"  终止结果: {result3}")

    await producer
    await aborter

    # ── 总结 ─────────────────────────────────────────────────

    print(f"\n{'=' * 60}")
    print("核心要点:")
    print("  1. push() 有 waiter → 直接唤醒，无 → 入队（demand-driven）")
    print("  2. async for 消费：队列优先，空则等待")
    print("  3. end() 唤醒所有 waiter，优雅终止")
    print("  4. result() 独立等待聚合结果，不影响迭代")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
