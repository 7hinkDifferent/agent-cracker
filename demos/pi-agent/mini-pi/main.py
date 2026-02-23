"""
Mini-Pi — 串联 4 个 MVP 组件的最小完整 Coding Agent

通过 import 兄弟 MVP demo 模块实现组合：
1. prompt-builder      → PromptBuilder + ToolDef（prompt 组装）
2. llm-multi-provider  → LlmClient + detect_provider（LLM 调用）
3. agent-session-loop  → SessionLoop + EventStream + MessageQueue（会话循环）
4. pluggable-ops       → LocalOps + FileOperations + ShellOperations（工具执行环境）

Run: uv run --with litellm python main.py
Mock mode (no API key): uv run python main.py --mock
"""

import os
import sys
import asyncio

# ── 添加兄弟 demo 目录到 import 路径 ─────────────────────────────

_DEMO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _subdir in ("prompt-builder", "llm-multi-provider", "agent-session-loop", "pluggable-ops"):
    _path = os.path.join(_DEMO_DIR, _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)

# ── 从兄弟 demo 导入 MVP 组件 ────────────────────────────────────

# 组件 1: Prompt Builder
from builder import PromptBuilder, TOOL_READ, TOOL_EDIT, TOOL_BASH

# 组件 2: Multi-Provider LLM
from providers import LlmClient, LlmMessage, detect_provider

# 组件 3: Session Loop
from loop import (
    SessionLoop, EventStream, MessageQueue,
    Message, ToolDef as LoopToolDef, EventType,
)

# 组件 4: Pluggable Ops
from tools import LocalOps

# ── 配置 ──────────────────────────────────────────────────────────

MODEL = os.environ.get("DEMO_MODEL", "openai/gpt-4o-mini")
MOCK_MODE = "--mock" in sys.argv


# ── 工具实现（通过 Ops 接口）──────────────────────────────────────

def make_tools(ops: LocalOps, cwd: str) -> dict[str, LoopToolDef]:
    """创建工具集，通过 Ops 接口执行实际操作。"""

    def read_file(args: dict) -> str:
        path = args.get("path", "")
        abs_path = os.path.join(cwd, path) if not os.path.isabs(path) else path
        try:
            content = ops.read_file(abs_path)
            offset = args.get("offset")
            limit = args.get("limit")
            if offset or limit:
                lines = content.splitlines()
                start = (offset or 1) - 1
                end = start + (limit or len(lines))
                content = "\n".join(lines[start:end])
            return content
        except Exception as e:
            return f"Error reading {path}: {e}"

    def edit_file(args: dict) -> str:
        path = args.get("path", "")
        abs_path = os.path.join(cwd, path) if not os.path.isabs(path) else path
        search = args.get("search", "")
        replace = args.get("replace", "")
        try:
            content = ops.read_file(abs_path)
            if search not in content:
                return f"Error: search text not found in {path}"
            new_content = content.replace(search, replace, 1)
            ops.write_file(abs_path, new_content)
            return f"Successfully edited {path}"
        except Exception as e:
            return f"Error editing {path}: {e}"

    def run_bash(args: dict) -> str:
        command = args.get("command", "")
        try:
            exit_code, output = ops.run_command(command, cwd)
            return output
        except Exception as e:
            return f"Error: {e}"

    return {
        "read": LoopToolDef("read", "Read file contents", read_file),
        "edit": LoopToolDef("edit", "Edit a file (search/replace)", edit_file),
        "bash": LoopToolDef("bash", "Execute shell command", run_bash),
    }


# ── LLM 桥接 ─────────────────────────────────────────────────────

class LlmBridge:
    """
    将 SessionLoop 的 MockLlm 接口连接到真实 LlmClient。
    桥接 Message ↔ LlmMessage 格式。
    """

    def __init__(self, client: LlmClient, model: str):
        self.client = client
        self.model = model

    async def complete(self, messages: list[Message]) -> Message:
        """将 loop.Message 转为 LlmMessage，调用 LLM，转回。"""
        llm_messages = []
        for msg in messages:
            lm = LlmMessage(
                role=msg.role,
                content=msg.content,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
            )
            llm_messages.append(lm)

        # 构建 tool schemas
        tool_schemas = [
            t.to_function_schema()
            for t in [TOOL_READ, TOOL_EDIT, TOOL_BASH]
        ]

        response = self.client.complete(
            model=self.model,
            messages=llm_messages,
            tools=tool_schemas,
        )

        return Message(
            role="assistant",
            content=response.content,
            tool_calls=response.tool_calls if response.tool_calls else None,
        )


class MockBridge:
    """Mock LLM 桥接，用于无 API key 的演示。"""

    def __init__(self):
        self._turn = 0

    async def complete(self, messages: list[Message]) -> Message:
        """模拟 LLM 响应：读文件 → 编辑 → 完成。"""
        await asyncio.sleep(0)
        self._turn += 1

        # 分析用户意图
        user_msgs = [m for m in messages if m.role == "user"]
        last_user = user_msgs[-1].content if user_msgs else ""

        if self._turn == 1:
            # 第一轮：读文件了解现状
            return Message(
                role="assistant",
                content="Let me read the file first.",
                tool_calls=[{
                    "id": f"call_{self._turn}",
                    "name": "read",
                    "arguments": {"path": "example.py"},
                }],
            )
        elif self._turn == 2:
            # 第二轮：执行编辑
            return Message(
                role="assistant",
                content="I'll make the requested change.",
                tool_calls=[{
                    "id": f"call_{self._turn}",
                    "name": "edit",
                    "arguments": {
                        "path": "example.py",
                        "search": "Hello",
                        "replace": "Hello, World",
                    },
                }],
            )
        elif self._turn == 3:
            # 第三轮：验证
            return Message(
                role="assistant",
                content="Let me verify the change.",
                tool_calls=[{
                    "id": f"call_{self._turn}",
                    "name": "read",
                    "arguments": {"path": "example.py"},
                }],
            )
        else:
            # 完成
            return Message(
                role="assistant",
                content="Done! I've updated example.py. The greeting now says 'Hello, World'.",
            )


# ── 事件打印 ──────────────────────────────────────────────────────

async def print_events(events: EventStream):
    """打印事件流。"""
    async for event in events:
        if event.type == EventType.MESSAGE_START:
            print("  ▸ LLM thinking...")
        elif event.type == EventType.MESSAGE_END:
            content = event.data.get("content", "")
            has_tools = event.data.get("has_tool_calls", False)
            suffix = " [+ tool calls]" if has_tools else ""
            print(f"  ◂ LLM: \"{content}\"{suffix}")
        elif event.type == EventType.TOOL_START:
            tool = event.data["tool"]
            args = event.data["args"]
            print(f"  ⚙ {tool}({args})")
        elif event.type == EventType.TOOL_END:
            result = event.data["result"]
            preview = result[:100].replace("\n", "\\n")
            if len(result) > 100:
                preview += "..."
            print(f"  ✓ {preview}")
        elif event.type == EventType.STEERING_INTERRUPT:
            print(f"  ⚡ STEERING: {event.data['count']} message(s) injected")
        elif event.type == EventType.LOOP_END:
            print(f"  ■ Done ({event.data['total_messages']} messages)")


# ── 主流程 ────────────────────────────────────────────────────────

async def run_agent():
    """运行 mini-pi agent。"""

    mode = "mock" if MOCK_MODE else "live"
    print(f"Mini-Pi Agent (mode: {mode}, model: {MODEL})")
    print("=" * 60)

    # 1. Pluggable Ops — 创建执行环境
    cwd = os.getcwd()
    ops = LocalOps()
    print(f"\n  [Ops] Environment: {ops}")
    print(f"  [Ops] Working dir: {cwd}")

    # 2. Prompt Builder — 组装 system prompt
    prompt_builder = PromptBuilder(
        tools=[TOOL_READ, TOOL_EDIT, TOOL_BASH],
        cwd=cwd,
        project_context="Mini-Pi demo project. Editing example files.",
    )
    system_prompt = prompt_builder.build()
    print(f"\n  [Prompt] System prompt: {len(system_prompt)} chars")
    print(f"  [Prompt] Tools: {', '.join(t.name for t in prompt_builder.tools)}")

    # 3. 创建示例文件
    example_file = os.path.join(cwd, "example.py")
    ops.write_file(example_file, 'def greet():\n    return "Hello"\n\nprint(greet())\n')
    print(f"\n  [Setup] Created {example_file}")

    # 4. 构建工具集
    tools = make_tools(ops, cwd)

    # 5. LLM + Session Loop
    events = EventStream()
    queue = MessageQueue()

    if MOCK_MODE:
        llm = MockBridge()
    else:
        client = LlmClient()
        llm = LlmBridge(client, MODEL)

    loop = SessionLoop(llm, tools, queue, events)

    # 6. 注入 system prompt 作为第一条消息
    loop.messages.append(Message(role="system", content=system_prompt))

    # 7. 运行
    user_request = "Update example.py to make the greeting say 'Hello, World' instead of 'Hello'"
    print(f"\n  [User] {user_request}")
    print(f"\n{'─' * 60}")
    print("Agent execution:")
    print()

    await asyncio.gather(
        loop.run(Message(role="user", content=user_request)),
        print_events(events),
    )

    # 8. 验证结果
    print(f"\n{'─' * 60}")
    print("Result verification:")
    final_content = ops.read_file(example_file)
    print(f"\n  example.py after edit:")
    for line in final_content.splitlines():
        print(f"    {line}")

    success = "Hello, World" in final_content
    print(f"\n  {'✓' if success else '✗'} Edit {'applied successfully' if success else 'NOT applied'}")

    # 9. 清理
    os.remove(example_file)

    # 10. 组件使用统计
    print(f"\n{'=' * 60}")
    print("Component Usage Summary")
    print("=" * 60)
    print(f"\n  1. PromptBuilder  → {len(system_prompt)} char system prompt")
    print(f"  2. LlmClient     → {detect_provider(MODEL)} provider ({mode} mode)")
    print(f"  3. SessionLoop    → {len(loop.messages)} messages, dual-layer loop")
    print(f"  4. LocalOps       → file read/write/exec via local filesystem")
    print(f"\n  All 4 MVP components working together!")
    print(f"\n✓ Mini-Pi demo complete!")


def main():
    asyncio.run(run_agent())


if __name__ == "__main__":
    main()
