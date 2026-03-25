"""
Eigent — Complexity Router Demo

复现 eigent 的任务复杂度路由机制：
- question_confirm_agent 判断：简单问题 → 直接回答，复杂任务 → Workforce
- 原实现使用 LLM 判断，Demo 使用关键词启发式 + 可选 LLM
- 展示路由决策和不同路径的处理流程

对应源码: backend/app/service/chat_service.py (question_confirm_agent)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ── 路由决策 ─────────────────────────────────────────────────────

class RouteDecision(str, Enum):
    DIRECT_ANSWER = "direct_answer"   # 简单问题，直接回答
    WORKFORCE = "workforce"           # 复杂任务，启动 Workforce


@dataclass
class RoutingResult:
    """路由判断结果"""
    decision: RouteDecision
    confidence: float           # 0.0 ~ 1.0
    reasoning: str
    response: Optional[str] = None  # direct_answer 时填充


# ── 关键词启发式规则 ─────────────────────────────────────────────

# 简单问题特征：疑问词开头 + 无动作要求
SIMPLE_KEYWORDS = [
    "what is", "what's", "who is", "who's", "when", "where",
    "how many", "how much", "define", "explain", "describe",
    "tell me about", "what does", "meaning of",
    "是什么", "什么是", "解释", "定义", "介绍", "描述",
]

# 复杂任务特征：需要执行、创建、修改
COMPLEX_KEYWORDS = [
    "create", "build", "write", "implement", "develop", "deploy",
    "fix", "debug", "refactor", "optimize", "migrate", "setup",
    "analyze and", "compare and", "design", "architect",
    "创建", "编写", "实现", "开发", "部署", "修复", "调试",
    "重构", "优化", "迁移", "搭建", "设计",
]

# 多步骤指示词
MULTI_STEP_INDICATORS = [
    "and then", "after that", "step by step", "first", "finally",
    "multiple", "several", "batch", "all", "each",
    "然后", "接着", "首先", "最后", "批量", "每个", "所有",
]


# ── 复杂度路由器 ─────────────────────────────────────────────────

class ComplexityRouter:
    """
    任务复杂度路由器 — 对应 eigent 的 question_confirm_agent。

    原实现（chat_service.py）:
    1. 用户消息先经过 question_confirm_agent
    2. LLM 判断是否为简单问题（可直接回答）
    3. 简单问题 → chat_agent 直接生成回答
    4. 复杂任务 → construct_workforce() 启动多 Agent 编排

    Demo 简化:
    - 使用关键词启发式替代 LLM 判断
    - 计算 complexity_score 作为路由依据
    """

    def __init__(self, complexity_threshold: float = 0.5):
        self.complexity_threshold = complexity_threshold

    def _compute_score(self, query: str) -> tuple[float, list[str]]:
        """计算复杂度分数（0.0 = 简单，1.0 = 复杂）"""
        lower = query.lower()
        reasons = []
        score = 0.0

        # 检查简单问题关键词
        simple_hits = sum(1 for kw in SIMPLE_KEYWORDS if kw in lower)
        if simple_hits > 0:
            score -= 0.3 * min(simple_hits, 2)
            reasons.append(f"简单问题关键词匹配 ({simple_hits})")

        # 检查复杂任务关键词
        complex_hits = sum(1 for kw in COMPLEX_KEYWORDS if kw in lower)
        if complex_hits > 0:
            score += 0.3 * min(complex_hits, 3)
            reasons.append(f"复杂任务关键词匹配 ({complex_hits})")

        # 检查多步骤指示词
        multi_hits = sum(1 for kw in MULTI_STEP_INDICATORS if kw in lower)
        if multi_hits > 0:
            score += 0.2 * min(multi_hits, 2)
            reasons.append(f"多步骤指示词 ({multi_hits})")

        # 长度启发式：超长消息更可能是复杂任务
        if len(query) > 200:
            score += 0.2
            reasons.append("长消息 (>200 字符)")
        elif len(query) < 50:
            score -= 0.1
            reasons.append("短消息 (<50 字符)")

        # 归一化到 [0, 1]
        score = max(0.0, min(1.0, score + 0.5))

        return score, reasons

    def route(self, query: str) -> RoutingResult:
        """路由决策：判断用户消息应走直接回答还是 Workforce。"""
        score, reasons = self._compute_score(query)

        if score < self.complexity_threshold:
            return RoutingResult(
                decision=RouteDecision.DIRECT_ANSWER,
                confidence=1.0 - score,
                reasoning="; ".join(reasons) or "默认判定为简单问题",
                response=self._simulate_direct_answer(query),
            )
        else:
            return RoutingResult(
                decision=RouteDecision.WORKFORCE,
                confidence=score,
                reasoning="; ".join(reasons) or "默认判定为复杂任务",
            )

    def _simulate_direct_answer(self, query: str) -> str:
        """模拟 chat_agent 的直接回答（替代 LLM 调用）"""
        return f"[Direct Answer] 针对'{query[:30]}...'的简要回答"


# ── Workforce 桩 ─────────────────────────────────────────────────

def simulate_workforce(query: str) -> list[str]:
    """模拟 Workforce 分解和执行（替代真实多 Agent 编排）"""
    # 模拟 Coordinator 分解任务
    subtasks = [
        f"子任务 1: 分析 '{query[:20]}...' 的需求",
        f"子任务 2: 实现核心功能",
        f"子任务 3: 编写测试和文档",
    ]
    return subtasks


# ── Demo ─────────────────────────────────────────────────────────

def main():
    print("=" * 68)
    print("Eigent Complexity Router Demo")
    print("=" * 68)

    router = ComplexityRouter(complexity_threshold=0.5)

    # 测试用例：覆盖简单问题和复杂任务
    test_queries = [
        # 简单问题 — 应走 direct_answer
        "What is Python?",
        "解释一下什么是微服务架构",
        "How many planets are in the solar system?",

        # 复杂任务 — 应走 workforce
        "Create a REST API with authentication and deploy it to AWS",
        "编写一个爬虫程序，然后将数据存入数据库，最后生成报告",
        "Build a React dashboard, implement real-time charts, and optimize performance",

        # 边界情况
        "Fix the bug in login page",
        "Tell me about machine learning and then create a prediction model",
    ]

    for i, query in enumerate(test_queries, 1):
        result = router.route(query)

        print(f"\n── Query {i} ──")
        print(f"  输入: {query}")
        print(f"  决策: {result.decision.value}")
        print(f"  置信度: {result.confidence:.2f}")
        print(f"  理由: {result.reasoning}")

        if result.decision == RouteDecision.DIRECT_ANSWER:
            print(f"  回答: {result.response}")
        else:
            subtasks = simulate_workforce(query)
            print(f"  Workforce 分解:")
            for st in subtasks:
                print(f"    -> {st}")

    # 阈值对比
    print(f"\n{'=' * 68}")
    print("阈值对比: 同一查询在不同阈值下的路由")
    print("=" * 68)

    query = "Explain how to fix the bug"
    for threshold in [0.4, 0.5, 0.6, 0.7]:
        r = ComplexityRouter(complexity_threshold=threshold)
        score, _ = r._compute_score(query)
        result = r.route(query)
        print(f"  threshold={threshold:.1f} -> {result.decision.value:14s} "
              f"(complexity_score={score:.2f})")


if __name__ == "__main__":
    main()
