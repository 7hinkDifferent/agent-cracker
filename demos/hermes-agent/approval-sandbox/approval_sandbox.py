from __future__ import annotations

"""Dangerous command approval demo core for Hermes."""

import re
from dataclasses import dataclass, field
from typing import Callable


DANGEROUS_PATTERNS = [
    (r"\brm\s+-[^\s]*r", "recursive delete"),
    (r"\bDROP\s+(TABLE|DATABASE)\b", "sql drop"),
    (r"\b(curl|wget)\b.*\|\s*(ba)?sh\b", "pipe remote content to shell"),
    (r"\bgit\s+reset\s+--hard\b", "git hard reset"),
]


def detect_dangerous_command(command: str) -> tuple[bool, str | None]:
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, description
    return False, None


@dataclass
class ApprovalState:
    approved_descriptions: set[str] = field(default_factory=set)

    def approve(self, description: str):
        self.approved_descriptions.add(description)

    def is_approved(self, description: str) -> bool:
        return description in self.approved_descriptions


class SandboxExecutor:
    """Guard dangerous commands before they reach an execution backend."""

    def __init__(self, run_command: Callable[[str], str], approvals: ApprovalState):
        self.run_command = run_command
        self.approvals = approvals

    def execute(self, command: str) -> str:
        dangerous, description = detect_dangerous_command(command)
        if dangerous and description and not self.approvals.is_approved(description):
            return f"BLOCKED pending approval: {description}"
        return self.run_command(command)
