# Hermes Agent — gateway-session-routing

## 目标

用最简代码复现 Hermes 的 gateway 入口：**外部 `MessageEvent` 标准化 + `build_session_key()` 路由到稳定 session**。

## 原理

Hermes 的 gateway 会接收来自 Telegram、Slack、Discord、Signal 等不同平台的消息。它不会把这些平台细节直接暴露给主循环，而是先统一成 `MessageEvent` / `SessionSource`，再通过 `build_session_key()` 算出会话边界。

DM、群聊、thread 的 session key 规则不同：DM 通常按 chat 隔离；群聊可以按 user 再切一层；thread 则会额外拼进 key。这样不同入口都能复用同一个 `AIAgent`，而 session continuity 仍然稳定。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/gateway-session-routing/
├── README.md
├── gateway_router.py
└── main.py
```

## 关键代码解读

```python
def build_session_key(source: SessionSource, group_sessions_per_user: bool = True) -> str:
    if source.chat_type == "dm":
        if source.thread_id:
            return f"agent:main:{source.platform}:dm:{source.chat_id}:{source.thread_id}"
        return f"agent:main:{source.platform}:dm:{source.chat_id}"
```

Hermes 的平台层关键不是“收到消息”，而是**把消息稳定地映射回同一个 session**。一旦 session key 稳定，后面的 memory、prompt cache、delivery 都能继续复用。

## 与原实现的差异

- 原版还包含 pairing / allowlist / slash command / running-agent guard；demo 只保留路由主线
- 原版 `SessionSource` 字段更多，包含 chat_name、topic、alt ids 等；demo 只保留决定 session key 的核心字段
- 原版会把 session context 注入 prompt；demo 只演示 key 计算和消息归档

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `gateway/run.py`, `gateway/session.py`
