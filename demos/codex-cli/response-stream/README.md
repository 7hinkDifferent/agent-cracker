# Demo: Codex CLI — Response Stream

## 目标

用最简代码复现 Codex CLI 的流式响应解析机制。

## MVP 角色

流式响应解析是 agent 的"耳朵"——从 LLM 的 SSE 流中实时解析出文本内容和 tool calls。Codex CLI 的特色是**增量拼接**：function call 的 arguments 分多个 chunk 到达，需要累积拼接为完整 JSON。

## 原理

### SSE 流格式

```
event: message
data: {"choices":[{"delta":{"content":"Hello"}}]}

event: message
data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"cmd"}}]}}]}

data: [DONE]
```

### 增量拼接

LLM 返回 tool call 时，`arguments` 字段分多个 chunk：
```
chunk 1: {"command"       ← 不完整
chunk 2: : "ls -la"}      ← 拼接后完整
```

需要累积所有 chunk，直到 JSON 可以完整解析。

### Token 估算

```python
tokens ≈ bytes / 4   # 保守高估，无需 tokenizer
```

## 运行

```bash
cd demos/codex-cli/response-stream
uv run python main.py
```

## 文件结构

```
demos/codex-cli/response-stream/
├── README.md       # 本文件
├── stream.py       # 可复用模块: SSE 解析 + 增量拼接 + 响应组装
└── main.py         # Demo 入口
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 语言 | Rust | Python |
| SSE 解析 | eventsource-stream + 异步 | 同步文本解析 |
| 流式回调 | tokio channel + TUI 实时渲染 | 顺序处理 |
| 超时处理 | tokio::timeout | 省略 |
| 截断 | UTF-8 边界安全切割 | 省略 |

## 相关文档

- 分析文档: [docs/codex-cli.md](../../../docs/codex-cli.md)
- 原项目: https://github.com/openai/codex
- 基于 commit: `0a0caa9`
- 核心源码: `codex-rs/core/src/stream.rs`, `codex-rs/core/src/turns.rs`
