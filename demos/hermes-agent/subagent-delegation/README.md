# Hermes Agent — subagent-delegation

## 目标

用最简代码复现 Hermes 的子 agent 委派：**fresh context、并行上限、深度限制与 blocked toolsets**。

## 原理

Hermes 的 `delegate_task` 不会把父会话的全部历史直接塞给子 agent，而是给每个 child 一个新的上下文、聚焦后的 goal，以及裁剪过的工具集合。这样父会话只看到总结结果，而不是每个子 agent 的全部中间推理。

同时，Hermes 会限制 delegation 深度和并行 child 数量，并去掉高风险工具（再次 delegation、clarify、memory、send_message、execute_code 等），防止子 agent 失控。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/subagent-delegation/
├── README.md
├── delegation.py
└── main.py
```

## 关键代码解读

```python
if task.depth >= MAX_DEPTH:
    raise DelegationError(f"Delegation depth limit reached ({MAX_DEPTH})")

return [toolset for toolset in toolsets if toolset not in BLOCKED_TOOLSETS]
```

Hermes 的核心思想不是“能开多少子 agent”，而是**如何让子 agent 在受控边界内工作**：新上下文、有限并行、禁止递归型危险能力。

## 与原实现的差异

- 原版会真的构造 child `AIAgent`、分配独立 task/session、并回传结构化 summary；demo 只返回文本摘要
- 原版既支持单任务也支持 batch delegation；demo 重点展示 batch + guardrails
- 原版还有 spinner/progress callback；demo 不处理 UI，只看治理逻辑

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `tools/delegate_tool.py`
