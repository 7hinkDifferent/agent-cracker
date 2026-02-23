"""
Pi-Agent Session Loop Demo

复现 Pi-Agent 的双层循环 + 消息队列架构：
- 内层循环：LLM → tool call → 结果回填
- 外层循环：follow-up 消息排队处理
- Steering 中断：用户消息打断当前 tool 执行
- EventStream：异步事件流（async iterator）

Run: uv run python main.py
"""

import asyncio
from loop import (
    SessionLoop, MockLlm, MessageQueue, EventStream,
    Message, ToolDef, Event, EventType,
)


# ── Demo 工具 ─────────────────────────────────────────────────────

def make_tools() -> dict[str, ToolDef]:
    """创建 demo 用的 mock 工具。"""
    return {
        "read": ToolDef(
            name="read",
            description="Read a file",
            execute=lambda args: f"Content of {args.get('path', '?')}: Hello World!",
        ),
        "bash": ToolDef(
            name="bash",
            description="Execute a command",
            execute=lambda args: f"$ {args.get('command', '?')}\nOutput: OK",
        ),
        "edit": ToolDef(
            name="edit",
            description="Edit a file",
            execute=lambda args: f"Edited {args.get('path', '?')}: replaced text",
        ),
    }


# ── 事件打印器 ────────────────────────────────────────────────────

async def print_events(events: EventStream, prefix: str = ""):
    """消费并打印事件流。"""
    async for event in events:
        if event.type == EventType.MESSAGE_START:
            print(f"{prefix}  ▸ LLM thinking...")
        elif event.type == EventType.MESSAGE_END:
            content = event.data.get("content", "")
            has_tools = event.data.get("has_tool_calls", False)
            suffix = " [+ tool calls]" if has_tools else ""
            print(f"{prefix}  ◂ LLM: \"{content}\"{suffix}")
        elif event.type == EventType.TOOL_START:
            tool = event.data["tool"]
            args = event.data["args"]
            print(f"{prefix}  ⚙ Tool: {tool}({args})")
        elif event.type == EventType.TOOL_END:
            result = event.data["result"]
            print(f"{prefix}  ✓ Result: {result}")
        elif event.type == EventType.STEERING_INTERRUPT:
            count = event.data["count"]
            skipped = event.data["skipped_results"]
            print(f"{prefix}  ⚡ STEERING INTERRUPT: {count} message(s), skipped {skipped} tool result(s)")
        elif event.type == EventType.LOOP_END:
            total = event.data["total_messages"]
            print(f"{prefix}  ■ Loop ended ({total} messages total)")


# ── Demo 1: 基本 tool call 循环 ──────────────────────────────────

async def demo_basic_loop():
    """演示基本的 LLM → tool call → 结果回填循环。"""
    print("=" * 60)
    print("Demo 1: Basic Tool Call Loop (内层循环)")
    print("=" * 60)
    print()

    tools = make_tools()
    events = EventStream()
    queue = MessageQueue()

    # 预设 LLM 脚本：
    # Turn 1: 调用 read 工具
    # Turn 2: 基于读取结果，调用 edit 工具
    # Turn 3: 完成（无 tool call）
    llm = MockLlm([
        Message(
            role="assistant",
            content="Let me read the file first.",
            tool_calls=[{"id": "call_1", "name": "read", "arguments": {"path": "main.py"}}],
        ),
        Message(
            role="assistant",
            content="Now I'll edit it.",
            tool_calls=[{"id": "call_2", "name": "edit", "arguments": {"path": "main.py", "search": "old", "replace": "new"}}],
        ),
        Message(
            role="assistant",
            content="Done! I've updated main.py.",
        ),
    ])

    loop = SessionLoop(llm, tools, queue, events)

    # 并发：运行循环 + 打印事件
    await asyncio.gather(
        loop.run(Message(role="user", content="Please update main.py")),
        print_events(events, prefix=""),
    )

    print(f"\n  Message history: {len(loop.messages)} messages")
    for i, msg in enumerate(loop.messages):
        role = msg.role
        content = msg.content[:50]
        extra = " [+tools]" if msg.tool_calls else ""
        print(f"    [{i}] {role:10s} {content}{extra}")


# ── Demo 2: Follow-up 外层循环 ───────────────────────────────────

async def demo_followup():
    """演示 follow-up 消息触发外层循环继续执行。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Follow-up Queue (外层循环)")
    print("=" * 60)
    print()

    tools = make_tools()
    events = EventStream()
    queue = MessageQueue()

    # 预设脚本：初始任务 + follow-up 任务
    llm = MockLlm([
        # 初始任务的响应
        Message(
            role="assistant",
            content="Reading the file.",
            tool_calls=[{"id": "call_1", "name": "read", "arguments": {"path": "app.py"}}],
        ),
        Message(
            role="assistant",
            content="Here's app.py content.",
        ),
        # follow-up 任务的响应
        Message(
            role="assistant",
            content="Running tests now.",
            tool_calls=[{"id": "call_2", "name": "bash", "arguments": {"command": "pytest"}}],
        ),
        Message(
            role="assistant",
            content="All tests passed!",
        ),
    ])

    loop = SessionLoop(llm, tools, queue, events)

    # 在循环启动前加入 follow-up
    queue.add_followup(Message(role="user", content="Also run the tests"))

    await asyncio.gather(
        loop.run(Message(role="user", content="Read app.py")),
        print_events(events, prefix=""),
    )

    print(f"\n  Message history: {len(loop.messages)} messages")
    print(f"  Follow-up processed: the outer loop ran twice")


# ── Demo 3: Steering 中断 ────────────────────────────────────────

async def demo_steering():
    """演示 steering 消息中断当前 tool 执行。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Steering Interrupt (中断机制)")
    print("=" * 60)
    print()

    tools = make_tools()
    events = EventStream()
    queue = MessageQueue()

    # 预设脚本：
    # Turn 1: Agent 想执行 bash 命令
    # (steering 中断：用户说"停下来")
    # Turn 2: Agent 看到 steering，改变行为
    llm = MockLlm([
        Message(
            role="assistant",
            content="I'll run the deployment script.",
            tool_calls=[{"id": "call_1", "name": "bash", "arguments": {"command": "deploy.sh"}}],
        ),
        # steering 后 LLM 重新响应
        Message(
            role="assistant",
            content="OK, I've stopped. The deployment was cancelled.",
        ),
    ])

    loop = SessionLoop(llm, tools, queue, events)

    # 模拟：在 tool 执行前就有 steering 消息
    # （实际场景中是用户在 tool 执行过程中输入）
    queue.add_steering(Message(role="user", content="Stop! Don't deploy yet."))

    await asyncio.gather(
        loop.run(Message(role="user", content="Deploy the app")),
        print_events(events, prefix=""),
    )

    print(f"\n  Message history: {len(loop.messages)} messages")
    print(f"  Key: tool result was SKIPPED, steering message injected instead")
    print(f"  This changed the LLM's next response direction")


# ── Demo 4: Abort 终止 ───────────────────────────────────────────

async def demo_abort():
    """演示 abort 强制终止循环。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Abort Signal (强制终止)")
    print("=" * 60)
    print()

    events = EventStream()
    queue = MessageQueue()

    # 用 tool 执行触发 abort（确定性中断）
    loop_ref: list[SessionLoop] = []  # 引用容器

    def abort_on_step2(args):
        """Step 2 的 tool 执行中触发 abort。"""
        loop_ref[0].abort()
        return f"$ {args.get('command', '?')}\nAbort triggered during execution!"

    tools = {
        "bash": ToolDef(
            name="bash",
            description="Execute a command",
            execute=lambda args: f"$ {args.get('command', '?')}\nOutput: OK",
        ),
        "danger": ToolDef(
            name="danger",
            description="Dangerous command that triggers abort",
            execute=abort_on_step2,
        ),
    }

    # 脚本：Step 1 正常 → Step 2 触发 abort → Step 3 不执行
    llm = MockLlm([
        Message(
            role="assistant",
            content="Step 1: running safe command.",
            tool_calls=[{"id": "call_1", "name": "bash", "arguments": {"command": "echo hello"}}],
        ),
        Message(
            role="assistant",
            content="Step 2: running dangerous command.",
            tool_calls=[{"id": "call_2", "name": "danger", "arguments": {"command": "rm -rf /"}}],
        ),
        Message(
            role="assistant",
            content="Step 3: this should never run.",
        ),
    ])

    loop = SessionLoop(llm, tools, queue, events)
    loop_ref.append(loop)

    await asyncio.gather(
        loop.run(Message(role="user", content="Run all steps")),
        print_events(events, prefix=""),
    )

    print(f"\n  Message history: {len(loop.messages)} messages (aborted early)")
    print(f"  Ran {llm._index} of {len(llm._script)} planned LLM calls")
    print(f"  Step 3 was never executed due to abort signal")


# ── Demo 5: 事件流消费 ───────────────────────────────────────────

async def demo_event_stream():
    """演示 EventStream 作为 async iterator 的用法。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: EventStream (异步事件迭代器)")
    print("=" * 60)
    print()

    events = EventStream()

    # 生产者：模拟事件发射
    async def producer():
        for etype in [EventType.MESSAGE_START, EventType.TOOL_START, EventType.TOOL_END, EventType.MESSAGE_END]:
            events.emit(Event(etype, {"demo": True}))
            await asyncio.sleep(0.01)
        events.close()

    # 消费者：用 async for 遍历
    collected = []

    async def consumer():
        async for event in events:
            collected.append(event)
            print(f"  Received: {event.type.value}")

    await asyncio.gather(producer(), consumer())

    print(f"\n  Total events consumed: {len(collected)}")
    print(f"  Event types: {[e.type.value for e in collected]}")
    print(f"  Pattern: async for event in EventStream() — same as Pi-Agent's async iterator")


# ── Main ──────────────────────────────────────────────────────────

async def async_main():
    print("Pi-Agent Session Loop Demo")
    print("Reproduces the dual-layer loop with steering interruption\n")

    await demo_basic_loop()
    await demo_followup()
    await demo_steering()
    await demo_abort()
    await demo_event_stream()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("\n  Dual-layer loop architecture:")
    print("    Outer loop: processes follow-up messages (queued)")
    print("    Inner loop: LLM → tool call → result → repeat")
    print("\n  Message queue modes:")
    print("    - Steering:  immediate interrupt, skips tool results")
    print("    - Follow-up: queued until Agent completes current task")
    print("\n  Termination conditions:")
    print("    1. LLM returns no tool calls → inner loop exits")
    print("    2. No follow-up messages → outer loop exits")
    print("    3. Abort signal → immediate termination")
    print("\n  EventStream:")
    print("    async iterator pattern — consumers use 'async for event in stream'")
    print("\n✓ Demo complete!")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
