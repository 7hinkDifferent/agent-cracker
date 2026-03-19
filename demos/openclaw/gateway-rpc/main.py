"""
OpenClaw — Gateway RPC 机制复现

复现 OpenClaw 的 WebSocket RPC Gateway：
- JSON 帧协议（req/res/event 三类帧）
- connect 握手（含协议版本协商）
- 方法路由与认证
- 异步消息分发

对应源码: src/gateway/server/, src/gateway/protocol.ts
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional


# ── 协议定义 ──────────────────────────────────────────────────────

PROTOCOL_VERSION = 1
DEFAULT_PORT = 18789


class FrameType(str, Enum):
    REQUEST = "req"
    RESPONSE = "res"
    EVENT = "event"


@dataclass
class RequestFrame:
    id: str
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    type: str = "req"


@dataclass
class ResponseFrame:
    id: str
    ok: bool
    payload: Any = None
    error: Optional[str] = None
    type: str = "res"


@dataclass
class EventFrame:
    event: str
    data: dict[str, Any] = field(default_factory=dict)
    type: str = "event"


def serialize(frame: RequestFrame | ResponseFrame | EventFrame) -> str:
    if isinstance(frame, RequestFrame):
        return json.dumps({"type": frame.type, "id": frame.id, "method": frame.method, "params": frame.params})
    if isinstance(frame, ResponseFrame):
        d: dict[str, Any] = {"type": frame.type, "id": frame.id, "ok": frame.ok}
        if frame.ok:
            d["payload"] = frame.payload
        else:
            d["error"] = frame.error
        return json.dumps(d)
    return json.dumps({"type": frame.type, "event": frame.event, "data": frame.data})


def parse_frame(raw: str) -> dict[str, Any]:
    return json.loads(raw)


# ── Gateway 连接状态 ──────────────────────────────────────────────

@dataclass
class GatewayConnection:
    """单个 WebSocket 连接的状态"""
    conn_id: str
    authenticated: bool = False
    client_name: str = ""
    protocol_version: int = 0
    send_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)

    async def send(self, frame: ResponseFrame | EventFrame):
        await self.send_queue.put(serialize(frame))


# ── RPC 方法注册 ──────────────────────────────────────────────────

MethodHandler = Callable[[GatewayConnection, dict[str, Any]], Coroutine[Any, Any, Any]]


class MethodRegistry:
    """RPC 方法注册表"""

    def __init__(self):
        self._handlers: dict[str, MethodHandler] = {}
        self._auth_required: set[str] = set()

    def register(self, method: str, handler: MethodHandler, auth_required: bool = True):
        self._handlers[method] = handler
        if auth_required:
            self._auth_required.add(method)

    def needs_auth(self, method: str) -> bool:
        return method in self._auth_required

    async def dispatch(self, conn: GatewayConnection, method: str, params: dict[str, Any]) -> Any:
        handler = self._handlers.get(method)
        if not handler:
            raise ValueError(f"Unknown method: {method}")
        return await handler(conn, params)


# ── Gateway 服务器 ────────────────────────────────────────────────

class GatewayServer:
    """
    OpenClaw Gateway RPC 服务器复现

    核心职责：
    1. WebSocket RPC 服务器（JSON 帧协议）
    2. 连接管理（握手 → 认证 → 方法分发）
    3. 事件广播（向所有已认证连接推送事件）
    """

    def __init__(self, password: str = "demo-password"):
        self.connections: dict[str, GatewayConnection] = {}
        self.password = password
        self.registry = MethodRegistry()
        self._setup_builtin_methods()

    def _setup_builtin_methods(self):
        """注册内置 RPC 方法"""
        # connect 不需要认证（它本身就是认证过程）
        self.registry.register("connect", self._handle_connect, auth_required=False)
        self.registry.register("send_message", self._handle_send_message)
        self.registry.register("list_agents", self._handle_list_agents)
        self.registry.register("ping", self._handle_ping)

    # ── 内置方法处理 ──

    async def _handle_connect(self, conn: GatewayConnection, params: dict[str, Any]) -> dict[str, Any]:
        """握手 + 协议版本协商 + 密码认证"""
        min_proto = params.get("minProtocol", 1)
        max_proto = params.get("maxProtocol", 1)

        if PROTOCOL_VERSION < min_proto or PROTOCOL_VERSION > max_proto:
            raise ValueError(
                f"Protocol mismatch: server={PROTOCOL_VERSION}, "
                f"client=[{min_proto},{max_proto}]"
            )

        password = params.get("password", "")
        if password != self.password:
            raise ValueError("Authentication failed: invalid password")

        conn.authenticated = True
        conn.client_name = params.get("clientName", "unknown")
        conn.protocol_version = PROTOCOL_VERSION

        return {
            "protocol": PROTOCOL_VERSION,
            "serverVersion": "openclaw-demo/1.0",
            "connId": conn.conn_id,
        }

    async def _handle_send_message(self, _conn: GatewayConnection, params: dict[str, Any]) -> dict[str, Any]:
        """模拟消息发送"""
        channel = params.get("channel", "unknown")
        text = params.get("text", "")
        msg_id = str(uuid.uuid4())[:8]

        # 广播消息事件
        await self.broadcast_event("message.sent", {
            "id": msg_id, "channel": channel, "text": text[:50]
        })

        return {"id": msg_id, "status": "sent"}

    async def _handle_list_agents(self, _conn: GatewayConnection, _params: dict[str, Any]) -> list[dict[str, str]]:
        """列出可用 agent"""
        return [
            {"id": "coder-agent", "status": "idle"},
            {"id": "helper-agent", "status": "busy"},
        ]

    async def _handle_ping(self, _conn: GatewayConnection, _params: dict[str, Any]) -> dict[str, float]:
        return {"pong": time.time()}

    # ── 连接管理 ──

    async def handle_message(self, conn: GatewayConnection, raw: str) -> Optional[str]:
        """处理入站消息，返回响应帧"""
        try:
            frame = parse_frame(raw)
        except json.JSONDecodeError:
            resp = ResponseFrame(id="?", ok=False, error="Invalid JSON")
            return serialize(resp)

        if frame.get("type") != "req":
            resp = ResponseFrame(id="?", ok=False, error="Expected request frame")
            return serialize(resp)

        req_id = frame.get("id", "?")
        method = frame.get("method", "")
        params = frame.get("params", {})

        # 第一条消息必须是 connect
        if not conn.authenticated and method != "connect":
            resp = ResponseFrame(id=req_id, ok=False, error="Must connect first")
            return serialize(resp)

        # 认证检查
        if self.registry.needs_auth(method) and not conn.authenticated:
            resp = ResponseFrame(id=req_id, ok=False, error="Not authenticated")
            return serialize(resp)

        try:
            result = await self.registry.dispatch(conn, method, params)
            resp = ResponseFrame(id=req_id, ok=True, payload=result)
        except ValueError as e:
            resp = ResponseFrame(id=req_id, ok=False, error=str(e))

        return serialize(resp)

    def add_connection(self) -> GatewayConnection:
        conn_id = str(uuid.uuid4())[:8]
        conn = GatewayConnection(conn_id=conn_id)
        self.connections[conn_id] = conn
        return conn

    def remove_connection(self, conn_id: str):
        self.connections.pop(conn_id, None)

    async def broadcast_event(self, event: str, data: dict[str, Any]):
        """向所有已认证连接广播事件"""
        frame = EventFrame(event=event, data=data)
        for conn in self.connections.values():
            if conn.authenticated:
                await conn.send(frame)


# ── 模拟客户端 ────────────────────────────────────────────────────

class GatewayClient:
    """模拟 Gateway 客户端"""

    def __init__(self, server: GatewayServer, name: str = "test-client"):
        self.server = server
        self.name = name
        self.conn: Optional[GatewayConnection] = None
        self._req_counter = 0

    def _next_id(self) -> str:
        self._req_counter += 1
        return f"req-{self._req_counter}"

    async def connect(self, password: str) -> dict[str, Any]:
        self.conn = self.server.add_connection()
        req = serialize(RequestFrame(
            id=self._next_id(), method="connect",
            params={"minProtocol": 1, "maxProtocol": 1, "password": password, "clientName": self.name},
        ))
        raw_resp = await self.server.handle_message(self.conn, req)
        return json.loads(raw_resp)  # type: ignore

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.conn:
            raise RuntimeError("Not connected")
        req = serialize(RequestFrame(id=self._next_id(), method=method, params=params or {}))
        raw_resp = await self.server.handle_message(self.conn, req)
        return json.loads(raw_resp)  # type: ignore


# ── Demo ──────────────────────────────────────────────────────────

async def main():
    print("=" * 64)
    print("OpenClaw Gateway RPC Demo")
    print("=" * 64)

    server = GatewayServer(password="secret123")
    client = GatewayClient(server, name="telegram-channel")

    # 1. 未认证时尝试调用方法
    print("\n── 1. 未认证调用 ──")
    conn = server.add_connection()
    raw = serialize(RequestFrame(id="x1", method="ping", params={}))
    resp_raw = await server.handle_message(conn, raw)
    resp = json.loads(resp_raw)
    print(f"  请求: ping (未连接)")
    print(f"  响应: ok={resp['ok']}, error={resp.get('error')}")
    server.remove_connection(conn.conn_id)

    # 2. 错误密码
    print("\n── 2. 认证失败 ──")
    resp = await client.connect("wrong-password")
    print(f"  请求: connect(password=wrong-password)")
    print(f"  响应: ok={resp['ok']}, error={resp.get('error')}")

    # 3. 正确连接
    print("\n── 3. 认证成功 ──")
    client2 = GatewayClient(server, name="discord-channel")
    resp = await client2.connect("secret123")
    print(f"  请求: connect(password=secret123)")
    print(f"  响应: ok={resp['ok']}")
    if resp["ok"]:
        payload = resp["payload"]
        print(f"  协议版本: {payload['protocol']}")
        print(f"  服务器: {payload['serverVersion']}")
        print(f"  连接ID: {payload['connId']}")

    # 4. 调用方法
    print("\n── 4. RPC 调用 ──")
    resp = await client2.call("list_agents")
    print(f"  请求: list_agents()")
    print(f"  响应: {json.dumps(resp['payload'], indent=2)}")

    resp = await client2.call("ping")
    print(f"\n  请求: ping()")
    print(f"  响应: pong={resp['payload']['pong']:.2f}")

    # 5. 发送消息（触发事件广播）
    print("\n── 5. 消息发送 + 事件广播 ──")
    resp = await client2.call("send_message", {"channel": "telegram", "text": "Hello from demo!"})
    print(f"  请求: send_message(channel=telegram)")
    print(f"  响应: id={resp['payload']['id']}, status={resp['payload']['status']}")

    # 检查广播的事件
    if not client2.conn.send_queue.empty():  # type: ignore
        event_raw = await client2.conn.send_queue.get()  # type: ignore
        event = json.loads(event_raw)
        print(f"  广播事件: {event['event']} → {json.dumps(event['data'])}")

    # 6. 未知方法
    print("\n── 6. 未知方法 ──")
    resp = await client2.call("nonexistent")
    print(f"  请求: nonexistent()")
    print(f"  响应: ok={resp['ok']}, error={resp.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
