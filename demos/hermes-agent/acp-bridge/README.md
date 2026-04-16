# Hermes Agent — acp-bridge

## 目标

用最简代码复现 Hermes 的 ACP 适配层：把 agent 运行中的 thinking / tool / done 回调翻译成 **JSON-RPC `session_update` 事件**，供 IDE 客户端消费。

## 原理

Hermes 不是简单地暴露一个 HTTP API，而是单独做了一层 ACP（Agent Client Protocol）桥接。编辑器里的 VS Code、Zed、JetBrains 等客户端通过 stdio JSON-RPC 与 Hermes 通信；Hermes 则把内部主循环里的阶段性回调转换成 `session_update` 事件流。

这让 Hermes 可以继续复用统一的 `AIAgent` 核心，而不必为了 IDE 场景再写一套专门的 agent runtime。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/acp-bridge/
├── README.md
├── acp_bridge.py
└── main.py
```

## 关键代码解读

```python
if request.method == "agent.tool":
    self.send_event(
        "session_update",
        stage="tool",
        tool=request.params["tool"],
        preview=request.params.get("preview", ""),
    )
```

ACP bridge 的重点是**协议翻译**：Hermes 内部说的是 loop callback / tool progress，IDE 客户端需要的是规范化的 JSON-RPC 事件。demo 把这种转换缩成一个小型消息映射器。

## 与原实现的差异

- 原版通过 stdio 持续收发 JSON-RPC，并维护 session 生命周期；demo 用内存 `outbox` 简化传输
- 原版会桥接更多事件类型（reasoning、step、error、attachments 等）；demo 只保留最核心的 4 种阶段
- 原版与真实 `AIAgent` 强绑定；demo 用脚本化请求模拟 IDE 侧交互

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `acp_adapter/entry.py`, `acp_adapter/server.py`, `acp_adapter/session.py`
