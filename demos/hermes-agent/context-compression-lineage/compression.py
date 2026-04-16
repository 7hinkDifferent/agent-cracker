from __future__ import annotations

"""Context compression + session lineage demo core for Hermes."""

from dataclasses import dataclass


@dataclass
class SessionNode:
    session_id: str
    parent_session_id: str | None
    summary: str


class ContextCompressor:
    def __init__(self, threshold_chars: int = 180):
        self.threshold_chars = threshold_chars

    def should_compress(self, messages: list[str]) -> bool:
        return sum(len(m) for m in messages) > self.threshold_chars

    def compress(self, session_id: str, messages: list[str]) -> tuple[list[str], SessionNode]:
        head = messages[:1]
        middle = messages[1:-1]
        tail = messages[-1:]
        summary = " | ".join(chunk[:30] for chunk in middle)
        child = SessionNode(session_id=f"{session_id}-child", parent_session_id=session_id, summary=summary)
        return head + [f"[summary] {summary}"] + tail, child


class LineageStore:
    def __init__(self):
        self.nodes: dict[str, SessionNode] = {}

    def add(self, node: SessionNode):
        self.nodes[node.session_id] = node

    def lineage(self, session_id: str) -> list[SessionNode]:
        chain: list[SessionNode] = []
        current = self.nodes.get(session_id)
        while current:
            chain.append(current)
            current = self.nodes.get(current.parent_session_id or "")
        return chain
