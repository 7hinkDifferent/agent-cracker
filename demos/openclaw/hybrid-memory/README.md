# OpenClaw — Hybrid Memory

复现 OpenClaw 的混合检索记忆系统（Dimension 10: 记忆与持久化）。

## 机制说明

OpenClaw 的长期记忆系统使用 **Vector + BM25 混合检索**，结合时间衰减和 MMR 去重。

```
用户查询 → 并行:
  ├─ Vector 检索（embedding 余弦相似度，权重 0.7）
  └─ BM25 文本检索（关键词 TF-IDF，权重 0.3）
→ 归一化混合分数
→ 时间衰减（半衰期 30 天，Evergreen 豁免）
→ MMR 去重（Jaccard 相似度，λ=0.7）
→ Top-K 结果（默认 6 条）
```

### 关键算法

| 算法 | 公式 | 参数 |
|------|------|------|
| BM25 排名转分数 | `1/(1+rank)` | — |
| 时间衰减 | `score × e^(-λ × age_days)` | λ = ln(2)/30 |
| MMR | `λ × relevance - (1-λ) × max(sim)` | λ = 0.7 |
| 相似度 | Jaccard(token_set_a, token_set_b) | — |
| Evergreen | MEMORY.md / SOUL.md 不衰减 | — |

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/memory/hybrid.ts` | 混合检索主逻辑 |
| `src/memory/mmr.ts` | MMR 去重 |
| `src/memory/temporal-decay.ts` | 时间衰减 |
| `src/memory/bm25.ts` | BM25 索引 |

## 运行

```bash
uv run python main.py
```

## 关键简化

| 原始实现 | Demo 简化 |
|---------|----------|
| OpenAI/Gemini/Voyage embedding | 基于 hash 的伪向量 |
| SQLite 持久化索引 | 纯内存 |
| 文件 watch + debounce 同步 | 省略 |
| 查询扩展 | 省略 |
| 分块：400 tokens, 80 overlap | 整条记忆作为一个 chunk |
