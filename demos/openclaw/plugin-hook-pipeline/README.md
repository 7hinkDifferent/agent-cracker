# OpenClaw — Plugin Hook Pipeline

复现 OpenClaw 的 Plugin Hook 管道（Dimension 12: 其他特色机制）。

## 机制说明

OpenClaw 提供 4 阶段 hook 管道，插件可在 Agent 生命周期的关键节点介入。

```
before_prompt_build → before_agent_start → [Agent 运行]
  → tool_call（每次调用前，可拦截）
  → tool_result（每次返回后，可统计）
```

每个阶段按插件注册顺序链式执行，任何 hook 可标记 `intercepted` 阻断后续。

## 对应源��

| 文件 | 作用 |
|------|------|
| `src/plugin-sdk/` | Plugin SDK 定义 |
| `src/extensionAPI.ts` | 扩展 API |

## 运行

```bash
uv run python main.py
```
