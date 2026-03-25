"""
Eigent — Workforce 编排 Demo

复现 eigent 的 CAMEL Workforce 多 Agent 并行编排机制：
任务分解 → 角色分配 → 并行执行 → 质量评估 → 结果汇总。

原实现: backend/app/utils/workforce.py (Workforce)
       backend/app/service/chat_service.py (construct_workforce, run_decomposition)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import litellm


# ─── 任务状态 ─────────────────────────────────────────────────

class TaskState(str, Enum):
    OPEN = "open"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Task:
    """简化的 CAMEL Task。

    原实现: camel.tasks.task.Task
    包含 id、content、result、state、parent、subtasks 等。
    """
    id: str
    content: str
    state: TaskState = TaskState.OPEN
    result: str = ""
    failure_count: int = 0
    subtasks: list["Task"] = field(default_factory=list)
    assigned_worker: str = ""


# ─── Worker Agent ──────────────────────────────────────────────

@dataclass
class WorkerAgent:
    """简化的 Worker — 对应 eigent 的 8 类 Agent。

    原实现中每个 Worker 是一个 ListenChatAgent，
    通过 CAMEL SingleAgentWorker 包装。
    """
    name: str
    role: str
    system_prompt: str

    async def step(self, task_content: str) -> str:
        """执行一个子任务 — 调用 LLM。

        原实现: ListenChatAgent.step() / astep()
        """
        model = os.environ.get("DEMO_MODEL", "gpt-4o-mini")
        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": task_content},
            ],
            max_tokens=200,
        )
        return response.choices[0].message.content


# ─── Workforce 编排器 ─────────────────────────────────────────

class Workforce:
    """简化的 Workforce — eigent 多 Agent 编排的核心。

    原实现: backend/app/utils/workforce.py
    继承 CAMEL BaseWorkforce，重写:
    - eigent_make_sub_tasks(): 任务分解
    - eigent_start(): 并行执行
    - _find_assignee(): 角色分配
    - _handle_completed_task(): 完成处理
    - _handle_failed_task(): 失败重试

    关键设计:
    1. Coordinator Agent 负责任务分解
    2. Task Agent 负责子任务分配
    3. Worker Agent 并行执行子任务
    4. 失败时 retry + replan
    """

    def __init__(self, workers: list[WorkerAgent], max_retries: int = 2) -> None:
        self.workers = {w.name: w for w in workers}
        self.max_retries = max_retries
        self._coordinator_model = os.environ.get("DEMO_MODEL", "gpt-4o-mini")

    async def decompose_task(self, task: Task) -> list[Task]:
        """任务分解 — 模拟 eigent_make_sub_tasks()。

        原实现使用 CAMEL 的 TASK_DECOMPOSE_PROMPT + task_agent 来分解。
        Coordinator 根据 worker 列表决定如何拆分。
        """
        worker_info = "\n".join(
            f"- {w.name} ({w.role})" for w in self.workers.values()
        )

        response = await litellm.acompletion(
            model=self._coordinator_model,
            messages=[
                {"role": "system", "content": (
                    "You are a task coordinator. Break the task into subtasks "
                    "and assign each to the most suitable worker.\n\n"
                    f"Available workers:\n{worker_info}\n\n"
                    "Return a JSON array of objects with 'subtask' and 'worker' fields.\n"
                    'Example: [{"subtask": "Research X", "worker": "browser_agent"}]'
                )},
                {"role": "user", "content": task.content},
            ],
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()

        # 解析子任务分配
        try:
            # 提取 JSON（可能包含 markdown 代码块）
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            assignments = json.loads(raw.strip())
        except (json.JSONDecodeError, IndexError):
            # 回退：整个任务分配给第一个 worker
            first_worker = list(self.workers.keys())[0]
            assignments = [{"subtask": task.content, "worker": first_worker}]

        subtasks = []
        for i, a in enumerate(assignments):
            st = Task(
                id=f"{task.id}.{i+1}",
                content=a.get("subtask", task.content),
                assigned_worker=a.get("worker", list(self.workers.keys())[0]),
            )
            subtasks.append(st)
            task.subtasks.append(st)

        return subtasks

    async def _execute_subtask(self, subtask: Task) -> None:
        """执行单个子任务 — 分配给对应 Worker。

        原实现通过 TaskChannel publish/subscribe 实现并行。
        """
        worker_name = subtask.assigned_worker
        worker = self.workers.get(worker_name)

        if not worker:
            # 回退到第一个可用 worker
            worker = list(self.workers.values())[0]
            worker_name = worker.name

        print(f"    🟢 [{worker_name}] 开始: {subtask.content[:50]}...")
        subtask.state = TaskState.RUNNING

        try:
            result = await worker.step(subtask.content)
            subtask.result = result
            subtask.state = TaskState.DONE
            print(f"    ✅ [{worker_name}] 完成: {result[:60]}...")
        except Exception as e:
            subtask.failure_count += 1
            subtask.state = TaskState.FAILED
            subtask.result = f"Error: {e}"
            print(f"    ❌ [{worker_name}] 失败 (retry {subtask.failure_count}/{self.max_retries})")

    async def execute(self, task: Task) -> str:
        """完整编排流程 — 分解 → 分配 → 并行执行 → 汇总。

        原实现: eigent_start() 调用 BaseWorkforce.start()
        """
        print(f"\n  📋 任务分解...")
        subtasks = await self.decompose_task(task)

        print(f"  📊 分解为 {len(subtasks)} 个子任务:")
        for st in subtasks:
            print(f"     [{st.assigned_worker}] {st.content[:60]}")

        # 并行执行所有子任务（原实现通过 CAMEL TaskChannel）
        print(f"\n  🚀 并行执行 {len(subtasks)} 个子任务...")
        await asyncio.gather(*[self._execute_subtask(st) for st in subtasks])

        # 失败重试（原实现: _handle_failed_task with retry + replan）
        for st in subtasks:
            while st.state == TaskState.FAILED and st.failure_count < self.max_retries:
                print(f"    🔄 重试: {st.content[:40]}...")
                await self._execute_subtask(st)

        # 汇总结果
        results = []
        for st in subtasks:
            status = "✅" if st.state == TaskState.DONE else "❌"
            results.append(f"{status} [{st.assigned_worker}] {st.content}: {st.result}")

        task.result = "\n".join(results)
        task.state = TaskState.DONE if all(
            st.state == TaskState.DONE for st in subtasks
        ) else TaskState.FAILED

        return task.result


# ─── 质量评估（简化版 _analyze_task）─────────────────────────

async def analyze_task_quality(task: Task) -> tuple[int, str]:
    """质量评估 — 模拟 Workforce._analyze_task()。

    原实现: 调用 coordinator_agent 评估子任务结果质量，
    返回 TaskAnalysisResult(reasoning, quality_score)。
    score < 阈值时触发 retry 或 replan。
    """
    model = os.environ.get("DEMO_MODEL", "gpt-4o-mini")
    response = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": (
                "Evaluate the quality of this task result. "
                "Return a JSON with 'score' (0-100) and 'reasoning' (1 sentence)."
            )},
            {"role": "user", "content": f"Task: {task.content}\nResult: {task.result[:500]}"},
        ],
        max_tokens=100,
    )
    raw = response.choices[0].message.content.strip()
    try:
        evaluation = json.loads(raw)
        return evaluation.get("score", 80), evaluation.get("reasoning", "OK")
    except json.JSONDecodeError:
        return 80, "Unable to parse evaluation, accepting result"


# ─── Demo 入口 ───────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("Eigent Workforce 编排 Demo")
    print("=" * 60)

    # 创建 Worker Agent 团队（简化的 8 类 Agent → 3 类）
    workers = [
        WorkerAgent(
            name="developer_agent",
            role="Lead Software Engineer",
            system_prompt="You are a Lead Software Engineer. Write concise code solutions.",
        ),
        WorkerAgent(
            name="browser_agent",
            role="Senior Research Analyst",
            system_prompt="You are a Senior Research Analyst. Provide concise research findings.",
        ),
        WorkerAgent(
            name="document_agent",
            role="Documentation Specialist",
            system_prompt="You are a Documentation Specialist. Write concise documentation.",
        ),
    ]

    workforce = Workforce(workers, max_retries=2)

    # 创建主任务
    task = Task(
        id="task-001",
        content="Create a Python script that fetches weather data from an API and generates a summary report",
    )

    print(f"\n📝 主任务: {task.content}")

    # 执行完整编排流程
    result = await workforce.execute(task)

    print(f"\n{'=' * 60}")
    print("📊 最终结果")
    print("=" * 60)
    print(result)
    print(f"\n  任务状态: {task.state.value}")
    print(f"  子任务数: {len(task.subtasks)}")

    # 质量评估
    print(f"\n{'─' * 40}")
    print("🔍 质量评估 (_analyze_task)")
    print("─" * 40)
    score, reasoning = await analyze_task_quality(task)
    print(f"  分数: {score}/100")
    print(f"  评价: {reasoning}")

    print("\n✅ Demo 完成")


if __name__ == "__main__":
    asyncio.run(main())
