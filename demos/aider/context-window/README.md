# context-window — 上下文窗口管理

复现 Aider 的 token 采样估算 + RepoMap 预算二分搜索 + 三层降级 + 消息组装。

> Based on commit: [`7afaa26`](https://github.com/Aider-AI/aider/tree/7afaa26f8b8b7b56146f0674d2a67e795b616b7c) (2026-02-22)

## 运行

```bash
uv run python main.py
```

## Demo 内容

| Demo | 说明 |
|------|------|
| Token Estimation | 小文件精确 vs 大文件 ~100 行采样估算 |
| RepoMap Budget | 二分搜索找最优文件子集 |
| Three-Tier | Focused(50x) → Global → Pure PageRank 降级 |
| Context Assembly | 7 层消息组装顺序 |
| Overflow Handling | ContextWindowExceededError 处理 |

## 核心机制

```
消息组装顺序:
  [system]     system prompt + example + reminder
  [user/asst]  done_messages（历史，可能已被摘要）
  [user]       repo_map（RepoMap 输出）
  [user]       readonly_files（只读文件）
  [user]       chat_files（可编辑文件）
  [user/asst]  cur_messages（当前轮）
  [system]     reminder（末尾重复）

RepoMap 三层降级:
  Tier 1: Focused — chat_file 50x + mentioned_ident 10x 加权
  Tier 2: Global  — 全文件，无个性化
  Tier 3: PageRank — 纯依赖图排序

Token 预算二分搜索:
  entries sorted by PageRank → binary search max k where sum(tokens[:k]) ≤ budget
```

## 核心源码

| 机制 | 原始文件 |
|------|----------|
| Token 估算 | `aider/coders/base_coder.py` → `token_count()` |
| RepoMap | `aider/repomap.py` |
| 上下文组装 | `aider/coders/base_coder.py` → 消息构建 |
| 超限处理 | `aider/coders/base_coder.py` → `check_tokens()` |
