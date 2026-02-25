"""
NanoClaw Task Scheduler Demo

演示 NanoClaw 的定时任务调度机制：
1. 三种调度类型（cron/interval/once）
2. 到期任务扫描（getDueTasks 轮询）
3. next_run 计算逻辑
4. context_mode（group vs isolated）
5. 任务生命周期（pause/resume/cancel）

Run: uv run --with croniter python main.py
"""

from datetime import datetime, timedelta, timezone

from scheduler import (
    ContextMode,
    ScheduleType,
    ScheduledTask,
    SchedulerLoop,
    TaskStatus,
    TaskStore,
    calculate_next_run,
    make_task_id,
)


def fmt_time(iso: str | None) -> str:
    """Format ISO timestamp for display."""
    if iso is None:
        return "None"
    return iso[:19].replace("T", " ") + "Z"


def fmt_status(task: ScheduledTask) -> str:
    """Format task status line."""
    return (
        f"    id={task.id}  type={task.schedule_type.value}  "
        f"status={task.status.value}  next_run={fmt_time(task.next_run)}"
    )


# ── Demo 1: 三种调度类型 ─────────────────────────────────────────


def demo_schedule_types():
    """创建 cron/interval/once 三种任务，展示各自的 schedule_value 语义。"""
    print("=" * 64)
    print("Demo 1: Three Schedule Types (cron / interval / once)")
    print("=" * 64)
    print()

    store = TaskStore()

    # Cron: 每 5 分钟执行一次
    cron_task = store.add_task(ScheduledTask(
        id="task-cron-01",
        group_folder="dev-team",
        chat_jid="group-dev@g.us",
        prompt="Check CI pipeline status and report failures",
        schedule_type=ScheduleType.CRON,
        schedule_value="*/5 * * * *",  # 每 5 分钟
        context_mode=ContextMode.ISOLATED,
    ))
    print(f"  [cron] expression: '*/5 * * * *' (every 5 min)")
    print(f"         next_run:   {fmt_time(cron_task.next_run)}")
    print()

    # Interval: 每 30 秒执行一次 (30000ms)
    interval_task = store.add_task(ScheduledTask(
        id="task-interval-01",
        group_folder="monitoring",
        chat_jid="group-mon@g.us",
        prompt="Ping health endpoint and alert if down",
        schedule_type=ScheduleType.INTERVAL,
        schedule_value="30000",  # 30 秒 = 30000ms
        context_mode=ContextMode.ISOLATED,
    ))
    print(f"  [interval] value: '30000' (30s in milliseconds)")
    print(f"             next_run: {fmt_time(interval_task.next_run)}")
    print()

    # Once: 固定时间执行一次
    once_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    once_task = store.add_task(ScheduledTask(
        id="task-once-01",
        group_folder="ops-team",
        chat_jid="group-ops@g.us",
        prompt="Generate end-of-day summary report",
        schedule_type=ScheduleType.ONCE,
        schedule_value=once_time,
        context_mode=ContextMode.GROUP,
    ))
    print(f"  [once] value: '{fmt_time(once_time)}' (one-time timestamp)")
    print(f"         next_run: {fmt_time(once_task.next_run)}")
    print()

    print(f"  Total tasks in store: {len(store.get_all_tasks())}")
    return store


# ── Demo 2: getDueTasks 扫描 ─────────────────────────────────────


def demo_due_tasks():
    """模拟到期任务扫描：设置过去的 next_run，验证 getDueTasks 筛选。"""
    print()
    print("=" * 64)
    print("Demo 2: getDueTasks — Scanning for Due Tasks")
    print("=" * 64)
    print()

    store = TaskStore()
    now = datetime.now(timezone.utc)

    # 已过期的任务（next_run 在过去）——应被检出
    past_time = (now - timedelta(minutes=5)).isoformat()
    store.add_task(ScheduledTask(
        id="task-due-1",
        group_folder="team-a",
        chat_jid="a@g.us",
        prompt="Overdue task A",
        schedule_type=ScheduleType.INTERVAL,
        schedule_value="60000",
        context_mode=ContextMode.ISOLATED,
        next_run=past_time,
    ))

    store.add_task(ScheduledTask(
        id="task-due-2",
        group_folder="team-b",
        chat_jid="b@g.us",
        prompt="Overdue task B",
        schedule_type=ScheduleType.ONCE,
        schedule_value=past_time,
        context_mode=ContextMode.GROUP,
        next_run=past_time,
    ))

    # 未到期的任务（next_run 在未来）——不应被检出
    future_time = (now + timedelta(hours=1)).isoformat()
    store.add_task(ScheduledTask(
        id="task-future-1",
        group_folder="team-c",
        chat_jid="c@g.us",
        prompt="Future task C",
        schedule_type=ScheduleType.CRON,
        schedule_value="0 * * * *",
        context_mode=ContextMode.ISOLATED,
        next_run=future_time,
    ))

    # 已暂停的过期任务——不应被检出
    store.add_task(ScheduledTask(
        id="task-paused-1",
        group_folder="team-d",
        chat_jid="d@g.us",
        prompt="Paused task D",
        schedule_type=ScheduleType.INTERVAL,
        schedule_value="60000",
        context_mode=ContextMode.ISOLATED,
        next_run=past_time,
        status=TaskStatus.PAUSED,
    ))

    print(f"  Total tasks:  {len(store.get_all_tasks())}")
    print(f"    - 2 overdue (next_run in the past, active)")
    print(f"    - 1 future  (next_run in 1 hour)")
    print(f"    - 1 paused  (next_run in the past, but paused)")
    print()

    due = store.get_due_tasks()
    print(f"  getDueTasks() returned {len(due)} task(s):")
    for t in due:
        print(f"    {t.id}: '{t.prompt}' (next_run={fmt_time(t.next_run)})")
    print()

    print("  Key: only active tasks with next_run <= now are returned.")
    print("  SQL equivalent: WHERE status='active' AND next_run IS NOT NULL AND next_run <= ?")


# ── Demo 3: next_run 计算 ────────────────────────────────────────


def demo_next_run_calculation():
    """展示三种调度类型的 next_run 计算逻辑。"""
    print()
    print("=" * 64)
    print("Demo 3: next_run Calculation (cron / interval / once)")
    print("=" * 64)
    print()

    print("  After a task runs, calculate_next_run() determines the next execution time:")
    print()

    # Cron: 使用 croniter 解析 cron 表达式
    cron_next = calculate_next_run(ScheduleType.CRON, "*/15 * * * *")
    print(f"  [cron]     '*/15 * * * *'  ->  next_run = {fmt_time(cron_next)}")
    print(f"             (croniter finds the next matching minute)")

    cron_hourly = calculate_next_run(ScheduleType.CRON, "0 * * * *")
    print(f"  [cron]     '0 * * * *'     ->  next_run = {fmt_time(cron_hourly)}")
    print(f"             (next full hour)")
    print()

    # Interval: 当前时间 + 毫秒
    interval_next = calculate_next_run(ScheduleType.INTERVAL, "300000")
    print(f"  [interval] '300000' (5min) ->  next_run = {fmt_time(interval_next)}")
    print(f"             (now + 300000ms = now + 5 minutes)")

    interval_short = calculate_next_run(ScheduleType.INTERVAL, "10000")
    print(f"  [interval] '10000' (10s)   ->  next_run = {fmt_time(interval_short)}")
    print()

    # Once: 返回 None（任务完成，不再调度）
    once_next = calculate_next_run(ScheduleType.ONCE, "2026-02-25T10:00:00Z")
    print(f"  [once]     (any value)     ->  next_run = {once_next}")
    print(f"             (None = no more runs, task status -> completed)")
    print()

    print("  Original code (task-scheduler.ts:162-173):")
    print("    cron:     CronExpressionParser.parse(value).next().toISOString()")
    print("    interval: new Date(Date.now() + parseInt(value)).toISOString()")
    print("    once:     (no next_run)")


# ── Demo 4: context_mode ─────────────────────────────────────────


def demo_context_mode():
    """展示 group 和 isolated 两种 context mode 的行为差异。"""
    print()
    print("=" * 64)
    print("Demo 4: Context Mode (group vs isolated)")
    print("=" * 64)
    print()

    # 模拟 session 注册表（group_folder -> session_id）
    sessions: dict[str, str] = {
        "dev-team": "session-abc123",
        "monitoring": "session-def456",
    }

    store = TaskStore()
    now = datetime.now(timezone.utc)
    past = (now - timedelta(seconds=10)).isoformat()

    # Group mode: 复用已有 session，保留对话历史
    group_task = store.add_task(ScheduledTask(
        id="task-group-ctx",
        group_folder="dev-team",
        chat_jid="dev@g.us",
        prompt="Check project status",
        schedule_type=ScheduleType.INTERVAL,
        schedule_value="60000",
        context_mode=ContextMode.GROUP,
        next_run=past,
    ))

    # Isolated mode: 每次创建全新 session
    isolated_task = store.add_task(ScheduledTask(
        id="task-isolated-ctx",
        group_folder="monitoring",
        chat_jid="mon@g.us",
        prompt="Run health check",
        schedule_type=ScheduleType.INTERVAL,
        schedule_value="60000",
        context_mode=ContextMode.ISOLATED,
        next_run=past,
    ))

    print("  [group mode]    context_mode='group'")
    print(f"    Task:       {group_task.id}")
    print(f"    Group:      {group_task.group_folder}")
    session_id = sessions.get(group_task.group_folder, None)
    print(f"    Session:    {session_id} (reuses existing group session)")
    print(f"    Effect:     Agent sees previous conversation history")
    print(f"    Use case:   Follow-up tasks that need context from earlier runs")
    print()

    print("  [isolated mode] context_mode='isolated'")
    print(f"    Task:       {isolated_task.id}")
    print(f"    Group:      {isolated_task.group_folder}")
    print(f"    Session:    None (creates fresh session each run)")
    print(f"    Effect:     Agent starts with clean slate, no history")
    print(f"    Use case:   Independent checks that should not be influenced by history")
    print()

    print("  Original code (task-scheduler.ts:110-111):")
    print("    const sessionId =")
    print("      task.context_mode === 'group' ? sessions[task.group_folder] : undefined;")


# ── Demo 5: 任务生命周期 ─────────────────────────────────────────


def demo_lifecycle():
    """演示完整的任务生命周期：active -> running -> update -> pause -> resume -> cancel。"""
    print()
    print("=" * 64)
    print("Demo 5: Task Lifecycle (active/paused/completed)")
    print("=" * 64)
    print()

    store = TaskStore()
    now = datetime.now(timezone.utc)
    past = (now - timedelta(seconds=10)).isoformat()

    # 创建一个 interval 任务
    task = store.add_task(ScheduledTask(
        id="task-lifecycle",
        group_folder="team-x",
        chat_jid="x@g.us",
        prompt="Daily standup reminder",
        schedule_type=ScheduleType.INTERVAL,
        schedule_value="60000",
        context_mode=ContextMode.ISOLATED,
        next_run=past,  # 已到期
    ))
    print(f"  1. CREATED  {fmt_status(task)}")

    # 轮询执行（模拟 SchedulerLoop.poll）
    scheduler = SchedulerLoop(store)
    results = scheduler.poll()
    task = store.get_task("task-lifecycle")
    assert task is not None
    print(f"  2. RAN      {fmt_status(task)}")
    print(f"              last_result='{task.last_result}'")
    print(f"              (next_run updated: interval adds 60000ms from now)")

    # 暂停
    ok = store.pause_task("task-lifecycle")
    task = store.get_task("task-lifecycle")
    assert task is not None
    print(f"  3. PAUSED   {fmt_status(task)}  (pause={ok})")

    # 暂停期间轮询——不应执行
    results = scheduler.poll()
    print(f"  4. POLL     (while paused) -> executed {len(results)} tasks (expected 0)")

    # 恢复
    ok = store.resume_task("task-lifecycle")
    task = store.get_task("task-lifecycle")
    assert task is not None
    print(f"  5. RESUMED  {fmt_status(task)}  (resume={ok})")
    print(f"              (next_run recalculated to avoid stale backlog)")

    # 取消
    ok = store.cancel_task("task-lifecycle")
    task = store.get_task("task-lifecycle")
    assert task is not None
    print(f"  6. CANCEL   {fmt_status(task)}  (cancel={ok})")
    print(f"              (next_run=None, no more executions)")
    print()

    # Once 任务自动完成
    once_task = store.add_task(ScheduledTask(
        id="task-once-lifecycle",
        group_folder="team-y",
        chat_jid="y@g.us",
        prompt="One-time deployment",
        schedule_type=ScheduleType.ONCE,
        schedule_value=past,
        context_mode=ContextMode.ISOLATED,
        next_run=past,
    ))
    print(f"  7. ONCE created  {fmt_status(once_task)}")
    scheduler.poll()
    once_task = store.get_task("task-once-lifecycle")
    assert once_task is not None
    print(f"  8. ONCE ran      {fmt_status(once_task)}")
    print(f"     (once tasks auto-complete: next_run=None -> status=completed)")

    # 查看运行日志
    print()
    logs = store.get_run_logs("task-lifecycle")
    print(f"  Run logs for task-lifecycle: {len(logs)} entries")
    for log in logs:
        print(f"    [{log.status}] at {fmt_time(log.run_at)}")


# ── Main ──────────────────────────────────────────────────────────


def main():
    print("NanoClaw Task Scheduler Demo")
    print("Reproduces the cron/interval/once scheduling + context modes\n")

    demo_schedule_types()
    demo_due_tasks()
    demo_next_run_calculation()
    demo_context_mode()
    demo_lifecycle()

    print()
    print("=" * 64)
    print("Summary")
    print("=" * 64)
    print()
    print("  Schedule types:")
    print("    cron:     standard cron expression, parsed by croniter")
    print("    interval: milliseconds between runs (now + ms)")
    print("    once:     one-time timestamp, auto-completes after run")
    print()
    print("  Context modes:")
    print("    group:    reuses existing session (has conversation history)")
    print("    isolated: fresh session each run (clean slate)")
    print()
    print("  Polling loop (60s interval):")
    print("    getDueTasks() -> enqueueTask() -> runTask() -> updateTaskAfterRun()")
    print()
    print("  Lifecycle: active -> (run) -> active | paused | completed")
    print("    pause/resume: manual control; cancel: permanent stop")
    print("    once tasks: auto-complete after single execution")


if __name__ == "__main__":
    main()
