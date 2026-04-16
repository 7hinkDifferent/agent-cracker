from __future__ import annotations

"""Mini Hermes Agent: compose MVP + platform demo modules into one flow."""

import os
import sys
import tempfile
from pathlib import Path

_DEMO_ROOT = Path(__file__).resolve().parent.parent
for _subdir in (
    "agent-session-loop",
    "tool-registry-discovery",
    "prompt-assembly",
    "session-memory-search",
    "terminal-multibackend",
    "gateway-session-routing",
    "acp-bridge",
    "cron-delivery",
    "approval-sandbox",
):
    _path = str(_DEMO_ROOT / _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from acp_bridge import HermesACPBridge, JsonRpcMessage
from approval_sandbox import ApprovalState, SandboxExecutor
from cron_delivery import CronJob, CronRunner
from gateway_router import GatewayRunner, MessageEvent
from loop_core import AssistantTurn, CompressionStrategy, HermesLoopAgent, MockProvider, ToolCall
from memory_store import SessionMemoryStore, seed_demo_data
from prompt_builder_demo import PromptAssembler, PromptInputs
from terminal_backends import TerminalManager
from tool_registry import registry, reset_and_discover


def build_tools(terminal_executor: SandboxExecutor) -> dict[str, callable]:
    return {
        "read_file": lambda args: registry.dispatch("read_file", args),
        "terminal": lambda args: terminal_executor.execute(args["command"]),
    }


def build_prompt(memory_root: Path, session_key: str) -> str:
    assembler = PromptAssembler()
    inputs = PromptInputs(
        cwd=_DEMO_ROOT / "prompt-assembly" / "sample_context",
        platform="telegram",
        system_message="Use tools, preserve session continuity, and keep replies terse.",
        memory_lines=(memory_root / "MEMORY.md").read_text(encoding="utf-8").splitlines(),
        user_lines=(memory_root / "USER.md").read_text(encoding="utf-8").splitlines(),
        skills_index=["python-workflow", "incident-triage"],
        ephemeral_system_prompt="Incoming gateway turn from a threaded conversation.",
        session_id=session_key,
        model=os.environ.get("DEMO_MODEL", "openai/gpt-4o-mini"),
    )
    cached = assembler.build_cached_prompt(inputs)
    overlay = assembler.build_ephemeral_overlay(inputs)
    return cached + "\n\n## Ephemeral Overlay\n" + overlay


def run_turn(session_key: str, tools: dict[str, callable], system_prompt: str) -> tuple[str, list[str]]:
    provider = MockProvider(
        name="mini-hermes-provider",
        script=[
            AssistantTurn(
                content="I will inspect the workspace first.",
                tool_calls=[ToolCall("1", "read_file", {"path": "README.md"})],
            ),
            AssistantTurn(
                content="Now I will verify the environment with a safe terminal command.",
                tool_calls=[ToolCall("2", "terminal", {"command": "printf 'terminal ok'"})],
            ),
            AssistantTurn(content="Workspace context loaded; I am ready to continue this session."),
        ],
    )
    agent = HermesLoopAgent(
        providers=[provider],
        tools=tools,
        compression=CompressionStrategy(threshold_chars=220),
    )
    final = agent.run(
        "Open the repo, check the environment, and tell me if this session can continue safely.",
        system_prompt,
    )
    return final, agent.events


def main():
    reset_and_discover()
    terminal_manager = TerminalManager()
    approvals = ApprovalState()
    terminal_executor = SandboxExecutor(lambda command: terminal_manager.run("local", command).output, approvals)
    tools = build_tools(terminal_executor)

    gateway = GatewayRunner(group_sessions_per_user=True)
    incoming = MessageEvent(
        platform="telegram",
        chat_id="dm-100",
        user_id="u-alice",
        text="Can you pick up yesterday's deployment thread?",
        chat_type="dm",
        thread_id="topic-7",
    )
    session_key = gateway.handle_message(incoming)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        store = SessionMemoryStore(tmp_root / "state.db", tmp_root / "memories")
        seed_demo_data(store)
        system_prompt = build_prompt(store.memory_dir, session_key)
        final, events = run_turn(session_key, tools, system_prompt)
        visible_tools = [entry.name for entry in registry.visible_tools({"file", "terminal"})]
        memory_hits = store.search("digest")

        print("=" * 72)
        print("Mini Hermes Agent Demo")
        print("=" * 72)
        print("这不是单一机制 demo，而是把入口、记忆、prompt、tool loop、ACP 与 cron 串起来。")
        print(f"Incoming session key: {session_key}")

        print("\n[Visible tools after registry filtering]\n")
        print(visible_tools)

        print("\n[Memory recall before the turn]\n")
        for hit in memory_hits:
            print(f"- {hit.session_id}: {hit.summary}")

        print("\n[Prompt excerpt]\n")
        print("\n".join(system_prompt.splitlines()[:12]))

        print("\n[Loop events]\n")
        for event in events:
            print(f"- {event}")

        print("\n[Final response]\n")
        print(final)

        print("\n[ACP mirror]\n")
        bridge = HermesACPBridge()
        for request in [
            JsonRpcMessage("session.start", {"session_id": session_key}),
            JsonRpcMessage("agent.tool", {"tool": "read_file", "preview": "README.md"}),
            JsonRpcMessage("agent.done", {"text": final}),
        ]:
            bridge.handle_request(request)
        for line in bridge.outbox:
            print(line)

        print("\n[Cron delivery]\n")
        cron = CronRunner(lambda prompt, skills: f"{prompt} / skills={skills}")
        print(
            cron.execute(
                CronJob(
                    job_id="digest",
                    schedule="0 8 * * *",
                    prompt="Summarize the latest session state",
                    delivery_platform="telegram",
                    delivery_target="owner-thread",
                    injected_skills=["incident-triage"],
                )
            )
        )


if __name__ == "__main__":
    main()
