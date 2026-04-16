# Hermes Agent — agent-session-loop

## 目标

用最简代码复现 Hermes `run_conversation()` 主循环：provider fallback、tool loop、interrupt 与 context compression 如何围绕同一个 `AIAgent` 协作。

## MVP 角色

这是 Hermes MVP 中的**主循环**。其他组件（prompt、tool registry、memory、terminal backend）最终都要被这个循环驱动起来。

## 原理

在原始项目里，`AIAgent.run_conversation()` 不是单纯的“发一次 LLM 请求”。它会维护一个稳定的 cached system prompt，然后在每轮里做 provider 调用、解析 tool calls、回填 tool 结果、必要时 context compression、以及在 provider 失败时切换 fallback provider。

Hermes 的特殊之处在于：CLI、gateway、ACP、cron 都复用同一个主循环，所以 interrupt、安全审批、session continuation、subagent budget 等能力最终都在这个循环里收口。这个 demo 刻意保留这种“统一入口”的感觉，但把 provider 和 tool 都换成脚本化 mock。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/agent-session-loop/
├── README.md
├── loop_core.py        # 最小 Hermes-style 主循环
└── main.py             # 演示 fallback / interrupt / compression
```

## 关键代码解读

```python
for iteration in range(1, self.max_iterations + 1):
    reason = self.interrupt.consume()
    if reason:
        messages.append(Message("system", f"[interrupt] {reason}"))

    if self.compression.should_compress(messages):
        messages = self.compression.compress(messages)

    turn = self._call_with_fallback(messages, self._cached_system_prompt)
    if not turn.tool_calls:
        return turn.content

    for call in turn.tool_calls:
        result = self.tools[call.name](call.arguments)
        messages.append(Message("tool", result, tool_call_id=call.id))
```

这段逻辑对应 Hermes 的核心循环：
- 每轮先消费 interrupt 信号
- token 超阈值时先做压缩
- 调用 provider，失败则 fallback
- 如果有 tool calls，就执行工具并把结果塞回历史
- 没有 tool calls 时直接结束当前 turn

## 运行后建议观察

1. **事件流顺序**：先看 provider fallback，再看 tool loop，最后看 compression 何时触发
2. **history 截面**：注意最终保存下来的并不是所有中间消息，而是包含一个 `[compressed-summary]`
3. **为什么适合平台型 agent**：同一条 loop 能同时服务 CLI / gateway / ACP / cron

## 与原实现的差异

- 原版同时支持 OpenAI / Codex Responses / Anthropic 三套 API 格式，这里统一成 `MockProvider`
- 原版会把 session 写入 SQLite 并复用 system prompt 缓存；demo 只保留内存中的 `history`
- 原版 compression 会维护 lineage 与更复杂的消息保护规则；demo 仅保留“压缩中间消息”的核心思想

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `run_agent.py`
