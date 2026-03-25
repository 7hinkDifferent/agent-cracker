# Event-Driven Loop

最小化的事件驱动 agent 循环，复现 Gemini CLI 的核心：

```
while true:
  1. 调用 LLM，流式接收事件
  2. 收集 ToolCallRequest 事件
  3. 并发执行工具
  4. 反馈工具响应回 LLM
  5. 检查终止条件
```

## 运行方式

```bash
uv run --with google-generativeai,pydantic main.py
```

## 关键特性

1. **完全流式化**：每个 LLM 事件立即发出，支持实时 UI 更新
2. **事件类型枚举**：ToolCallRequest、Finished、Error 等
3. **轮数限制**：防止无限循环
4. **终止条件**：Finished (无工具) / Error / MaxTurns / UserAbort
5. **并发工具执行**：支持多个工具同时运行

## 代码结构

- `main.py` — 主循环实现 + 示例用法
- `types.py` — 事件和请求数据类型
- `event_translator.py` — Genai SDK 事件转译层

## 对应源码

- [packages/core/src/agent/legacy-agent-session.ts](../../../projects/gemini-cli/packages/core/src/agent/legacy-agent-session.ts) (L144-250)
- [packages/core/src/agent/agent-session.ts](../../../projects/gemini-cli/packages/core/src/agent/agent-session.ts) (L70-160)
