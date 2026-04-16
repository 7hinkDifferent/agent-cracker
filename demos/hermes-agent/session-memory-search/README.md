# Hermes Agent — session-memory-search

## 目标

用最简代码复现 Hermes 的**双层长期记忆**：`MEMORY.md` / `USER.md` 冻结注入 + SQLite FTS5 `session_search` 回忆历史细节。

## MVP 角色

这是 Hermes MVP 中的**长期记忆层**。它让 agent 不必只依赖当前窗口，而能在长期运行中保留稳定事实与历史对话细节。

## 原理

Hermes 的长期记忆并不是单一向量库。它把稳定、长期有效的事实写入 `MEMORY.md` / `USER.md`，在每次构建 system prompt 时直接注入；而对于低频但仍重要的细节，则通过 SQLite `messages` + `messages_fts` 做全文搜索，再把匹配 session 做摘要后塞回当前轮。

这个组合特别适合“个人 agent 平台”：高频偏好走零延迟 prompt 注入，低频历史通过检索召回，避免 memory 文件无限膨胀。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/session-memory-search/
├── README.md
├── main.py
└── memory_store.py
```

## 关键代码解读

```python
self.conn.execute(
    "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, content='messages', content_rowid='id')"
)
```

Hermes 的 `session_search` 先用 FTS5 召回候选消息，再按 session 分组、加载完整会话并总结。demo 里把“LLM 总结”简化成了规则化摘要，但保留了 **结构化 memory + FTS5 recall** 的核心组合。

## 运行后建议观察

1. **先看 Memory snapshot**：这是每轮 prompt 都会稳定注入的长期事实
2. **再看 session_search 结果**：这是按 query 临时召回的低频历史
3. **理解双层分工**：稳定事实放 `MEMORY.md` / `USER.md`，细节历史留给 FTS5 检索

## 与原实现的差异

- 原版会对每个候选 session 调辅助模型做更高质量的 focused summary；demo 用规则摘要替代
- 原版 schema 还包含 `tool_calls`、`reasoning`、`started_at` 等元数据；demo 只保留最关键的 session/message/FTS 表
- 原版还会沿着 parent/child session lineage 回溯；demo 只展示 parent 字段，不实现完整 lineage 展开

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `hermes_state.py`, `tools/memory_tool.py`, `tools/session_search_tool.py`
