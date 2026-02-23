# Demo: Pi-Agent — Multi-Provider Overflow

## 目标

用最简代码复现 Pi-Agent 的多 Provider Overflow 检测与恢复机制。

## 原理

不同 LLM Provider 报告 context overflow 的方式各不相同。Pi-Agent 通过**模式匹配 + 静默检测 + 分层重试**实现了跨 provider 的统一溢出处理：

### 错误模式匹配

| Provider | 错误格式 |
|----------|----------|
| Anthropic | `"prompt is too long: X tokens > Y maximum"` |
| OpenAI | `"exceeds the context window"` / `"maximum context length is X"` |
| Google | `"input token count (X) exceeds the maximum (Y)"` |
| xAI | `"maximum prompt length is X"` |
| Mistral/Cerebras | HTTP 400/413，body 为空或简短 |

### 静默溢出

部分 provider 不报错但实际溢出——通过 `usage.input > contextWindow` 检测。

### 多层重试策略

| 层级 | 错误类型 | 策略 |
|------|---------|------|
| LLM Provider 层 | 速率限制 | 指数退避（base 1s，最多 3 次） |
| LLM Provider 层 | 服务过载 | 指数退避，尊重 Retry-After 头 |
| Agent Session 层 | Context overflow | 触发 compaction → 压缩后重试 |

## 运行

```bash
cd demos/pi-agent/multi-provider-overflow
uv run python main.py
```

## 文件结构

```
demos/pi-agent/multi-provider-overflow/
├── README.md       # 本文件
└── main.py         # Demo（自包含，含检测函数 + 5 个演示）
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 语言 | TypeScript | Python |
| Provider 数量 | 6+ 完整 SDK | 5 种模式匹配 |
| 重试机制 | 真实指数退避 + HTTP 调用 | 逻辑演示（无实际重试） |
| Compaction 触发 | 真实 LLM 摘要压缩 | 计算演示 |
| 流式溢出检测 | SSE 中途检测 | 省略 |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 基于 commit: `316c2af`
- 核心源码: `packages/ai/src/utils/overflow.ts`
