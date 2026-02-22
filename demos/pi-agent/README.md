# Pi-Agent — Demo Overview

基于 [docs/pi-agent.md](../../docs/pi-agent.md) 分析，以下是值得复现的核心机制。

## Demo 清单

- [x] **event-stream** — EventStream 异步迭代器（自定义 async iterator + event queue，流式事件传递）
- [x] **pluggable-ops** — Pluggable Operations 模式（工具执行环境依赖注入，本地/SSH/Docker 透明切换）
- [x] **steering-queue** — Steering/Follow-up 双消息队列（实时干预 Agent 执行，中断 vs 排队两种模式）
- [x] **structured-compaction** — 结构化 Compaction 摘要（固定格式 + 增量 UPDATE，阈值/溢出双触发）
- [ ] **multi-provider-overflow** — 多 Provider Overflow 检测（10+ provider 错误模式匹配 + 静默溢出检测）
- [ ] **extension-hooks** — 深度扩展系统（生命周期钩子 + 动态 tool/command 注册 + UI 覆盖）

## 进度

4/6 已完成
