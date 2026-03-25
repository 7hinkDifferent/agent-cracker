# Session Replay

复现 Gemini CLI 的会话恢复与事件重放机制。

## 原理

Gemini CLI 支持**精确事件重放**，让用户可从任意事件点恢复：

```
[Event 1: text]
[Event 2: tool_call]          ← User wants to resume from here
[Event 3: tool_result]
[Event 4: agent_end]

↓

Load events 1-2 from history → Resume streaming new events
```

这与传统会话恢复不同：

- **传统**：恢复整个对话上下文，从头计算
- **Gemini CLI**：重放确切事件，支持分支与返工

## 关键特性

1. **事件序列存储**：每个 LLM 事件有唯一 ID
2. **精确定位**：通过 eventId 或 streamId 定位重放起点
3. **流式订阅**：重放→接收新流，无缝转换
4. **分支支持**：可从中间点创建新分支

## 运行方式

```bash
uv run main.py
```

## 对应源码

- [packages/core/src/agent/agent-session.ts](../../../projects/gemini-cli/packages/core/src/agent/agent-session.ts) (~180 行 stream() 方法)
