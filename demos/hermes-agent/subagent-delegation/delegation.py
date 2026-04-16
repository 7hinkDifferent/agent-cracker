from __future__ import annotations

"""Subagent delegation demo core for Hermes."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time


MAX_DEPTH = 2
MAX_CONCURRENT_CHILDREN = 3
BLOCKED_TOOLSETS = {"delegation", "clarify", "memory", "send_message", "execute_code"}


@dataclass
class ChildTask:
    goal: str
    context: str = ""
    depth: int = 0
    requested_toolsets: list[str] | None = None


class DelegationError(RuntimeError):
    pass


class SubagentDelegator:
    def sanitize_toolsets(self, requested: list[str] | None) -> list[str]:
        toolsets = requested or ["terminal", "file", "web"]
        return [toolset for toolset in toolsets if toolset not in BLOCKED_TOOLSETS]

    def run_child(self, task: ChildTask) -> str:
        if task.depth >= MAX_DEPTH:
            raise DelegationError(f"Delegation depth limit reached ({MAX_DEPTH})")
        toolsets = self.sanitize_toolsets(task.requested_toolsets)
        time.sleep(0.05)
        return f"goal={task.goal!r}, toolsets={toolsets}, fresh_context={bool(task.context)}"

    def run_batch(self, tasks: list[ChildTask]) -> list[str]:
        if len(tasks) > MAX_CONCURRENT_CHILDREN:
            raise DelegationError(f"At most {MAX_CONCURRENT_CHILDREN} children may run concurrently")
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = [pool.submit(self.run_child, task) for task in tasks]
            return [future.result() for future in futures]
