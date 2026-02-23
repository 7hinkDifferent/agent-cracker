# Pi-Agent — Demo Overview

基于 [docs/pi-agent.md](../../docs/pi-agent.md) 分析，以下是构建最小可运行版本和复现特色机制所需的组件。

> Based on commit: [`316c2af`](https://github.com/badlogic/pi-mono/tree/316c2afe38d34a352474b852b95195be266709cb) (2026-02-23)

## MVP 组件

构建最小可运行版本需要以下组件：

- [ ] **agent-session-loop** — Agent 会话主循环（消息→LLM→tool call→结果回填，含 steering 中断）(TypeScript — 依赖语言特性: async/await + EventStream async iterator 是核心抽象)
- [x] **pluggable-ops** — Pluggable Operations 模式（工具执行环境依赖注入，本地/SSH/Docker 透明切换）(Python)
- [ ] **prompt-builder** — Prompt 构建器（system prompt 分层组装 + tool schema 注入 + 上下文拼接）(Python)
- [ ] **llm-multi-provider** — 多 Provider LLM 调用（统一接口适配 OpenAI/Anthropic/Google + 流式响应解析）(Python)

## 进阶机制

以下是该 agent 的特色功能，可选择性复现：

- [x] **event-stream** — EventStream 异步迭代器（自定义 async iterator + event queue，流式事件传递）
- [x] **steering-queue** — Steering/Follow-up 双消息队列（实时干预 Agent 执行，中断 vs 排队两种模式）
- [x] **structured-compaction** — 结构化 Compaction 摘要（固定格式 + 增量 UPDATE，阈值/溢出双触发）
- [ ] **multi-provider-overflow** — 多 Provider Overflow 检测（10+ provider 错误模式匹配 + 静默溢出检测）
- [ ] **extension-hooks** — 深度扩展系统（生命周期钩子 + 动态 tool/command 注册 + UI 覆盖）

## 完整串联

- [ ] **mini-pi** — 组合以上 MVP 组件的最小完整 agent

## 进度

MVP: 1/4 | 进阶: 3/5 | 总计: 4/10
