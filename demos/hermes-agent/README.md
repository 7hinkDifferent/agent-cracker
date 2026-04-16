# hermes-agent — Demo Overview

基于 [docs/hermes-agent.md](../../docs/hermes-agent.md) 分析，以下是构建最小可运行版本和复现特色机制所需的组件。

> Based on commit: [`722331a`](https://github.com/NousResearch/hermes-agent/tree/722331a57de9e18f134c896d733870b4a493dc84) (2026-04-15)

## MVP 组件

构建最小可运行版本需要以下组件：

- [x] **agent-session-loop** — `run_conversation()` 主循环：API 调用、tool loop、interrupt、fallback、compression (Python)
- [x] **tool-registry-discovery** — AST 扫描 + `registry.register()` 自注册 + toolset 过滤 (Python)
- [x] **prompt-assembly** — SOUL/memory/skills/context/platform hints 分层组装，区分 cached 与 ephemeral prompt (Python)
- [x] **session-memory-search** — `MEMORY.md`/`USER.md` + SQLite FTS5 `session_search` 双层长期记忆 (Python)
- [x] **terminal-multibackend** — local/docker/ssh/modal/daytona/singularity 统一终端抽象 (Python)

## 平台机制

以下是超越 coding agent 的平台层机制（D9-D12），可复现为独立 demo：

- [x] **gateway-session-routing** — 多平台 `MessageEvent` 标准化 + `build_session_key()` 会话路由 (D9: 通道层) (Python)
- [x] **acp-bridge** — ACP stdio JSON-RPC 桥接，把 Hermes 接入 VS Code/Zed/JetBrains (D9/D12: IDE 接入) (Python)
- [x] **cron-delivery** — fresh session 定时任务 + skill 注入 + 跨平台 delivery (D11: 自治调度) (Python)
- [x] **approval-sandbox** — dangerous command 审批 + execute_code/terminal 多后端安全执行 (D11: 安全) (Python)

## 进阶机制

以下是该 agent 的特色功能，可选择性复现：

- [x] **skills-progressive-disclosure** — skills index → skill_view → references 按需加载，降低 token 占用
- [x] **subagent-delegation** — 最多 3 个并行子 agent、独立上下文、深度限制与 blocked toolsets
- [x] **fallback-retry-recovery** — invalid tool/json 修复 + provider fallback + credential pool 轮换
- [x] **context-compression-lineage** — 结构化摘要压缩 + session lineage + 历史可检索回溯

## 完整串联

- [x] **mini-hermes-agent** — 组合以上 MVP 组件 + 平台机制的最小完整 agent 平台

## 推荐学习路径

如果你是第一次看 Hermes，建议按这个顺序跑：

1. **先看 MVP**：`agent-session-loop` → `tool-registry-discovery` → `prompt-assembly` → `session-memory-search` → `terminal-multibackend`
2. **再看平台层**：`gateway-session-routing` → `acp-bridge` → `cron-delivery` → `approval-sandbox`
3. **最后看进阶机制**：`skills-progressive-disclosure` → `subagent-delegation` → `fallback-retry-recovery` → `context-compression-lineage`
4. **收尾跑 `mini-hermes-agent`**：把前面的模块如何拼成一个平台型 agent 看完整

这条路径基本对应 Hermes 从“单轮 agent runtime”到“长期运行个人 agent 平台”的扩展过程。

## 进度

MVP: 5/5 | 平台: 4/4 | 进阶: 4/4 | 串联: 1/1 | 总计: 14/14
