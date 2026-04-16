# Hermes Agent — context-compression-lineage

## 目标

用最简代码复现 Hermes 的上下文压缩策略：**压缩中段消息 + 生成 child session lineage**，而不是简单截断历史。

## 原理

Hermes 触发 context compression 时，不会粗暴丢弃旧消息。它会尽量保留头部关键信息和最近 tail，把中间消息压成结构化摘要；同时把压缩后的会话视作原会话的 child session，并记录 `parent_session_id`。

这样做有两个好处：当前 prompt 变短了，但历史并没有消失；后续 `session_search` 仍然可以沿 lineage 找回被压缩掉的上下文。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/context-compression-lineage/
├── README.md
├── compression.py
└── main.py
```

## 关键代码解读

```python
summary = " | ".join(chunk[:30] for chunk in middle)
child = SessionNode(session_id=f"{session_id}-child", parent_session_id=session_id, summary=summary)
return head + [f"[summary] {summary}"] + tail, child
```

Hermes 的关键不是“压缩”，而是**压缩后仍保留 lineage**。这意味着被移出当前上下文的内容仍然可回溯。

## 与原实现的差异

- 原版 compressor 会考虑 tool-call 对、近端消息保护和更丰富的摘要格式；demo 只保留 head/middle/tail 思想
- 原版 lineage 存在 SQLite 中并与 session_search 联动；demo 用内存 `LineageStore`
- 原版还有 gateway preflight compression safety net；demo 只演示主循环中的 compaction

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `run_agent.py`, `website/docs/developer-guide/context-compression-and-caching.md`
