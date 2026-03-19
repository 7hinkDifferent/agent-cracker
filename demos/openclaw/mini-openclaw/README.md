# OpenClaw — Mini-OpenClaw 串联 Demo

组合所有 MVP 组件 + 平台机制的最小完整 Agent 平台。

## 架构

```
Telegram ──┐
Discord  ──┼─→ [路由引擎] → [Session Key]
WhatsApp ──┘       │
                   ▼
[记忆检索] ──→ [Prompt 构建] ←── [工具选择]
                   │
                   ▼
            [内嵌引擎 + Fallback]
                   │
            ┌──────┼──────┐
            ▼      ▼      ▼
         Claude  GPT-4o  Gemini

[Cron 调度] ──→ [Heartbeat]
[子Agent] ──→ [spawn/steer/kill]
```

## 组合的模块

通过 `sys.path` 导入兄弟 MVP demo 的模块，**不重写代码**：

| 模块 | 来源 |
|------|------|
| `RoutingEngine` | `channel-routing/main.py` |
| `GatewayServer` | `gateway-rpc/main.py` |
| `ToolPolicyPipeline` | `tool-profile/main.py` |
| `SystemPromptBuilder` | `system-prompt-builder/main.py` |
| `EmbeddedEngine` | `embedded-engine/main.py` |
| `HybridMemorySearch` | `hybrid-memory/main.py` |
| `CronScheduler` | `cron-scheduler/main.py` |
| `SubagentOrchestrator` | `subagent-orchestration/main.py` |

## 完整流程

1. **消息到达** → Channel Routing 路由到正确 Agent + Session
2. **记忆检索** → Hybrid Memory 查找相关历史
3. **工具选择** → Tool Profile 按场景筛选可用工具
4. **Prompt 构建** → System Prompt Builder 组装 13 sections
5. **LLM 调用** → Embedded Engine 含 Model Fallback
6. **定时任务** → Cron Scheduler 触发周期性工作
7. **子 Agent** → Subagent Orchestrator 派生独立 worker

## 运行

```bash
uv run python main.py
```
