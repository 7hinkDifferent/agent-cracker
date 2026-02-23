# Aider — Demo Overview

基于 [docs/aider.md](../../docs/aider.md) 分析，以下是构建最小可运行版本和复现特色机制所需的组件。

> Based on commit: [`7afaa26`](https://github.com/Aider-AI/aider/tree/7afaa26f8b8b7b56146f0674d2a67e795b616b7c) (2026-02-22)

## MVP 组件

构建最小可运行版本需要以下组件：

- [x] **core-loop** — 主循环（用户输入 → LLM 调用 → 编辑应用 → 反馈，单轮交互骨架）(Python)
- [x] **search-replace** — SEARCH/REPLACE 块解析器（正则状态机 + 两级模糊匹配）(Python)
- [x] **prompt-assembly** — Prompt 组装（system prompt + repo map + chat history + 文件上下文拼接）(Python)
- [x] **llm-response-parsing** — LLM 响应解析（从 markdown 代码块提取编辑指令，多格式适配）(Python)

## 进阶机制

以下是该 agent 的特色功能，可选择性复现：

- [x] **repomap** — 仓库语法地图（tree-sitter AST 解析 + PageRank 排序 + token 约束）
- [x] **reflection** — 反思循环（编辑 → lint/test → 错误反馈 → 自动修复，最多 3 次）
- [x] **architect** — 双模型协作（架构师规划 + 编辑器实现，两阶段 LLM 调用）
- [ ] **multi-coder** — 多 Coder 多态架构（工厂模式 + 12 种编辑格式运行时切换）
- [ ] **chat-summary** — LLM 驱动的历史摘要（二分递归压缩 + 后台线程异步执行）
- [ ] **fuzzy-match** — 多级容错匹配（精确 → 空白容忍 → 省略号 → 编辑距离 80%）
- [ ] **context-window** — 上下文窗口管理（token 采样估算 + 二分搜索约束 + 三层降级）

## 完整串联

- [ ] **mini-aider** — 组合以上 MVP 组件的最小完整 agent

## 进度

MVP: 4/4 | 进阶: 3/7 | 总计: 7/12
