# OpenClaw — Gateway RPC

复现 OpenClaw 的 WebSocket RPC Gateway 控制面（Dimension 9: 通道层与网关）。

## 机制说明

Gateway 是 OpenClaw 的**中央控制面**，所有通道（Discord/Telegram/Slack 等）通过 WebSocket RPC 与之通信。

```
通道适配器 ──WebSocket──→ Gateway Server (:18789)
                           │
                           ├─ 握手认证 (connect + 协议版本协商)
                           ├─ 方法路由 (MethodRegistry)
                           ├─ 认证门控 (auth_required 标记)
                           └─ 事件广播 (broadcast_event)
```

### 帧协议

| 帧类型 | 方向 | 字段 |
|--------|------|------|
| `req` | client→server | `id`, `method`, `params` |
| `res` | server→client | `id`, `ok`, `payload`/`error` |
| `event` | server→client | `event`, `data` |

### 连接生命周期

1. 建立 WebSocket → 分配 `conn_id`
2. 首条消息**必须**是 `connect`（含密码 + 协议版本范围）
3. 认证通过后可调用任意注册方法
4. 方法执行结果以 `res` 帧返回
5. 服务端可主动推送 `event` 帧给所有已认证连接

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/gateway/server/` | Gateway 服务器实现 |
| `src/gateway/server/ws-connection/message-handler.ts` | 消息帧处理与握手 |
| `src/gateway/protocol.ts` | 协议帧类型定义 |

## 运行

```bash
uv run python main.py
```

## 关键简化

| 原始实现 | Demo 简化 |
|---------|----------|
| 真实 WebSocket (ws) | 直接函数调用模拟 |
| 设备密钥对 + 签名认证 | 简化为密码认证 |
| nonce 防重放 | 省略 |
| 协议版本范围协商 | 保留核心逻辑 |
