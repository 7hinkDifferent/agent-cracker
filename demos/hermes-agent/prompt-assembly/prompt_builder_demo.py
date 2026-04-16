from __future__ import annotations

"""Prompt assembly primitives for the Hermes prompt-assembly demo."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


DEFAULT_AGENT_IDENTITY = "You are Hermes Agent, a direct and durable personal AI assistant."
PLATFORM_HINTS = {
    "cli": "Platform hint: respond with concise terminal-friendly markdown.",
    "telegram": "Platform hint: keep replies compact and avoid oversized code fences.",
    "cron": "Platform hint: this is an autonomous scheduled run; act without waiting for the user.",
}


@dataclass
class PromptInputs:
    cwd: Path
    platform: str
    system_message: str = ""
    memory_lines: list[str] = field(default_factory=list)
    user_lines: list[str] = field(default_factory=list)
    skills_index: list[str] = field(default_factory=list)
    ephemeral_system_prompt: str = ""
    session_id: str = "session-demo"
    model: str = "openai/gpt-4o-mini"


class PromptAssembler:
    """Split Hermes prompt building into cached and ephemeral layers."""

    def build_cached_prompt(self, inputs: PromptInputs) -> str:
        sections: list[str] = [DEFAULT_AGENT_IDENTITY]
        if inputs.system_message:
            sections.append(f"## User system message\n{inputs.system_message}")
        if inputs.memory_lines:
            sections.append("## MEMORY.md\n" + "\n".join(f"- {line}" for line in inputs.memory_lines))
        if inputs.user_lines:
            sections.append("## USER.md\n" + "\n".join(f"- {line}" for line in inputs.user_lines))
        if inputs.skills_index:
            sections.append("## Skills Index\n" + "\n".join(f"- {line}" for line in inputs.skills_index))
        context_block = build_context_files_prompt(inputs.cwd)
        if context_block:
            sections.append(context_block)
        hint = PLATFORM_HINTS.get(inputs.platform)
        if hint:
            sections.append(hint)
        return "\n\n".join(section.strip() for section in sections if section.strip())

    def build_ephemeral_overlay(self, inputs: PromptInputs) -> str:
        parts = [
            f"session_id={inputs.session_id}",
            f"model={inputs.model}",
            f"platform={inputs.platform}",
        ]
        if inputs.ephemeral_system_prompt:
            parts.append(f"overlay={inputs.ephemeral_system_prompt}")
        return " | ".join(parts)


def build_context_files_prompt(cwd: Path) -> str:
    """Load the nearest context file using Hermes priority order."""
    for name in (".hermes.md", "AGENTS.md", "CLAUDE.md", ".cursorrules"):
        candidate = cwd / name
        if candidate.exists():
            body = candidate.read_text(encoding="utf-8").strip()
            return f"## Context File ({name})\n{body}"
    return ""
