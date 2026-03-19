"""
OpenClaw — System Prompt Builder 机制复现

复现 OpenClaw 的 14+ sections 动态 prompt 组装：
- 3 种 prompt 模式（full / minimal / none）
- 条件注入（Skills 匹配、Memory 指令、SOUL.md 人格、Sandbox 描述）
- 动态 tool 列表渲染
- Runtime 元数据注入

对应源码: src/agents/system-prompt.ts (696 行)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── 数据模型 ──────────────────────────────────────────────────────

class PromptMode(str, Enum):
    FULL = "full"         # 主 agent：全部 sections
    MINIMAL = "minimal"   # 子 agent：精简 sections
    NONE = "none"         # 纯身份声明


@dataclass
class ToolInfo:
    """工具摘要（用于 prompt 注入）"""
    id: str
    description: str


@dataclass
class SkillMatch:
    """匹配到的 Skill"""
    name: str
    content: str  # SKILL.md 内容


@dataclass
class SandboxInfo:
    """沙箱环境信息"""
    enabled: bool = False
    container_workspace: str = "/agent/workspace"
    host_workspace: str = ""
    browser_bridge: bool = False


@dataclass
class ContextFile:
    """上下文文件"""
    path: str
    content: str


@dataclass
class PromptParams:
    """Prompt 构建参数"""
    mode: PromptMode = PromptMode.FULL
    agent_id: str = "main"
    agent_name: str = "OpenClaw"
    model: str = "claude-sonnet-4-20250514"
    channel: str = "cli"
    os_name: str = "macOS"
    hostname: str = "mac-studio"
    timezone: str = "Asia/Shanghai"
    tools: list[ToolInfo] = field(default_factory=list)
    skill_match: Optional[SkillMatch] = None
    memory_enabled: bool = False
    sandbox: SandboxInfo = field(default_factory=SandboxInfo)
    context_files: list[ContextFile] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    silent_reply_token: str = "[[SILENT]]"


# ── Prompt 构建器 ─────────────────────────────────────────────────

class SystemPromptBuilder:
    """
    OpenClaw System Prompt Builder 复现

    组装流程:
    基础身份 → + 可用 tool 摘要 → + channel 特定指令
      → + Skills 匹配结果 → + Memory 指令
      → + SOUL.md 人格注入 → + 沙箱环境描述
      → + Runtime 元数据
    """

    def build(self, params: PromptParams) -> str:
        if params.mode == PromptMode.NONE:
            return self._build_none(params)

        sections: list[str] = []
        is_minimal = params.mode == PromptMode.MINIMAL

        # ── Section 1: Identity ──
        sections.append(self._section_identity(params))

        # ── Section 2: Tooling ──
        sections.append(self._section_tooling(params))

        # ── Section 3: Tool Call Style ──
        if not is_minimal:
            sections.append(self._section_tool_call_style())

        # ── Section 4: Safety ──
        sections.append(self._section_safety())

        # ── Section 5: Skills (full only) ──
        if not is_minimal and params.skill_match:
            sections.append(self._section_skills(params.skill_match))

        # ── Section 6: Memory (full only) ──
        if not is_minimal and params.memory_enabled:
            sections.append(self._section_memory())

        # ── Section 7: Sandbox (conditional) ──
        if params.sandbox.enabled:
            sections.append(self._section_sandbox(params.sandbox))

        # ── Section 8: Date & Time ──
        sections.append(self._section_datetime(params))

        # ── Section 9: Workspace ──
        sections.append(self._section_workspace(params))

        # ── Section 10: Project Context ──
        if params.context_files:
            sections.append(self._section_context(params.context_files))

        # ── Section 11: Messaging (full only) ──
        if not is_minimal:
            sections.append(self._section_messaging(params))

        # ── Section 12: Silent Reply (full only) ──
        if not is_minimal:
            sections.append(self._section_silent_reply(params))

        # ── Section 13: Runtime (always) ──
        sections.append(self._section_runtime(params))

        return "\n\n".join(s for s in sections if s)

    # ── 各 Section 实现 ──

    def _build_none(self, params: PromptParams) -> str:
        return f"You are {params.agent_name}, a personal assistant running inside OpenClaw."

    def _section_identity(self, params: PromptParams) -> str:
        return (
            f"# Identity\n"
            f"You are a personal assistant running inside OpenClaw.\n"
            f"Your name is {params.agent_name}."
        )

    def _section_tooling(self, params: PromptParams) -> str:
        if not params.tools:
            return "# Tooling\nYou have access to built-in tools for file operations and shell execution."
        lines = ["# Tooling", "You have access to the following tools:", ""]
        for tool in params.tools:
            lines.append(f"- **{tool.id}**: {tool.description}")
        return "\n".join(lines)

    def _section_tool_call_style(self) -> str:
        return (
            "# Tool Call Style\n"
            "Be concise. Avoid narrating low-risk operations.\n"
            "Do not ask for permission before using tools unless the operation is destructive."
        )

    def _section_safety(self) -> str:
        return (
            "# Safety\n"
            "- You do not have independent goals or a desire for self-preservation.\n"
            "- You should never attempt to replicate yourself or create new AI agents.\n"
            "- Prioritize human oversight over task completion.\n"
            "- If uncertain, ask for clarification rather than guessing."
        )

    def _section_skills(self, skill: SkillMatch) -> str:
        return (
            f"# Skills\n"
            f"A skill matched the current task: **{skill.name}**\n"
            f"Before proceeding, read the SKILL.md for instructions.\n\n"
            f"```\n{skill.content}\n```"
        )

    def _section_memory(self) -> str:
        return (
            "# Memory\n"
            "You have access to a long-term memory system via `memory_search`.\n"
            "When the user asks about past conversations or facts:\n"
            "1. Always search memory first before answering.\n"
            "2. Use MEMORY.md and memory/*.md files for persistent notes.\n"
            "3. If you learn new facts about the user, save them to memory."
        )

    def _section_sandbox(self, sandbox: SandboxInfo) -> str:
        lines = [
            "# Sandbox",
            f"Tools run inside a Docker container.",
            f"Container workspace: `{sandbox.container_workspace}`",
        ]
        if sandbox.host_workspace:
            lines.append(f"Host workspace (mounted): `{sandbox.host_workspace}`")
        if sandbox.browser_bridge:
            lines.append("Browser bridge is available for web automation.")
        return "\n".join(lines)

    def _section_datetime(self, params: PromptParams) -> str:
        return (
            f"# Date & Time\n"
            f"User timezone: {params.timezone}"
        )

    def _section_workspace(self, params: PromptParams) -> str:
        ws = params.sandbox.container_workspace if params.sandbox.enabled else "~/workspace"
        return f"# Workspace\nWorking directory: `{ws}`"

    def _section_context(self, files: list[ContextFile]) -> str:
        lines = ["# Project Context"]
        has_soul = False
        for f in files:
            lines.append(f"\n## {f.path}\n```\n{f.content}\n```")
            if f.path.lower().endswith("soul.md"):
                has_soul = True
        if has_soul:
            lines.append(
                "\nIf SOUL.md is present, embody its persona and tone. "
                "Avoid stiff, generic replies — be authentic to the defined character."
            )
        return "\n".join(lines)

    def _section_messaging(self, params: PromptParams) -> str:
        return (
            f"# Messaging\n"
            f"Current channel: {params.channel}\n"
            f"Use `[[reply_to_current]]` to send a native reply to the current message.\n"
            f"Use inline buttons with `[[button:label:action]]` syntax."
        )

    def _section_silent_reply(self, params: PromptParams) -> str:
        return (
            f"# Silent Reply\n"
            f"If you have nothing meaningful to say, respond with exactly: "
            f"`{params.silent_reply_token}`"
        )

    def _section_runtime(self, params: PromptParams) -> str:
        caps = ", ".join(params.capabilities) if params.capabilities else "text"
        return (
            f"# Runtime\n"
            f"agent={params.agent_id}, host={params.hostname}, os={params.os_name}, "
            f"model={params.model}, channel={params.channel}, capabilities={caps}"
        )


# ── Demo ──────────────────────────────────────────────────────────

def main():
    builder = SystemPromptBuilder()

    print("=" * 64)
    print("OpenClaw System Prompt Builder Demo")
    print("=" * 64)

    # ── Mode 1: none ──
    print("\n── Mode: none ──")
    prompt = builder.build(PromptParams(mode=PromptMode.NONE, agent_name="Jarvis"))
    print(f"  长度: {len(prompt)} chars")
    print(f"  内容: {prompt}")

    # ── Mode 2: minimal（子 agent） ──
    print("\n── Mode: minimal（子 agent） ──")
    prompt = builder.build(PromptParams(
        mode=PromptMode.MINIMAL,
        agent_id="sub-1",
        agent_name="Worker",
        model="gpt-4o",
        tools=[
            ToolInfo("read", "Read file contents"),
            ToolInfo("exec", "Execute shell command"),
        ],
    ))
    sections = prompt.split("\n\n# ")
    print(f"  长度: {len(prompt)} chars, Sections: {len(sections)}")
    for s in sections:
        title = s.split("\n")[0].lstrip("# ")
        print(f"    - {title}")

    # ── Mode 3: full（完整 agent） ──
    print("\n── Mode: full（完整 agent） ──")
    prompt = builder.build(PromptParams(
        mode=PromptMode.FULL,
        agent_id="main",
        agent_name="Claw",
        model="claude-sonnet-4-20250514",
        channel="discord",
        tools=[
            ToolInfo("read", "Read file contents"),
            ToolInfo("write", "Write file contents"),
            ToolInfo("edit", "Edit file with search/replace"),
            ToolInfo("exec", "Execute shell command"),
            ToolInfo("memory_search", "Search long-term memory"),
            ToolInfo("message", "Send message to channel"),
        ],
        skill_match=SkillMatch("github", "Use `gh` CLI for GitHub operations..."),
        memory_enabled=True,
        sandbox=SandboxInfo(enabled=True, host_workspace="/home/user/project"),
        context_files=[
            ContextFile("SOUL.md", "You are a witty, concise assistant who loves puns."),
            ContextFile("AGENTS.md", "Project uses TypeScript + pnpm. Run tests with vitest."),
        ],
        capabilities=["text", "image", "voice"],
    ))
    sections = prompt.split("\n\n# ")
    print(f"  长度: {len(prompt)} chars, Sections: {len(sections)}")
    for s in sections:
        title = s.split("\n")[0].lstrip("# ")
        print(f"    - {title}")

    # 输出完整 prompt
    print(f"\n── 完整 Prompt 内容 ──")
    print("-" * 64)
    print(prompt)
    print("-" * 64)


if __name__ == "__main__":
    main()
