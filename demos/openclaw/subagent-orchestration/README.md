# OpenClaw — Subagent Orchestration

复现 OpenClaw 的子 Agent 生命周期管理（Dimension 11: 安全模型与自治）。

## 机制说明

OpenClaw 支持完整的子 Agent 编排：spawn → steer → kill，含深度限制和结果自动通知。

```
Main Agent
  │
  ├─ sessions_spawn(task="分析日志", mode="run")
  │   → Sub-Agent A（独立 session，minimal prompt）
  │   → 完成后自动 announce 回 Main Agent
  │
  ├─ subagents steer(message="优先处理错误日志")
  │   → 中途调整 Sub-Agent 方向
  │
  └─ subagents kill(agentId)
      → 终止子 agent
```

### Spawn 模式

| 模式 | 说明 | 生命周期 |
|------|------|----------|
| `run` | 一次性执行 | 完成后自动结束 |
| `session` | 持久会话 | 等待后续交互或手动 kill |

### 安全限制

| 限制 | 值 | 说明 |
|------|------|------|
| MAX_SPAWN_DEPTH | 3 | 防止无限递归派生 |
| MAX_CHILDREN_PER_AGENT | 5 | 每个 agent 最多 5 个子 agent |

### Session Key 格式

```
agent:{parentId}:subagent:{childId}
```

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/agents/subagent-spawn.ts` | 子 agent 派生逻辑 |
| `src/agents/tools/subagents-tool.ts` | subagents tool (list/kill/steer) |
| `src/agents/tools/sessions-spawn-tool.ts` | sessions_spawn tool |

## 运行

```bash
uv run python main.py
```

## 关键简化

| 原始实现 | Demo 简化 |
|---------|----------|
| 真实 pi-agent session 创建 | 模拟 agent 实例 |
| Subagent Context 注入 system prompt | 省略 |
| 通过 enqueueSystemEvent 通知 | 直接事件记录 |
| sessions_send 横向通信 | 省略 |
