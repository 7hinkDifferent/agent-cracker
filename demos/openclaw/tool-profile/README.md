# OpenClaw — Tool Profile

复现 OpenClaw 的 4 档渐进 Tool Profile 策略和 Tool Policy Pipeline（Dimension 3: Tool 系统）。

## 机制说明

OpenClaw 管理 47+ 个工具，通过 **4 档 Profile** 控制不同场景下的工具可用性：

| Profile | 场景 | 工具数 |
|---------|------|--------|
| `minimal` | 子 agent / 状态监控 | ~1 |
| `coding` | 编码任务 | ~15 |
| `messaging` | 消息通信 | ~5 |
| `full` | 全功能 Agent | 全部 |

### Policy Pipeline

工具的最终可用集合由 5 阶段流水线决定：

```
全量工具目录
  → Stage 1: Profile 过滤（按档位筛选）
  → Stage 2: Owner-only 检查（非 owner 移除 cron/gateway 等）
  → Stage 3: Deny list（显式禁止）
  → Stage 4: Allow list（显式允许，可覆盖 profile 限制）
  → Stage 5: Plugin 扩展（注入插件工具）
  → 最终可用工具集
```

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/agents/tool-catalog.ts` | 47 个核心工具定义 + 4 档 profile |
| `src/agents/tool-policy.ts` | Policy pipeline + owner-only 拦截 |

## 运行

```bash
uv run python main.py
```

## 关键简化

| 原始实现 | Demo 简化 |
|---------|----------|
| 47 个核心工具 | 精选 23 个代表性工具 |
| TypeBox schema 校验 | 省略 schema |
| expandPluginGroups 宏展开 | 直接追加 plugin 工具 |
| Sandbox 路径覆盖 | 省略沙箱路径处理 |
