"""
NanoClaw Task Scheduler — Reusable Module

复现 NanoClaw 的三种定时调度（cron/interval/once）+ 双 context mode
+ 60s 轮询循环的核心机制。

对应原实现：src/task-scheduler.ts (249 行) + src/db.ts (getDueTasks/updateTaskAfterRun)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Optional

from croniter import croniter


# ── Schedule & Context Types ─────────────────────────────────────


class ScheduleType(str, Enum):
    CRON = "cron"          # Standard cron expression (e.g. "*/5 * * * *")
    INTERVAL = "interval"  # Milliseconds between runs (e.g. "300000")
    ONCE = "once"          # One-time ISO timestamp (e.g. "2026-02-25T10:00:00Z")


class ContextMode(str, Enum):
    GROUP = "group"        # 复用组群 session，保留对话历史
    ISOLATED = "isolated"  # 每次运行创建新 session，无历史


class TaskStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


# ── Data Model ───────────────────────────────────────────────────


@dataclass
class ScheduledTask:
    """对应原实现 types.ts 的 ScheduledTask 接口。"""
    id: str
    group_folder: str
    chat_jid: str
    prompt: str
    schedule_type: ScheduleType
    schedule_value: str
    context_mode: ContextMode
    status: TaskStatus = TaskStatus.ACTIVE
    next_run: Optional[str] = None    # ISO 8601 timestamp
    last_run: Optional[str] = None    # ISO 8601 timestamp
    last_result: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class TaskRunLog:
    """任务运行日志，对应原实现 types.ts 的 TaskRunLog。"""
    task_id: str
    run_at: str
    duration_ms: int
    status: str   # "success" | "error"
    result: Optional[str] = None
    error: Optional[str] = None


# ── Next Run Calculation ─────────────────────────────────────────


def calculate_next_run(schedule_type: ScheduleType, schedule_value: str) -> Optional[str]:
    """
    计算下一次运行时间。

    对应原实现 task-scheduler.ts 第 162-173 行：
    - cron: 使用 cron-parser 计算下一个匹配时间
    - interval: 当前时间 + 毫秒间隔
    - once: 无下一次（返回 None -> 任务标记 completed）
    """
    now = datetime.now(timezone.utc)

    if schedule_type == ScheduleType.CRON:
        # croniter: 纯 Python cron 解析器，等价于原实现的 cron-parser
        cron = croniter(schedule_value, now)
        next_dt = cron.get_next(datetime)
        return next_dt.astimezone(timezone.utc).isoformat()

    elif schedule_type == ScheduleType.INTERVAL:
        ms = int(schedule_value)
        next_dt = now + timedelta(milliseconds=ms)
        return next_dt.isoformat()

    elif schedule_type == ScheduleType.ONCE:
        # once 任务运行一次后不再调度
        return None

    return None


def calculate_initial_next_run(schedule_type: ScheduleType, schedule_value: str) -> str:
    """计算任务创建时的首次 next_run。"""
    if schedule_type == ScheduleType.ONCE:
        # once 任务的 schedule_value 就是运行时间
        return schedule_value

    next_run = calculate_next_run(schedule_type, schedule_value)
    assert next_run is not None, f"Initial next_run should not be None for {schedule_type}"
    return next_run


# ── In-Memory Task Store ─────────────────────────────────────────


class TaskStore:
    """
    内存版任务存储，等价于原实现 db.ts 中的 SQLite 操作。

    原实现用 SQL 查询 WHERE status='active' AND next_run <= ?
    来筛选到期任务。这里用 Python 列表 + 过滤实现同样语义。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._run_logs: list[TaskRunLog] = []

    def add_task(self, task: ScheduledTask) -> ScheduledTask:
        """创建任务并设置初始 next_run。对应 db.ts createTask()。"""
        if task.next_run is None:
            task.next_run = calculate_initial_next_run(
                task.schedule_type, task.schedule_value
            )
        self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """按 ID 查询任务。对应 db.ts getTaskById()。"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[ScheduledTask]:
        """获取全部任务。对应 db.ts getAllTasks()。"""
        return list(self._tasks.values())

    def get_due_tasks(self) -> list[ScheduledTask]:
        """
        筛选到期任务。对应 db.ts getDueTasks()。

        原实现 SQL:
          SELECT * FROM scheduled_tasks
          WHERE status = 'active' AND next_run IS NOT NULL AND next_run <= ?
          ORDER BY next_run
        """
        now = datetime.now(timezone.utc).isoformat()
        due = [
            t for t in self._tasks.values()
            if t.status == TaskStatus.ACTIVE
            and t.next_run is not None
            and t.next_run <= now
        ]
        return sorted(due, key=lambda t: t.next_run or "")

    def update_after_run(self, task_id: str, result_summary: str, error: Optional[str] = None) -> None:
        """
        运行后更新任务。对应 db.ts updateTaskAfterRun() + task-scheduler.ts 第 162-180 行。

        关键逻辑：
        - 计算 next_run（once 返回 None）
        - next_run 为 None 时，status 设为 completed
        - 更新 last_run 和 last_result
        """
        task = self._tasks.get(task_id)
        if not task:
            return

        now = datetime.now(timezone.utc).isoformat()
        next_run = calculate_next_run(task.schedule_type, task.schedule_value)

        task.last_run = now
        task.last_result = f"Error: {error}" if error else result_summary
        task.next_run = next_run

        # 原实现: status = CASE WHEN ? IS NULL THEN 'completed' ELSE status END
        if next_run is None:
            task.status = TaskStatus.COMPLETED

    def pause_task(self, task_id: str) -> bool:
        """暂停任务。对应 db.ts updateTask(id, {status: 'paused'})。"""
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.ACTIVE:
            task.status = TaskStatus.PAUSED
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """恢复任务。暂停后恢复需要重新计算 next_run。"""
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.PAUSED:
            task.status = TaskStatus.ACTIVE
            # 恢复时重算 next_run（避免立即触发堆积的过期任务）
            task.next_run = calculate_initial_next_run(
                task.schedule_type, task.schedule_value
            )
            return True
        return False

    def cancel_task(self, task_id: str) -> bool:
        """取消任务（标记 completed，清空 next_run）。"""
        task = self._tasks.get(task_id)
        if task and task.status != TaskStatus.COMPLETED:
            task.status = TaskStatus.COMPLETED
            task.next_run = None
            return True
        return False

    def log_run(self, log: TaskRunLog) -> None:
        """记录运行日志。对应 db.ts logTaskRun()。"""
        self._run_logs.append(log)

    def get_run_logs(self, task_id: str) -> list[TaskRunLog]:
        """获取指定任务的运行日志。"""
        return [log for log in self._run_logs if log.task_id == task_id]


# ── Scheduler Loop ───────────────────────────────────────────────


# Mock task runner: 模拟容器内 Agent 执行任务
def default_task_runner(task: ScheduledTask) -> str:
    """默认 mock 执行器，模拟任务执行并返回结果。"""
    return f"Executed prompt: '{task.prompt[:60]}' for group '{task.group_folder}'"


class SchedulerLoop:
    """
    定时调度循环。对应原实现 task-scheduler.ts 的 startSchedulerLoop()。

    原实现用 setTimeout(loop, 60000) 做 60 秒轮询：
    1. getDueTasks() 获取到期任务
    2. 对每个任务检查是否仍然 active
    3. queue.enqueueTask() 加入组群队列执行
    4. 执行后更新 next_run / last_run / last_result
    """

    POLL_INTERVAL_SEC = 60  # 原实现 SCHEDULER_POLL_INTERVAL = 60000ms

    def __init__(
        self,
        store: TaskStore,
        runner: Callable[[ScheduledTask], str] = default_task_runner,
    ) -> None:
        self.store = store
        self.runner = runner
        self._running = False

    def poll(self) -> list[tuple[str, str]]:
        """
        执行一次轮询。返回 [(task_id, result), ...]。

        对应原实现 loop() 函数（task-scheduler.ts 第 196-218 行）。
        这里同步执行以简化 demo，原实现通过 GroupQueue 异步调度。
        """
        results: list[tuple[str, str]] = []
        due_tasks = self.store.get_due_tasks()

        for task in due_tasks:
            # 原实现: re-check task status in case it was paused/cancelled
            current = self.store.get_task(task.id)
            if not current or current.status != TaskStatus.ACTIVE:
                continue

            # 执行任务（原实现通过 queue.enqueueTask -> runTask）
            error = None
            result = ""
            try:
                result = self.runner(current)
            except Exception as e:
                error = str(e)
                result = f"Error: {error}"

            # 更新任务状态（原实现: updateTaskAfterRun + logTaskRun）
            self.store.update_after_run(
                current.id,
                result[:200],  # 原实现截取前 200 字符
                error,
            )
            self.store.log_run(TaskRunLog(
                task_id=current.id,
                run_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=0,  # mock 执行无耗时
                status="error" if error else "success",
                result=result if not error else None,
                error=error,
            ))

            results.append((current.id, result))

        return results


def make_task_id() -> str:
    """生成唯一任务 ID。"""
    return f"task-{uuid.uuid4().hex[:8]}"
