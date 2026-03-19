# OpenClaw — Embedded Engine

复现 OpenClaw 内嵌 pi-agent 的调用链和 Model Fallback 机制（Dimension 2: Agent Loop）。

## 机制说明

OpenClaw 不重造 Agent 核心，而是将 pi-agent 作为**库**内嵌调用，在其之上增加了 Model Fallback 和 Auth Profile 轮转。

```
runEmbeddedPiAgent()
  │
  ├─ 按 priority 排序 Auth Profiles
  │
  ├─ while (有可用 profile):
  │    ├─ 选择第一个非 cooldown 的 profile
  │    ├─ runEmbeddedAttempt(profile)
  │    │    ├─ 成功 → 返回结果
  │    │    └─ 失败 → classifyFailoverReason(error)
  │    │              ├─ rate-limit → cooldown 60s → 下一个 profile
  │    │              ├─ auth       → cooldown 5min → 下一个 profile
  │    │              ├─ billing    → 不可恢复 → 终止
  │    │              ├─ timeout    → cooldown 30s → 下一个 profile
  │    │              └─ context-overflow → 触发 compaction → 重试
  │    └─ 切换到下一个 profile
  │
  └─ 所有 profile 耗尽 → FailoverError
```

### Failover 分类器

| 错误类型 | Cooldown | 策略 |
|---------|----------|------|
| rate-limit | 60s | 切换 provider |
| auth | 5min | 可能 key 过期 |
| billing | 1h | 不可恢复，立即终止 |
| timeout | 30s | 短暂等待后重试 |
| context-overflow | — | 触发 compaction |

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/agents/pi-embedded-runner/run.ts` | 内嵌运行器主循环 |
| `src/agents/pi-embedded-runner/run/attempt.ts` | 单次运行尝试 |
| `src/auto-reply/reply/agent-runner-execution.ts` | Model Fallback 编排 |

## 运行

```bash
uv run python main.py
```

## 关键简化

| 原始实现 | Demo 简化 |
|---------|----------|
| 真实 pi-agent createAgentSession | 模拟 LLM 调用 |
| 复杂的 compaction + session 管理 | 省略 compaction 流程 |
| Auth Profile 从配置文件加载 | 内存中直接构建 |
| Anthropic magic string 清理 | 省略 |
