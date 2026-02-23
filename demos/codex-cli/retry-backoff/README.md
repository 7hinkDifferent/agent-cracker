# retry-backoff — 指数退避重试

复现 Codex CLI 的指数退避重试机制：退避函数、±10% 抖动、错误可重试性分类。

> Based on commit: [`0a0caa9`](https://github.com/openai/codex/tree/0a0caa9df266ebc124d524ee6ad23ee6513fe501) (2026-02-23)

## 运行

```bash
uv run python main.py
```

## Demo 内容

| Demo | 说明 |
|------|------|
| Backoff Sequence | 指数退避序列：200ms → 400ms → ... → 25600ms |
| Jitter Distribution | ±10% 抖动分布可视化（直方图） |
| Error Classification | 12 种错误类型的可重试性分类 |
| Retry Success | 暂态故障 → 退避重试 → 恢复成功 |
| Non-Retryable Error | 不可重试错误 → 立即停止 |
| Retry Exhaustion | 所有重试用尽 → 返回最后错误 |

## 核心机制

```
退避公式: delay = 200ms × 2.0^(attempt-1) × uniform(0.9, 1.1)

attempt  base      range (±10%)
  1      200ms     180ms ~ 220ms
  2      400ms     360ms ~ 440ms
  3      800ms     720ms ~ 880ms
  4      1600ms    1440ms ~ 1760ms
  5      3200ms    2880ms ~ 3520ms
  ...
```

## 错误分类

| 可重试（transient） | 不可重试（permanent） |
|---------------------|----------------------|
| SSE 断连 | 用户中断（Ctrl+C） |
| 命令超时 | 上下文溢出 |
| HTTP 429/5xx | 配额用完 |
| 连接失败 | 请求格式错误 |
| 响应流中断 | 沙箱拒绝 |
| | 认证失败 |

## 核心源码

| 机制 | 原始文件 |
|------|----------|
| 退避函数 | `codex-rs/core/src/util.rs` → `backoff()` |
| 错误分类 | `codex-rs/core/src/error.rs` → `CodexErr::is_retryable()` |

## 与原实现的差异

- **不实际等待**: `simulate_delay=False` 跳过 sleep（演示速度）
- **公式完全一致**: 200ms 初始 × 2.0 因子 × ±10% 抖动
- **错误分类完整**: 覆盖 codex-cli 全部 12 种 CodexErr 变体
