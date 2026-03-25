# eigent — Demo Overview

基于 [docs/eigent.md](../../docs/eigent.md) 分析，以下是构建最小可运行版本和复现特色机制所需的组件。

> Based on commit: [`38f8f2b`](https://github.com/eigent-ai/eigent/tree/38f8f2b292d7d1f64dbd211312ca335202565c83) (2026-03-25)

## MVP 组件

构建最小可运行版本需要以下组件：

- [x] **queue-event-loop** — 队列驱动的异步事件循环，Action 分发 + SSE 流式响应 (Python)
- [x] **workforce-orchestration** — 基于 CAMEL Workforce 的任务分解与并行 Agent 执行 (Python)
- [x] **agent-factory** — 8 类专业 Agent 工厂 + ListenChatAgent 事件织入 (Python)
- [x] **toolkit-dispatch** — Toolkit 三层体系：注册、收集、条件过滤 + @listen_toolkit 装饰器 (Python)
- [x] **prompt-assembly** — 角色化 system prompt 模板 + 动态变量注入 + 对话历史拼接 (Python)

## 平台机制

以下是超越 coding agent 的平台层机制（D9-D12），可复现为独立 demo：

- [ ] **sse-streaming** — SSE 事件流协议：Agent/Toolkit 激活事件 + 任务分解流式推送 (D9: 通道层) (Python)
- [ ] **trigger-webhook** — Webhook/Slack/Cron 触发器：外部事件驱动 Agent 任务 (D9/D11: 通道+自治) (Python)
- [ ] **note-collaboration** — NoteTakingToolkit 跨 Agent 笔记协作 + shared_files 约定 (D10: 协作记忆) (Python)
- [ ] **skill-config** — 多�� Skill 配置体系：项目级 > 用户级，按 Agent 类型权限控制 (D12: 特色) (Python)

## 进阶机制

以下是该 agent 的特色功能，可选择性复现：

- [ ] **complexity-router** — 任务复杂度判断：简单问题直接回答 vs 复杂任务启动 Workforce (Python)
- [ ] **failure-retry-replan** — Workforce 失败处理：retry + replan 策略 + _analyze_task 质量评估 (Python)
- [ ] **mcp-lifecycle** — MCP 服务器全生命周期管理：安装、OAuth 认证、工具注入、连接池 (Python)

## 完整串联

- [ ] **mini-eigent** — 组合以上 MVP 组件 + 平台机制的最小完整 agent

## 进度

MVP: 5/5 | 平台: 0/4 | 进阶: 0/3 | 串联: 0/1 | 总计: 5/13
