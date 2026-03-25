"""
Eigent — Failure Retry & Replan Demo

复现 eigent 的 Workforce 失败处理机制：
- FailureHandlingConfig: retry + replan 策略
- _analyze_task: 质量评估 + 最多 3 次重试
- for_failure 模式切换：失败重试 vs 首次评估
- failure_count 跟踪和 RuntimeError 兜底

对应源码: backend/app/utils/workforce.py (Workforce._analyze_task, _handle_failed_task)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── 配置与数据模型 ────────────────────────────────────────────────

class FailureStrategy(str, Enum):
    RETRY = "retry"       # 重试同一个 Worker
    REPLAN = "replan"     # 重新分配给另一个 Worker


@dataclass
class FailureHandlingConfig:
    """失败处理配置 — 对应原实现的 FailureHandlingConfig。

    原实现: camel.workforce.workforce.FailureHandlingConfig
    enabled_strategies: 启用的策略列表（按优先级）
    """
    enabled_strategies: list[FailureStrategy] = field(
        default_factory=lambda: [FailureStrategy.RETRY, FailureStrategy.REPLAN]
    )
    max_retries: int = 3
    quality_threshold: int = 70  # 分数低于此值视为失败


class TaskState(str, Enum):
    OPEN = "open"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class TaskAnalysisResult:
    """任务分析结果 — 对应原实现的 TaskAnalysisResult。

    原实现: camel.tasks.task.TaskAnalysisResult
    None 表示分析本身失败（触发重试）
    """
    reasoning: str
    quality_score: int  # 0-100


@dataclass
class Task:
    """简化的 CAMEL Task"""
    id: str
    content: str
    state: TaskState = TaskState.OPEN
    result: str = ""
    failure_count: int = 0
    assigned_worker: str = ""


@dataclass
class WorkerAgent:
    """简化的 Worker Agent"""
    name: str
    role: str
    fail_rate: float = 0.0  # 模拟失败率

    def execute(self, task_content: str) -> str:
        """模拟执行任务（替代 LLM 调用）"""
        if random.random() < self.fail_rate:
            raise RuntimeError(f"Worker {self.name} execution failed")
        return f"[{self.name}] 完成: {task_content[:40]}"


# ── 质量评估 ─────────────────────────────────────────────────────

class TaskAnalyzer:
    """
    任务质量评估器 — 对应 Workforce._analyze_task()。

    原实现关键逻辑:
    1. 调用 coordinator_agent 评估任务结果质量
    2. 返回 TaskAnalysisResult(reasoning, quality_score)
    3. 如果返回 None → 重试评估（最多 3 次）
    4. for_failure=True 时：所有重试失败 → RuntimeError
    5. for_failure=False 时：所有重试失败 → 接受结果（默认 score=80）
    """

    def __init__(self, config: FailureHandlingConfig):
        self.config = config

    def analyze_task(
        self,
        task: Task,
        for_failure: bool = False,
        simulate_none_count: int = 0,
    ) -> TaskAnalysisResult:
        """
        评估任务质量 — 模拟 _analyze_task() 的完整重试逻辑。

        参数:
            task: 待评估的任务
            for_failure: True=失败后重新评估, False=首次评估
            simulate_none_count: 模拟前 N 次返回 None（测试重试路径）
        """
        max_retries = self.config.max_retries
        attempt = 0

        while attempt < max_retries:
            attempt += 1
            print(f"      [_analyze_task] 第 {attempt}/{max_retries} 次评估...")

            # 模拟 LLM 可能返回 None（解析失败）
            result = self._simulate_analysis(task, attempt, simulate_none_count)

            if result is not None:
                print(f"      [_analyze_task] 评估成功: score={result.quality_score}, "
                      f"reason='{result.reasoning}'")
                return result

            print(f"      [_analyze_task] 评估返回 None, 重试中...")
            time.sleep(0.1)  # 模拟短暂延迟

        # 所有重试耗尽
        if for_failure:
            # 原实现: raise RuntimeError("Failed to analyze task after retries")
            raise RuntimeError(
                f"Task '{task.id}' 分析失败: {max_retries} 次重试均返回 None"
            )
        else:
            # 原实现: 接受结果，默认 score=80
            print(f"      [_analyze_task] 重试耗尽但 for_failure=False, 接受默认分数 80")
            return TaskAnalysisResult(reasoning="默认接受（评估超时）", quality_score=80)

    def _simulate_analysis(
        self, task: Task, attempt: int, simulate_none_count: int
    ) -> Optional[TaskAnalysisResult]:
        """模拟 LLM 质量评估（替代真实 LLM 调用）"""
        if attempt <= simulate_none_count:
            return None  # 模拟 LLM 返回无法解析的结果

        # 根据任务内容和失败次数模拟评分
        base_score = 85 if "simple" in task.content.lower() else 65
        score = min(100, base_score + task.failure_count * 10)
        return TaskAnalysisResult(
            reasoning=f"第 {attempt} 次评估通过",
            quality_score=score,
        )


# ── Workforce 失败处理 ───────────────────────────────────────────

class WorkforceFailureHandler:
    """
    Workforce 失败处理器 — 对应 Workforce._handle_failed_task()。

    原实现流程:
    1. Worker 执行失败 → failure_count += 1
    2. 如果 failure_count < max_retries:
       a. 先 _analyze_task(for_failure=True) 评估是否值得重试
       b. score >= threshold → retry（同一 Worker）
       c. score < threshold → replan（换 Worker）
    3. 所有重试耗尽 → 任务标记为 FAILED
    """

    def __init__(
        self,
        config: FailureHandlingConfig,
        workers: list[WorkerAgent],
    ):
        self.config = config
        self.workers = {w.name: w for w in workers}
        self.analyzer = TaskAnalyzer(config)

    def handle_task(self, task: Task) -> None:
        """执行任务并处理失败（完整的 retry + replan 流程）"""
        worker = self.workers.get(task.assigned_worker)
        if not worker:
            worker = list(self.workers.values())[0]
            task.assigned_worker = worker.name

        while True:
            # 执行任务
            print(f"\n    [{worker.name}] 执行任务 '{task.id}': {task.content[:40]}...")
            task.state = TaskState.RUNNING

            try:
                task.result = worker.execute(task.content)
                task.state = TaskState.DONE
                print(f"    [{worker.name}] 执行成功: {task.result[:50]}")
                break
            except RuntimeError as e:
                task.failure_count += 1
                task.state = TaskState.FAILED
                print(f"    [{worker.name}] 执行失败 (failure_count={task.failure_count}/"
                      f"{self.config.max_retries}): {e}")

                if task.failure_count >= self.config.max_retries:
                    print(f"    [!] 重试耗尽, 任务 '{task.id}' 最终失败")
                    break

                # 决定策略: retry vs replan
                strategy = self._decide_strategy(task)
                print(f"    [策略] 选择: {strategy.value}")

                if strategy == FailureStrategy.REPLAN:
                    new_worker = self._find_alternative_worker(worker.name)
                    if new_worker:
                        print(f"    [replan] 从 {worker.name} 切换到 {new_worker.name}")
                        worker = new_worker
                        task.assigned_worker = new_worker.name
                    else:
                        print(f"    [replan] 无可用替代 Worker, 退回 retry")

    def _decide_strategy(self, task: Task) -> FailureStrategy:
        """决定失败处理策略 — retry 还是 replan"""
        if FailureStrategy.REPLAN in self.config.enabled_strategies:
            # 模拟: 失败 2 次以上倾向 replan
            if task.failure_count >= 2:
                return FailureStrategy.REPLAN
        return FailureStrategy.RETRY

    def _find_alternative_worker(self, current: str) -> Optional[WorkerAgent]:
        """找一个不同的 Worker"""
        for name, worker in self.workers.items():
            if name != current:
                return worker
        return None


# ── Demo ─────────────────────────────────────────────────────────

def main():
    random.seed(42)

    print("=" * 68)
    print("Eigent Failure Retry & Replan Demo")
    print("=" * 68)

    config = FailureHandlingConfig(
        enabled_strategies=[FailureStrategy.RETRY, FailureStrategy.REPLAN],
        max_retries=3,
        quality_threshold=70,
    )

    # ── 场景 1: _analyze_task 正常评估 ────────────────────────
    print("\n" + "-" * 60)
    print("场景 1: _analyze_task 正常评估 (for_failure=False)")
    print("-" * 60)

    analyzer = TaskAnalyzer(config)
    task1 = Task(id="t1", content="Simple question about Python")
    result1 = analyzer.analyze_task(task1, for_failure=False)
    print(f"  结果: score={result1.quality_score}, reasoning='{result1.reasoning}'")

    # ── 场景 2: _analyze_task 返回 None + for_failure=False ───
    print("\n" + "-" * 60)
    print("场景 2: _analyze_task 前 2 次返回 None, for_failure=False")
    print("-" * 60)

    task2 = Task(id="t2", content="Complex task analysis")
    result2 = analyzer.analyze_task(task2, for_failure=False, simulate_none_count=2)
    print(f"  结果: score={result2.quality_score}, reasoning='{result2.reasoning}'")

    # ── 场景 3: _analyze_task 全部 None + for_failure=True ────
    print("\n" + "-" * 60)
    print("场景 3: _analyze_task 全部返回 None, for_failure=True -> RuntimeError")
    print("-" * 60)

    task3 = Task(id="t3", content="Will fail analysis")
    try:
        analyzer.analyze_task(task3, for_failure=True, simulate_none_count=5)
    except RuntimeError as e:
        print(f"  捕获 RuntimeError: {e}")

    # ── 场景 4: _analyze_task 全部 None + for_failure=False ───
    print("\n" + "-" * 60)
    print("场景 4: _analyze_task 全部返回 None, for_failure=False -> 默认 score=80")
    print("-" * 60)

    task4 = Task(id="t4", content="Will accept default")
    result4 = analyzer.analyze_task(task4, for_failure=False, simulate_none_count=5)
    print(f"  结果: score={result4.quality_score}, reasoning='{result4.reasoning}'")

    # ── 场景 5: 完整 retry + replan 流程 ──────────────────────
    print("\n" + "-" * 60)
    print("场景 5: 完整 retry + replan 流程")
    print("-" * 60)

    workers = [
        WorkerAgent("developer", "开发者", fail_rate=0.7),  # 高失败率
        WorkerAgent("browser", "研究员", fail_rate=0.1),     # 低失败率
    ]

    handler = WorkforceFailureHandler(config, workers)
    task5 = Task(id="t5", content="Build a web scraper", assigned_worker="developer")
    handler.handle_task(task5)

    print(f"\n  最终状态: {task5.state.value}")
    print(f"  失败次数: {task5.failure_count}")
    print(f"  最终 Worker: {task5.assigned_worker}")
    if task5.result:
        print(f"  结果: {task5.result}")

    # ── 场景 6: 所有重试耗尽 ──────────────────────────────────
    print("\n" + "-" * 60)
    print("场景 6: 所有重试耗尽 — 任务最终失败")
    print("-" * 60)

    always_fail_workers = [
        WorkerAgent("agent_a", "Agent A", fail_rate=1.0),
        WorkerAgent("agent_b", "Agent B", fail_rate=1.0),
    ]

    handler2 = WorkforceFailureHandler(config, always_fail_workers)
    task6 = Task(id="t6", content="Impossible task", assigned_worker="agent_a")
    handler2.handle_task(task6)

    print(f"\n  最终状态: {task6.state.value}")
    print(f"  失败次数: {task6.failure_count}")


if __name__ == "__main__":
    main()
