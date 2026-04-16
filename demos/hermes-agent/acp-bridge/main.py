from __future__ import annotations

from acp_bridge import HermesACPBridge, JsonRpcMessage


REQUESTS = [
    JsonRpcMessage("session.start", {"session_id": "zed-1"}),
    JsonRpcMessage("agent.thinking", {"text": "Inspecting workspace context"}),
    JsonRpcMessage("agent.tool", {"tool": "read_file", "preview": "AGENTS.md"}),
    JsonRpcMessage("agent.done", {"text": "Workspace rules loaded and summarized."}),
]


def main():
    bridge = HermesACPBridge()

    print("=" * 72)
    print("Hermes ACP Bridge Demo")
    print("=" * 72)

    for request in REQUESTS:
        bridge.handle_request(request)

    print("Input -> JSON-RPC session_update events:\n")
    for line in bridge.outbox:
        print(line)


if __name__ == "__main__":
    main()
