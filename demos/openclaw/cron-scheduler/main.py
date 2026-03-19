"""
OpenClaw — Cron Scheduler 机制复现

复现 OpenClaw 的定时调度系统：
- 3 种调度类型（at / every / cron 表达式）
- Heartbeat 空闲检测
- 错误指数退避（30s → 1min → 5min → 15min → 60min）
- Missed job 检测与补执行

对应源码: src/cron/schedule.ts, src/cron/service/timer.ts
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


# ── 数据模型 ──────────────────────────────────────────────────────

class ScheduleKind(str, Enum):
    AT = "at"        # 绝对时间点（一次性）
    EVERY = "every"  # 相对间隔（循环）
    CRON = "cron"    # Cron 表达式（循环）


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Schedule:
    """调度配置"""
    kind: ScheduleKind
    at_time: Optional[float] = None      # AT: Unix timestamp
    every_seconds: Optional[float] = None # EVERY: 间隔秒数
    cron_expr: Optional[str] = None       # CRON: cron 表达式
    anchor_time: float = 0.0             # EVERY 的锚定时间

    def __post_init__(self):
        if self.anchor_time == 0.0:
            self.anchor_time = time.time()


@dataclass
class CronJob:
    """调度任务"""
    job_id: str
    name: str
    schedule: Schedule
    agent_id: str
    task: str                             # Agent 要执行的任务描述
    status: JobStatus = JobStatus.PENDING
    last_run: float = 0.0
    next_run: float = 0.0
    run_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0

    def __post_init__(self):
        if self.next_run == 0.0:
            self.next_run = self._compute_next_run(time.time())

    def _compute_next_run(self, now: float) -> float:
        if self.schedule.kind == ScheduleKind.AT:
            return self.schedule.at_time or now

        if self.schedule.kind == ScheduleKind.EVERY:
            interval = self.schedule.every_seconds or 60
            if self.last_run > 0:
                return self.last_run + interval
            return self.schedule.anchor_time + interval

        # 简化 cron：按分钟间隔模拟
        return now + 60

    def compute_backoff_delay(self) -> float:
        """错误指数退避"""
        backoff_schedule = [30, 60, 300, 900, 3600]  # 30s, 1min, 5min, 15min, 60min
        idx = min(self.consecutive_failures, len(backoff_schedule) - 1)
        return backoff_schedule[idx]


# ── Heartbeat ────────────────────────────────────────────────────

@dataclass
class HeartbeatState:
    """Heartbeat 状态"""
    last_heartbeat: float = 0.0
    agent_idle: bool = True
    interval_seconds: float = 60.0


# ── 调度引擎 ──────────────────────────────────────────────────────

class CronScheduler:
    """
    OpenClaw Cron Scheduler 复现

    核心功能：
    1. 3 种调度类型（at/every/cron）
    2. Heartbeat 空闲检测
    3. 错误指数退避
    4. Missed job 补执行
    """

    MAX_CONCURRENT_RUNS = 3
    MAX_TIMER_DELAY = 60.0  # 最大 timer 间隔

    def __init__(self):
        self.jobs: dict[str, CronJob] = {}
        self.heartbeat = HeartbeatState()
        self._job_counter = 0
        self._running_count = 0
        self.execution_log: list[str] = []

    # ── 任务管理 ──

    def add_job(
        self,
        name: str,
        schedule: Schedule,
        agent_id: str,
        task: str,
    ) -> CronJob:
        self._job_counter += 1
        job_id = f"cron-{self._job_counter:03d}"
        job = CronJob(
            job_id=job_id, name=name, schedule=schedule,
            agent_id=agent_id, task=task,
        )
        self.jobs[job_id] = job
        return job

    def remove_job(self, job_id: str) -> bool:
        return self.jobs.pop(job_id, None) is not None

    # ── 调度逻辑 ──

    def get_due_jobs(self, now: float) -> list[CronJob]:
        """获取到期的任务"""
        due = []
        for job in self.jobs.values():
            if job.status == JobStatus.RUNNING:
                continue
            if job.schedule.kind == ScheduleKind.AT and job.run_count > 0:
                continue  # 一次性任务已执行
            if job.next_run <= now:
                due.append(job)
        return due

    def find_missed_jobs(self, now: float, downtime_since: float) -> list[CronJob]:
        """检测宕机期间遗漏的任务"""
        missed = []
        for job in self.jobs.values():
            if job.schedule.kind == ScheduleKind.AT:
                if job.run_count == 0 and (job.schedule.at_time or 0) < now:
                    missed.append(job)
            elif job.last_run < downtime_since and job.next_run < now:
                missed.append(job)
        return missed

    def execute_job(self, job: CronJob, now: float, success: bool = True) -> str:
        """执行任务（模拟）"""
        if self._running_count >= self.MAX_CONCURRENT_RUNS:
            return f"[{job.job_id}] 跳过：并发上限 ({self.MAX_CONCURRENT_RUNS})"

        job.status = JobStatus.RUNNING
        self._running_count += 1
        job.run_count += 1
        job.last_run = now

        if success:
            job.status = JobStatus.COMPLETED
            job.consecutive_failures = 0
            job.next_run = job._compute_next_run(now)
            msg = f"[{job.job_id}] ✓ {job.name}: 执行成功 (第{job.run_count}次)"
        else:
            job.status = JobStatus.FAILED
            job.failure_count += 1
            job.consecutive_failures += 1
            backoff = job.compute_backoff_delay()
            job.next_run = now + backoff
            msg = f"[{job.job_id}] ✗ {job.name}: 执行失败 → 退避 {backoff:.0f}s"

        self._running_count -= 1
        self.execution_log.append(msg)
        return msg

    # ── Heartbeat ──

    def process_heartbeat(self, now: float) -> str:
        """处理心跳"""
        self.heartbeat.last_heartbeat = now
        due = self.get_due_jobs(now)
        if due:
            self.heartbeat.agent_idle = False
            return f"HEARTBEAT: {len(due)} 个任务待执行"
        self.heartbeat.agent_idle = True
        return "HEARTBEAT_OK"


# ── 调度解析 ──────────────────────────────────────────────────────

def parse_schedule(expr: str) -> Schedule:
    """
    解析调度表达式

    支持格式：
    - "at:1234567890"     → 绝对时间（Unix timestamp）
    - "every:30m"         → 每 30 分钟
    - "every:2h"          → 每 2 小时
    - "cron:*/5 * * * *"  → cron 表达式
    """
    if expr.startswith("at:"):
        timestamp = float(expr[3:])
        return Schedule(kind=ScheduleKind.AT, at_time=timestamp)

    if expr.startswith("every:"):
        interval_str = expr[6:]
        m = re.match(r"(\d+)(s|m|h|d)", interval_str)
        if not m:
            raise ValueError(f"Invalid interval: {interval_str}")
        value = int(m.group(1))
        unit = m.group(2)
        multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return Schedule(kind=ScheduleKind.EVERY, every_seconds=value * multiplier[unit])

    if expr.startswith("cron:"):
        return Schedule(kind=ScheduleKind.CRON, cron_expr=expr[5:])

    raise ValueError(f"Unknown schedule format: {expr}")


# ── Demo ──────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("OpenClaw Cron Scheduler Demo")
    print("=" * 64)

    scheduler = CronScheduler()
    now = time.time()

    # ── 1. 调度解析 ──
    print("\n── 1. 调度表达式解析 ──")
    exprs = [
        f"at:{now + 300}",
        "every:30m",
        "every:2h",
        "cron:*/5 * * * *",
    ]
    for expr in exprs:
        s = parse_schedule(expr)
        detail = ""
        if s.kind == ScheduleKind.AT:
            detail = f"触发时间: +{(s.at_time or 0) - now:.0f}s"
        elif s.kind == ScheduleKind.EVERY:
            detail = f"间隔: {s.every_seconds:.0f}s"
        elif s.kind == ScheduleKind.CRON:
            detail = f"表达式: {s.cron_expr}"
        print(f"  {expr:30s} → {s.kind.value:5s} | {detail}")

    # ── 2. 任务调度 ──
    print("\n── 2. 任务调度与执行 ──")

    # 一次性任务（已到期）
    j1 = scheduler.add_job("定时备份", Schedule(ScheduleKind.AT, at_time=now - 10), "backup-agent", "执行数据库备份")
    # 循环任务（已到期）
    j2 = scheduler.add_job("健康检查", Schedule(ScheduleKind.EVERY, every_seconds=300, anchor_time=now - 400), "monitor-agent", "检查服务健康状态")
    # 未到期任务
    j3 = scheduler.add_job("日报生成", Schedule(ScheduleKind.EVERY, every_seconds=86400, anchor_time=now), "report-agent", "生成工作日报")

    due = scheduler.get_due_jobs(now)
    print(f"  注册任务: {len(scheduler.jobs)}, 到期任务: {len(due)}")
    for job in due:
        print(f"    → {job.name} ({job.schedule.kind.value})")

    # 执行到期任务
    for job in due:
        msg = scheduler.execute_job(job, now)
        print(f"  {msg}")

    # ── 3. 错误退避 ──
    print("\n── 3. 错误指数退避 ──")

    error_job = scheduler.add_job("不稳定任务", Schedule(ScheduleKind.EVERY, every_seconds=60), "flaky-agent", "执行不稳定操作")
    for i in range(5):
        msg = scheduler.execute_job(error_job, now + i * 10, success=False)
        delay = error_job.compute_backoff_delay()
        print(f"  失败 #{i+1}: 退避={delay:6.0f}s  next_run=+{error_job.next_run - now:.0f}s")

    # ── 4. Heartbeat ──
    print("\n── 4. Heartbeat 心跳 ──")

    # 空闲状态
    status = scheduler.process_heartbeat(now + 10000)
    print(f"  {status} (idle={scheduler.heartbeat.agent_idle})")

    # 有待处理任务
    scheduler.add_job("紧急任务", Schedule(ScheduleKind.AT, at_time=now), "urgent-agent", "处理紧急事件")
    status = scheduler.process_heartbeat(now)
    print(f"  {status} (idle={scheduler.heartbeat.agent_idle})")

    # ── 5. Missed job 检测 ──
    print("\n── 5. Missed Job 检测 ──")
    missed_job = scheduler.add_job(
        "遗漏任务", Schedule(ScheduleKind.AT, at_time=now - 3600), "missed-agent", "应该在1小时前执行"
    )
    missed = scheduler.find_missed_jobs(now, downtime_since=now - 7200)
    print(f"  宕机 2 小时后检测到 {len(missed)} 个遗漏任务:")
    for m in missed:
        print(f"    → {m.name} (应执行于 {(now - (m.schedule.at_time or now)):.0f}s 前)")


if __name__ == "__main__":
    main()
