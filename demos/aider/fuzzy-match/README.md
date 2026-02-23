# fuzzy-match — 多级容错匹配

复现 Aider 的 5 级逐步降级匹配：精确 → 空白容忍 → 省略号 → 编辑距离 80% → 跨文件。

> Based on commit: [`7afaa26`](https://github.com/Aider-AI/aider/tree/7afaa26f8b8b7b56146f0674d2a67e795b616b7c) (2026-02-22)

## 运行

```bash
uv run python main.py
```

## Demo 内容

| Demo | 说明 |
|------|------|
| Exact Match | Level 1: 精确逐字匹配 |
| Whitespace Tolerance | Level 2: 忽略首尾空白差异 |
| Ellipsis Expansion | Level 3: `...` 通配符展开 |
| Edit Distance | Level 4: Levenshtein 80% 相似度阈值 |
| Cross-File Search | Level 5: 在其他聊天文件中搜索 |
| Full Pipeline | 完整 5 级降级管线 |

## 核心机制

```
SEARCH 块匹配文件内容:

Level 1: 精确匹配
  └─ file.find(search) → 找到则完成

Level 2: 空白容忍
  └─ strip 每行首尾空白后重试

Level 3: 省略号展开
  └─ ... 行 → 通配符，分段匹配

Level 4: 编辑距离 80%
  └─ 滑动窗口 × Levenshtein ratio ≥ 0.80

Level 5: 跨文件搜索
  └─ 目标文件失败 → 搜索所有聊天文件

全部失败 → ValueError → 反思循环（最多 3 次）
```

## 核心源码

| 机制 | 原始文件 |
|------|----------|
| 多级匹配 | `aider/coders/editblock_coder.py` |
| 反思触发 | `aider/coders/base_coder.py` |
