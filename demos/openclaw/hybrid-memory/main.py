"""
OpenClaw — Hybrid Memory 机制复现

复现 OpenClaw 的混合检索记忆系统：
- Vector (70%) + BM25 (30%) 加权混合
- MMR 去重（Jaccard 相似度 + λ=0.7）
- 时间衰减（指数衰减，半衰期 30 天，Evergreen 豁免）
- 分块索引（400 tokens/chunk, 80 tokens overlap）

对应源码: src/memory/hybrid.ts, src/memory/mmr.ts, src/memory/temporal-decay.ts
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Optional


# ── 数据模型 ──────────────────────────────────────────────────────

@dataclass
class MemoryChunk:
    """记忆分块"""
    id: str
    file_path: str
    text: str
    embedding: list[float] = field(default_factory=list)  # 模拟向量
    created_at: float = 0.0  # Unix timestamp
    tokens: list[str] = field(default_factory=list)  # BM25 用


@dataclass
class SearchResult:
    """搜索结果"""
    chunk: MemoryChunk
    vector_score: float = 0.0
    bm25_score: float = 0.0
    hybrid_score: float = 0.0
    decayed_score: float = 0.0
    mmr_score: float = 0.0


# ── BM25 检索 ─────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """简化分词"""
    return re.findall(r'\w+', text.lower())


def bm25_rank_to_score(rank: int) -> float:
    """BM25 排名转分数：1/(1+rank)"""
    return 1.0 / (1.0 + rank)


class BM25Index:
    """简化的 BM25 索引"""

    def __init__(self):
        self.docs: list[MemoryChunk] = []
        self.df: dict[str, int] = {}  # 文档频率
        self.avg_dl: float = 0.0
        self.k1: float = 1.5
        self.b: float = 0.75

    def add(self, chunk: MemoryChunk):
        chunk.tokens = tokenize(chunk.text)
        self.docs.append(chunk)
        seen = set(chunk.tokens)
        for token in seen:
            self.df[token] = self.df.get(token, 0) + 1
        self.avg_dl = sum(len(d.tokens) for d in self.docs) / max(len(self.docs), 1)

    def search(self, query: str, top_k: int = 10) -> list[tuple[MemoryChunk, float]]:
        query_tokens = tokenize(query)
        n = len(self.docs)
        scores: list[tuple[MemoryChunk, float]] = []

        for doc in self.docs:
            score = 0.0
            dl = len(doc.tokens)
            tf_map: dict[str, int] = {}
            for t in doc.tokens:
                tf_map[t] = tf_map.get(t, 0) + 1

            for qt in query_tokens:
                if qt not in tf_map:
                    continue
                tf = tf_map[qt]
                df = self.df.get(qt, 0)
                idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / max(self.avg_dl, 1))
                score += idf * numerator / denominator

            scores.append((doc, score))

        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]


# ── Vector 检索 ───────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def mock_embed(text: str, dim: int = 8) -> list[float]:
    """模拟 embedding（基于字符 hash 生成伪向量）"""
    tokens = tokenize(text)
    vec = [0.0] * dim
    for i, t in enumerate(tokens):
        h = hash(t)
        for d in range(dim):
            vec[d] += ((h >> d) & 1) * 0.1 - 0.05
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# ── 时间衰减 ──────────────────────────────────────────────────────

EVERGREEN_FILES = {"memory.md", "soul.md"}
HALF_LIFE_DAYS = 30


def apply_temporal_decay(
    score: float,
    created_at: float,
    now: float,
    file_path: str,
    half_life_days: float = HALF_LIFE_DAYS,
) -> float:
    """
    指数时间衰减: score * e^(-λ * age_days)
    Evergreen 文件不衰减
    """
    basename = file_path.rsplit("/", 1)[-1].lower()
    if basename in EVERGREEN_FILES:
        return score  # Evergreen 豁免

    age_days = (now - created_at) / 86400
    if age_days <= 0:
        return score
    lambda_val = math.log(2) / half_life_days
    return score * math.exp(-lambda_val * age_days)


# ── MMR 去重 ──────────────────────────────────────────────────────

def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Jaccard 相似度（基于 token 集合）"""
    tokens_a = set(tokenize(text_a))
    tokens_b = set(tokenize(text_b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def mmr_rerank(
    results: list[SearchResult],
    lambda_val: float = 0.7,
    top_k: int = 6,
) -> list[SearchResult]:
    """
    MMR: λ * relevance - (1-λ) * max(similarity_to_selected)
    """
    if not results:
        return []

    selected: list[SearchResult] = []
    remaining = list(results)

    # 第一个直接选最高分
    remaining.sort(key=lambda r: -r.decayed_score)
    selected.append(remaining.pop(0))
    selected[-1].mmr_score = selected[-1].decayed_score

    while remaining and len(selected) < top_k:
        best_idx = -1
        best_mmr = float("-inf")

        for i, candidate in enumerate(remaining):
            relevance = candidate.decayed_score
            max_sim = max(
                jaccard_similarity(candidate.chunk.text, s.chunk.text)
                for s in selected
            )
            mmr = lambda_val * relevance - (1 - lambda_val) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        if best_idx >= 0:
            chosen = remaining.pop(best_idx)
            chosen.mmr_score = best_mmr
            selected.append(chosen)

    return selected


# ── 混合检索引擎 ──────────────────────────────────────────────────

class HybridMemorySearch:
    """
    OpenClaw 混合记忆检索复现

    流程:
    查询 → 查询扩展（可选）→ 并行:
      ├─ Vector 检索（embedding 相似度，权重 0.7）
      └─ BM25 文本检索（关键词��配，权重 0.3）
    → 归一化分数 → 混合加权 → 时间衰减 → MMR 去重 → Top-K
    """

    def __init__(self, vector_weight: float = 0.7, bm25_weight: float = 0.3):
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.chunks: list[MemoryChunk] = []
        self.bm25 = BM25Index()

    def add_chunk(self, chunk: MemoryChunk):
        chunk.embedding = mock_embed(chunk.text)
        self.chunks.append(chunk)
        self.bm25.add(chunk)

    def search(
        self,
        query: str,
        top_k: int = 6,
        min_score: float = 0.1,
        mmr_lambda: float = 0.7,
    ) -> list[SearchResult]:
        now = time.time()
        query_embedding = mock_embed(query)

        # ── 并行检索 ──
        # Vector 检索
        vector_scores: dict[str, float] = {}
        for chunk in self.chunks:
            sim = cosine_similarity(query_embedding, chunk.embedding)
            vector_scores[chunk.id] = max(0, sim)

        # BM25 检索
        bm25_results = self.bm25.search(query, top_k=len(self.chunks))
        bm25_scores: dict[str, float] = {}
        for rank, (chunk, _raw_score) in enumerate(bm25_results):
            bm25_scores[chunk.id] = bm25_rank_to_score(rank)

        # ── 混合分数 ──
        results: list[SearchResult] = []
        for chunk in self.chunks:
            vs = vector_scores.get(chunk.id, 0.0)
            bs = bm25_scores.get(chunk.id, 0.0)
            hybrid = self.vector_weight * vs + self.bm25_weight * bs

            if hybrid < min_score:
                continue

            decayed = apply_temporal_decay(hybrid, chunk.created_at, now, chunk.file_path)

            results.append(SearchResult(
                chunk=chunk,
                vector_score=vs,
                bm25_score=bs,
                hybrid_score=hybrid,
                decayed_score=decayed,
            ))

        # ── MMR 去重 ──
        return mmr_rerank(results, lambda_val=mmr_lambda, top_k=top_k)


# ── Demo ──────────────────────────────────────────────────────────

def main():
    search = HybridMemorySearch(vector_weight=0.7, bm25_weight=0.3)
    now = time.time()

    # 添加记忆分块
    memories = [
        ("m1", "MEMORY.md", "用户喜欢 Python 和 TypeScript 编程语言", now - 86400 * 60),     # 60 天前
        ("m2", "memory/prefs.md", "用户偏好深色主题和 Vim 键位绑定", now - 86400 * 30),       # 30 天前
        ("m3", "memory/prefs.md", "用户最近对 Rust 编程语言感兴趣", now - 86400 * 5),          # 5 天前
        ("m4", "memory/work.md", "用户在一个 TypeScript monorepo 项目中工作", now - 86400 * 2),# 2 天前
        ("m5", "memory/work.md", "项目使用 pnpm 和 vitest 做包管理和测试", now - 86400 * 2),   # 2 天前
        ("m6", "memory/misc.md", "用户养了一只叫小花的猫", now - 86400 * 90),                  # 90 天前
        ("m7", "MEMORY.md", "用户的时区是 Asia/Shanghai", now - 86400 * 120),                 # 120 天前（Evergreen）
        ("m8", "memory/code.md", "TypeScript 项目中使用 oxlint 做 linting", now - 86400 * 1),  # 1 天前
    ]

    for mid, path, text, created in memories:
        search.add_chunk(MemoryChunk(id=mid, file_path=path, text=text, created_at=created))

    print("=" * 72)
    print("OpenClaw Hybrid Memory Search Demo")
    print("=" * 72)

    queries = [
        "用户喜欢什么编程语言",
        "TypeScript 项目配置",
        "用户的宠物",
    ]

    for query in queries:
        print(f"\n── 查询: \"{query}\" ──")
        results = search.search(query, top_k=4, min_score=0.05)

        print(f"  {'ID':4s} {'文件':25s} {'Vector':8s} {'BM25':8s} {'Hybrid':8s} {'Decay':8s} {'MMR':8s}")
        print(f"  {'─'*4} {'─'*25} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        for r in results:
            is_eg = "★" if r.chunk.file_path.lower().endswith("memory.md") else " "
            print(
                f"  {r.chunk.id:4s} {r.chunk.file_path:25s} "
                f"{r.vector_score:7.3f}  {r.bm25_score:7.3f}  "
                f"{r.hybrid_score:7.3f}  {r.decayed_score:7.3f}  {r.mmr_score:7.3f} {is_eg}"
            )
            print(f"       └─ {r.chunk.text[:50]}...")

    # Evergreen 对比
    print(f"\n── 时间衰减对比 ──")
    print(f"  {'文件':25s} {'年龄':8s} {'原始':8s} {'衰减后':8s} {'衰减率':8s}")
    print(f"  {'─'*25} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
    for chunk in search.chunks:
        age_days = (now - chunk.created_at) / 86400
        raw = 0.5
        decayed = apply_temporal_decay(raw, chunk.created_at, now, chunk.file_path)
        ratio = decayed / raw if raw > 0 else 0
        is_eg = "★" if chunk.file_path.lower().endswith("memory.md") else ""
        print(
            f"  {chunk.file_path:25s} {age_days:5.0f}天   "
            f"{raw:7.3f}  {decayed:7.3f}  {ratio:6.1%} {is_eg}"
        )


if __name__ == "__main__":
    main()
