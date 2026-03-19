# OpenClaw — Auth Profile Rotation

复现 OpenClaw 的多 API Key 优先级轮转和 Cooldown 追踪机制。

## 机制说明

OpenClaw 管理多个 Auth Profile（不同 provider 的 API Key），按优先级排序，失败时自动轮转。

```
请求 → 选择最高优先级的非 cooldown profile
  → 成功 → 更新统计
  → 失败 → classifyFailoverReason()
            → 标记 cooldown（按错误类型时长不同）
            → 选择下一个可用 profile
            → 所有耗尽 → FailoverError
```

| 错误类型 | Cooldown | 说明 |
|---------|----------|------|
| rate-limit | 60s | 短暂限流 |
| auth | 5min | Key 可能过期 |
| billing | 1h | 需要充值 |
| timeout | 30s | 短暂网络问题 |
| server-error | 2min | 服务端故障 |

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/agents/auth-profiles.ts` | Profile 管理与 cooldown |
| `src/agents/pi-embedded-runner/run.ts` | 轮转调用逻辑 |

## 运行

```bash
uv run python main.py
```
