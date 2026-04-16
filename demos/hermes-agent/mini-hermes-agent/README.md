# Hermes Agent — mini-hermes-agent 串联 Demo

## 目标

组合 Hermes 的 5 个 MVP 组件 + 4 个平台机制，得到一个最小可运行的**个人 agent 平台**：消息入口 → session 路由 → prompt + memory → tool loop → ACP / cron 输出。

## 组合的模块

本 demo **直接 import 兄弟目录模块**，不重写实现：

| 模块 | 来源 |
|------|------|
| `HermesLoopAgent` | `agent-session-loop/loop_core.py` |
| `registry` + `reset_and_discover` | `tool-registry-discovery/tool_registry.py` |
| `PromptAssembler` | `prompt-assembly/prompt_builder_demo.py` |
| `SessionMemoryStore` | `session-memory-search/memory_store.py` |
| `TerminalManager` | `terminal-multibackend/terminal_backends.py` |
| `GatewayRunner` + `build_session_key` | `gateway-session-routing/gateway_router.py` |
| `HermesACPBridge` | `acp-bridge/acp_bridge.py` |
| `CronRunner` | `cron-delivery/cron_delivery.py` |
| `SandboxExecutor` | `approval-sandbox/approval_sandbox.py` |

## 完整流程

1. Telegram 消息进入 `GatewayRunner`
2. `build_session_key()` 生成稳定 session key
3. `SessionMemoryStore` 提供 `MEMORY.md` / `USER.md`
4. `PromptAssembler` 构建 cached prompt + ephemeral overlay
5. `ToolRegistry` 决定哪些工具对模型可见
6. `HermesLoopAgent` 执行 tool loop
7. `SandboxExecutor` 守卫 terminal 命令
8. 同一结果还能被 `HermesACPBridge` 映射给 IDE，或由 `CronRunner` 发送定时结果

## 学习建议

推荐在跑这个串联 demo 之前，先分别看：
- `agent-session-loop`
- `prompt-assembly`
- `session-memory-search`
- `gateway-session-routing`
- `approval-sandbox`

这样在看 `mini-hermes-agent` 输出时，能更容易识别每一段输出分别来自哪个兄弟模块。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/mini-hermes-agent/
├── README.md
└── main.py
```

## 运行后建议观察

1. **入口层**：先看 `session_key`，理解消息如何落到稳定会话
2. **能力暴露**：再看 `Visible tools`，理解 registry + toolset filtering 的效果
3. **长期记忆**：`Memory recall before the turn` 展示 session_search 怎样在正式运行前补回历史细节
4. **统一运行时**：随后看 loop events、ACP mirror、Cron delivery，理解同一内核如何被多个入口复用

## 与原实现的差异

- 原版是真正可长期运行的统一平台，这里只保留一条最短主干路径
- 原版 tool / gateway / ACP / cron 都有更复杂的错误恢复与状态持久化；demo 只做机制拼接
- 原版还包含 skills、subagent、fallback recovery、compression lineage 等进阶能力；这里重点是把 MVP + 平台机制接起来

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `run_agent.py`, `gateway/run.py`, `gateway/session.py`, `acp_adapter/entry.py`, `cron/`
