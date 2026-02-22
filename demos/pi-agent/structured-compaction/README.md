# Demo: Pi-Agent — Structured Compaction 结构化上下文压缩

## 目标

用最简代码复现 pi-agent 的上下文压缩策略：chars/4 token 估算 → 阈值触发 → 切割点查找 → LLM 结构化摘要 → 增量 UPDATE。

## 原理

当对话上下文接近模型窗口限制时，pi-agent 不是简单截断或丢弃旧消息，而是用 LLM 生成**结构化摘要**替换旧消息：

**3 步流程**：
1. **找切割点**：从最新消息向前累积 token，超过 `keepRecentTokens` 时在 user/assistant 消息边界切
2. **LLM 摘要**：将被切掉的旧消息发给 LLM，按固定结构生成摘要
3. **增量 UPDATE**：后续压缩不从头写，而是更新已有摘要

**结构化摘要格式**：
```markdown
## Goal          — 用户要完成什么
## Progress      — Done / In Progress
## Key Decisions — 做了什么决策，为什么
## Next Steps    — 下一步行动
## Critical Context — 必须保留的关键数据
```

**独特设计**：
- `chars/4` token 估算：不依赖任何特定 tokenizer，简单但实用
- 增量 UPDATE：第二次压缩时将上次摘要作为上下文，让 LLM 合并更新

## 运行

```bash
cd demos/pi-agent/structured-compaction

# 有 API key（真实 LLM 摘要）
uv run --with litellm python main.py

# 无 API key（mock 摘要演示流程）
python main.py
```

## 文件结构

```
demos/pi-agent/structured-compaction/
├── README.md          # 本文件
├── main.py            # 演示：初始压缩 → 增量 UPDATE
└── compaction.py      # 压缩算法核心（估算/切割/摘要）
```

## 关键代码解读

### chars/4 Token 估算

```python
def estimate_tokens(message: dict) -> int:
    chars = len(message["content"])
    return max(1, chars // 4)  # 保守高估
```

### 切割点查找

```python
def find_cut_point(messages, keep_recent_tokens):
    accumulated = 0
    for i in range(len(messages) - 1, -1, -1):
        accumulated += estimate_tokens(messages[i])
        if accumulated >= keep_recent_tokens:
            # 找最近的 user/assistant 边界
            return nearest_valid_cut_point(i)
    return 0
```

### 增量 UPDATE

```python
# 首次：生成初始摘要
summary = generate_summary(old_messages, previous_summary=None)

# 后续：UPDATE 已有摘要
summary = generate_summary(old_messages, previous_summary=prev_summary)
# → LLM 看到 <previous-summary> 和 <recent-conversation>，合并更新
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 消息格式 | SessionEntry（带 ID、类型标记） | 简单 dict |
| Split Turn | 支持切割点在 turn 中间 | 不支持 |
| 文件跟踪 | 提取 read/write/edit 文件列表 | 无 |
| 图片处理 | 图片计为 1200 tokens | 无 |
| 持久化 | JSONL 追加写入 | 无 |
| 触发方式 | 阈值触发 + 溢出触发 | 仅阈值触发 |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 核心源码: `packages/coding-agent/src/core/compaction/compaction.ts`
