from __future__ import annotations

"""Run the Hermes agent-session-loop demo."""

from loop_core import (
    AssistantTurn,
    CompressionStrategy,
    HermesLoopAgent,
    InterruptController,
    MockProvider,
    ToolCall,
)


SYSTEM_PROMPT = "You are Hermes Agent. Keep acting until the task is complete."


def make_tools() -> dict[str, callable]:
    long_chunk = "\n".join(f"line {i}: cached context" for i in range(1, 18))

    return {
        "read_file": lambda args: f"README excerpt from {args['path']}:\n{long_chunk}",
        "terminal": lambda args: f"$ {args['command']}\napp.py\nREADME.md\nstate.db",
    }


def build_agent() -> HermesLoopAgent:
    primary = MockProvider(
        name="openai-primary",
        script=[AssistantTurn(content="should not be used")],
        fail_on_calls={1, 2, 3},
    )
    fallback = MockProvider(
        name="anthropic-fallback",
        script=[
            AssistantTurn(
                content="I should inspect the workspace before answering.",
                tool_calls=[ToolCall("call_1", "read_file", {"path": "README.md"})],
            ),
            AssistantTurn(
                content="I also want a directory listing.",
                tool_calls=[ToolCall("call_2", "terminal", {"command": "ls"})],
            ),
            AssistantTurn(
                content="Done. I found the project docs and the working files.",
                tool_calls=[],
            ),
        ],
    )
    interrupt = InterruptController()
    interrupt.trigger("new Telegram message arrived while the loop was thinking")
    return HermesLoopAgent(
        providers=[primary, fallback],
        tools=make_tools(),
        compression=CompressionStrategy(threshold_chars=140),
        interrupt=interrupt,
    )


def main():
    print("=" * 72)
    print("Hermes Agent Session Loop Demo")
    print("=" * 72)
    print("场景: 主 provider 失败 → fallback provider 接管 → tool loop → interrupt → compression")
    print("观察重点: 先看事件流，再看最终保留下来的 history，理解为何中间消息会被压缩成摘要。")
    print()

    agent = build_agent()
    final = agent.run(
        user_message=(
            "Inspect the workspace, remember enough context for later, and tell me what you found. "
            "Please keep enough state so a follow-up gateway turn can resume cleanly."
        ),
        system_prompt=SYSTEM_PROMPT,
    )

    print("[Event timeline]")
    for index, event in enumerate(agent.events, start=1):
        print(f"{index:02d}. {event}")

    print("\n[Final response]")
    print(final)

    print("\n[Persisted history snapshot]")
    print("注意: 被压缩掉的中段消息不会逐条出现，而是收敛成一个 `[compressed-summary]` system message。")
    for message in agent.history:
        tool_suffix = f" (tool_call_id={message.tool_call_id})" if message.tool_call_id else ""
        print(f"[{message.role}] {message.content[:90]}{tool_suffix}")


if __name__ == "__main__":
    main()
