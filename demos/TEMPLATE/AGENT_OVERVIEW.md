# {{AGENT_NAME}} — Demo Overview

基于 [docs/{{AGENT_NAME}}.md](../../docs/{{AGENT_NAME}}.md) 分析，以下是构建最小可运行版本和复现特色机制所需的组件。

> Based on commit: [`{{COMMIT_SHORT}}`]({{REPO_URL}}/tree/{{COMMIT_SHA}}) ({{COMMIT_DATE}})

## MVP 组件

构建最小可运行版本需要以下组件：

- [ ] **{{component-1}}** — 一句话描述 (Python)
- [ ] **{{component-2}}** — 一句话描述 ({{Language}} — 依赖语言特性: {{reason}})

<!-- 以下为平台机制段，仅平台型 agent（type: agent-platform）保留，纯 coding agent 删除此段 -->
## 平台机制

以下是超越 coding agent 的平台层机制（D9-D12），可复现为独立 demo：

- [ ] **{{platform-mechanism-1}}** — 一句话描述 (D9: 通道层)
- [ ] **{{platform-mechanism-2}}** — 一句话描述 (D10: 记忆)
<!-- /平台机制段结束 -->

## 进阶机制

以下是该 agent 的特色功能，可选择性复现：

- [ ] **{{mechanism-1}}** — 一句话描述

## 完整串联

- [ ] **mini-{{AGENT_NAME}}** — 组合以上 MVP 组件（+ 平台机制）的最小完整 agent

## 进度

<!-- 纯 coding agent 格式 -->
MVP: 0/N | 进阶: 0/M | 串联: 0/1 | 总计: 0/K
<!-- 平台型 agent 格式（删除上一行，取消注释下一行） -->
<!-- MVP: 0/N | 平台: 0/P | 进阶: 0/M | 串联: 0/1 | 总计: 0/K -->
