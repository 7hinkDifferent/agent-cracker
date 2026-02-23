# chat-summary — LLM 驱动的历史摘要

复现 Aider 的二分递归压缩 + 后台异步摘要机制。

> Based on commit: [`7afaa26`](https://github.com/Aider-AI/aider/tree/7afaa26f8b8b7b56146f0674d2a67e795b616b7c) (2026-02-22)

## 运行

```bash
uv run python main.py
```

## Demo 内容

| Demo | 说明 |
|------|------|
| Binary Compression | 二分递归：split → summarize head → recurse |
| Summary Content | 摘要内容策略（第一人称、保留标识符） |
| Incremental Growth | 消息增长与摘要触发时机 |
| Recursion Depth | 不同数据量的递归深度对比 |
| Async Background | 后台异步摘要（不阻塞用户交互） |

## 核心算法

```python
def summarize_real(messages, depth=0):
    if total_tokens <= max_tokens:
        return messages            # 不需要摘要

    half_budget = max_tokens // 2
    split = find_split_point(messages, half_budget)

    head = messages[:split]        # 旧消息 → LLM 摘要
    tail = messages[split:]        # 新消息 → 原样保留

    summary = llm_summarize(head)
    return summarize_real([summary] + tail, depth + 1)  # 递归
```

## 核心源码

| 机制 | 原始文件 |
|------|----------|
| ChatSummary 类 | `aider/history.py` |
| 摘要集成点 | `aider/coders/base_coder.py` |
| 摘要 prompt | `aider/prompts.py` |
