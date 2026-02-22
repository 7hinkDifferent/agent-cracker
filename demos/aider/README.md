# Aider — Demo Overview

基于 [docs/aider.md](../../docs/aider.md) 分析，以下是值得复现的核心机制。

## Demo 清单

- [x] **repomap** — 仓库语法地图（tree-sitter AST 解析 + PageRank 排序 + token 约束）
- [x] **search-replace** — SEARCH/REPLACE 块解析器（正则状态机 + 两级模糊匹配）
- [x] **reflection** — 反思循环（编辑 → lint/test → 错误反馈 → 自动修复，最多 3 次）
- [x] **architect** — 双模型协作（架构师规划 + 编辑器实现，两阶段 LLM 调用）
- [ ] **multi-coder** — 多 Coder 多态架构（工厂模式 + 12 种编辑格式运行时切换）
- [ ] **chat-summary** — LLM 驱动的历史摘要（二分递归压缩 + 后台线程异步执行）
- [ ] **fuzzy-match** — 多级容错匹配（精确 → 空白容忍 → 省略号 → 编辑距离 80%）
- [ ] **context-window** — 上下文窗口管理（token 采样估算 + 二分搜索约束 + 三层降级）

## 进度

4/8 已完成
