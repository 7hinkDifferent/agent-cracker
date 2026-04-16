from __future__ import annotations

"""ACP bridge demo core for Hermes."""

import json
from dataclasses import dataclass


@dataclass
class JsonRpcMessage:
    method: str
    params: dict


class HermesACPBridge:
    """Translate Hermes loop callbacks into ACP-style session updates."""

    def __init__(self):
        self.outbox: list[str] = []

    def send_event(self, method: str, **params):
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params}, ensure_ascii=False)
        self.outbox.append(payload)

    def handle_request(self, request: JsonRpcMessage):
        if request.method == "session.start":
            self.send_event("session_update", stage="started", session_id=request.params["session_id"])
        elif request.method == "agent.thinking":
            self.send_event("session_update", stage="thinking", text=request.params["text"])
        elif request.method == "agent.tool":
            self.send_event("session_update", stage="tool", tool=request.params["tool"], preview=request.params.get("preview", ""))
        elif request.method == "agent.done":
            self.send_event("session_update", stage="done", text=request.params["text"])
        else:
            self.send_event("session_update", stage="ignored", method=request.method)
