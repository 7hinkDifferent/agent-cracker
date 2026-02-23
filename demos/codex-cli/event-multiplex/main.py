"""
Codex CLI Event Multiplex Demo

复现 Codex CLI 的 tokio::select! 多通道事件调度：
- 4 通道多路复用（app_event / llm_response / user_input / thread_created）
- 内层 turn 执行循环（LLM → tool → 检查 → 循环/退出）
- Token 超限自动 compaction
- 用户中断处理

Run: uv run python main.py
"""

import asyncio
from multiplex import (
    EventMultiplexer, Channel, ChannelType, Event,
    TurnLoop, TurnResult,
)


async def demo_select():
    """演示 tokio::select! 风格的多通道事件处理。"""
    print("=" * 60)
    print("Demo 1: Multi-Channel Select (tokio::select! 模拟)")
    print("=" * 60)
    print()

    mux = EventMultiplexer()

    # 创建 4 个通道
    app_ch = mux.add_channel(ChannelType.APP_EVENT)
    llm_ch = mux.add_channel(ChannelType.LLM_RESPONSE)
    user_ch = mux.add_channel(ChannelType.USER_INPUT)
    thread_ch = mux.add_channel(ChannelType.THREAD_CREATED)

    received = []

    # 注册处理器
    def on_app(event):
        received.append(f"APP: {event.data}")
        print(f"  [{event.channel.value:15s}] {event.data}")

    def on_llm(event):
        received.append(f"LLM: {event.data}")
        print(f"  [{event.channel.value:15s}] {event.data}")

    def on_user(event):
        received.append(f"USR: {event.data}")
        print(f"  [{event.channel.value:15s}] {event.data}")
        if event.data == "quit":
            return "stop"

    def on_thread(event):
        received.append(f"THR: {event.data}")
        print(f"  [{event.channel.value:15s}] {event.data}")

    mux.on(ChannelType.APP_EVENT, on_app)
    mux.on(ChannelType.LLM_RESPONSE, on_llm)
    mux.on(ChannelType.USER_INPUT, on_user)
    mux.on(ChannelType.THREAD_CREATED, on_thread)

    # 模拟事件发射（不同延迟）
    async def emit_events():
        await asyncio.sleep(0.01)
        thread_ch.send("worker-1 spawned")
        await asyncio.sleep(0.01)
        llm_ch.send("Thinking about your question...")
        await asyncio.sleep(0.01)
        app_ch.send("tool:read completed")
        await asyncio.sleep(0.01)
        llm_ch.send("Here's my answer.")
        await asyncio.sleep(0.01)
        user_ch.send("quit")  # 触发停止

    await asyncio.gather(mux.run(), emit_events())

    print(f"\n  Events processed: {len(received)}")
    print(f"  Key: events from different channels handled in arrival order")


async def demo_turn_loop():
    """演示 run_turn() 内层循环。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Turn Execution Loop (run_turn 内层循环)")
    print("=" * 60)
    print()

    turn_count = [0]

    async def mock_llm(messages):
        turn_count[0] += 1
        user_msgs = [m for m in messages if m["role"] == "user"]

        if turn_count[0] == 1:
            return TurnResult(
                needs_follow_up=True,
                content="Let me read that file.",
                tool_calls=[{"name": "shell", "command": "cat main.py"}],
                token_usage=500,
            )
        elif turn_count[0] == 2:
            return TurnResult(
                needs_follow_up=True,
                content="I'll apply the patch.",
                tool_calls=[{"name": "apply_patch", "diff": "--- a/main.py\n+++ b/main.py"}],
                token_usage=800,
            )
        else:
            return TurnResult(
                needs_follow_up=False,
                content="Done! The file has been updated.",
                token_usage=300,
            )

    async def mock_tool(tc):
        name = tc.get("name", "?")
        if name == "shell":
            return f"$ {tc.get('command', '')}\ndef main(): pass"
        elif name == "apply_patch":
            return "Patch applied successfully"
        return "OK"

    loop = TurnLoop(llm_fn=mock_llm, tool_fn=mock_tool, token_limit=128000)
    events = await loop.run("Fix the bug in main.py")

    for ev in events:
        etype = ev["type"]
        if etype == "llm_response":
            has_tools = f" [+{ev['tool_calls']} tools]" if ev["tool_calls"] else ""
            print(f"  ◂ LLM: \"{ev['content']}\"{has_tools}")
        elif etype == "tool_result":
            print(f"  ⚙ Tool: {ev['tool']}")
        elif etype == "turn_complete":
            print(f"  ■ Turn complete")

    print(f"\n  Total messages: {len(loop.messages)}")
    print(f"  Total tokens: {loop.total_tokens}")


async def demo_auto_compact():
    """演示 token 超限触发自动 compaction。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Auto-Compact on Token Overflow")
    print("=" * 60)
    print()

    turn_count = [0]

    async def mock_llm(messages):
        turn_count[0] += 1
        if turn_count[0] <= 3:
            return TurnResult(
                needs_follow_up=True,
                content=f"Step {turn_count[0]}: processing...",
                tool_calls=[{"name": "shell", "command": f"step{turn_count[0]}"}],
                token_usage=50000,  # 大量 token
            )
        return TurnResult(
            needs_follow_up=False,
            content="All steps complete!",
            token_usage=1000,
        )

    async def mock_tool(tc):
        return f"Step output OK"

    async def mock_compact(messages):
        # 保留 system + 最近 2 条
        compacted = [{"role": "system", "content": "[Summary of previous work]"}]
        compacted.extend(messages[-2:])
        print(f"  ⟳ Compacted: {len(messages)} messages → {len(compacted)}")
        return compacted

    loop = TurnLoop(
        llm_fn=mock_llm,
        tool_fn=mock_tool,
        compact_fn=mock_compact,
        token_limit=100000,  # 低阈值
    )

    events = await loop.run("Run all steps")

    for ev in events:
        etype = ev["type"]
        if etype == "llm_response":
            print(f"  ◂ LLM: \"{ev['content']}\"")
        elif etype == "tool_result":
            print(f"  ⚙ Tool: {ev['tool']}")
        elif etype == "auto_compact":
            print(f"  ⟳ AUTO-COMPACT triggered (tokens after: {ev['tokens_after']})")
        elif etype == "turn_complete":
            print(f"  ■ Complete")

    print(f"\n  Final tokens: {loop.total_tokens}")


async def demo_abort():
    """演示用户中断。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: User Abort (Ctrl+C 中断)")
    print("=" * 60)
    print()

    call_count = [0]
    loop_ref: list[TurnLoop] = []

    async def mock_llm(messages):
        call_count[0] += 1
        if call_count[0] <= 3:
            return TurnResult(
                needs_follow_up=True,
                content=f"Step {call_count[0]}...",
                tool_calls=[{"name": "shell", "command": f"step-{call_count[0]}"}],
                token_usage=100,
            )
        return TurnResult(needs_follow_up=False, content="Done", token_usage=10)

    async def mock_tool(tc):
        # 在第二个 tool 执行时触发 abort
        if call_count[0] == 2:
            loop_ref[0].abort()
            return "Aborted by user (Ctrl+C)"
        return "OK"

    loop = TurnLoop(llm_fn=mock_llm, tool_fn=mock_tool)
    loop_ref.append(loop)

    events = await loop.run("Do something long")

    for ev in events:
        etype = ev["type"]
        if etype == "llm_response":
            print(f"  ◂ LLM: \"{ev['content']}\"")
        elif etype == "tool_result":
            print(f"  ⚙ Tool: {ev['tool']}")
        elif etype == "turn_aborted":
            print(f"  ✗ Turn aborted (Ctrl+C)")

    print(f"\n  Turns before abort: {call_count[0]}")
    print(f"  Step 3 was never reached")

    print(f"\n  Turns executed before abort: {call_count[0]}")


async def async_main():
    print("Codex CLI Event Multiplex Demo")
    print("Reproduces tokio::select! multi-channel event dispatching\n")

    await demo_select()
    await demo_turn_loop()
    await demo_auto_compact()
    await demo_abort()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("\n  Dual-layer architecture:")
    print("    Outer: EventMultiplexer (select! over 4 channels)")
    print("      - app_event:      internal events (tool done, compact)")
    print("      - llm_response:   streaming LLM output")
    print("      - user_input:     keyboard/mouse events")
    print("      - thread_created: worker thread notifications")
    print("    Inner: TurnLoop (LLM → tool → check → loop/break)")
    print("\n  Termination:")
    print("    - needs_follow_up=false → turn complete")
    print("    - token overflow → auto-compact → continue")
    print("    - user abort → immediate stop")
    print("\n✓ Demo complete!")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
