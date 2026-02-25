# nanoclaw — Demo Overview

基于 [docs/nanoclaw.md](../../docs/nanoclaw.md) 分析，以下是构建最小可运行版本和复现特色机制所需的组件。

> Based on commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147) (2026-02-25)

## MVP 组件

构建最小可运行版本需要以下组件：

- [ ] **message-poll-loop** — 消息轮询 + 组群路由 + 容器调度主循环 (Python)
- [ ] **container-spawn** — Docker 容器启动 + mount 构建 + 哨兵标记流式输出解析 (Python)
- [ ] **ipc-mcp-server** — 容器内 MCP 工具服务器 (send_message/schedule_task 等) (TypeScript — 依赖 @modelcontextprotocol/sdk)
- [ ] **agent-runner** — 容器内 Claude SDK query() 循环 + MessageStream IPC 管道 (TypeScript — 依赖 @anthropic-ai/claude-agent-sdk)
- [ ] **group-queue** — 每组消息队列 + 全局并发控制 + 指数退避重试 (Python)

## 平台机制

以下是超越 coding agent 的平台层机制（D9-D12），可复现为独立 demo：

- [ ] **channel-abstraction** — Channel 接口 + WhatsApp 适配 + JID 路由 (D9: 通道层) (Python)
- [ ] **sqlite-persistence** — SQLite 消息/会话/任务持久化 + 游标恢复 (D10: 记忆) (Python)
- [ ] **mount-security** — 外部 allowlist + 阻止列表 + symlink 解析安全校验 (D11: 安全) (Python)
- [ ] **task-scheduler** — Cron/interval/once 三种调度 + group/isolated context mode (D11: 自治) (Python)

## 进阶机制

以下是该 agent 的特色功能，可选择性复现：

- [ ] **sentinel-stream-parser** — 哨兵标记（START/END marker）的流式 stdout JSON 解析 (Python)
- [ ] **skills-engine** — Skill 安装/卸载/rebase/冲突检测的代码变换引擎 (TypeScript — 依赖 git 操作)
- [ ] **precompact-archive** — PreCompact hook 对话归档 (Markdown 导出) (Python)
- [ ] **cursor-rollback** — 消息游标推进 + 失败回滚的 at-least-once 语义 (Python)

## 完整串联

- [ ] **mini-nanoclaw** — 组合以上 MVP 组件 + 平台机制的最小完整 agent

## 进度

MVP: 0/5 | 平台: 0/4 | 进阶: 0/4 | 串联: 0/1 | 总计: 0/14
