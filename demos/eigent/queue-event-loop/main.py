"""
Eigent — 队列驱动事件循环 Demo

复现 eigent 的核心主循环机制：通过 asyncio.Queue 解耦事件分发，
支持多种 Action 类型（improve/start/end/stop），以 SSE 格式流式输出。

原实现: backend/app/service/chat_service.py (step_solve)
       backend/app/service/task.py (Action, TaskLock)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator

import litellm


# ─── Action 枚举 ───────────────────────────────────────────────
# 原实现 Action 有 20+ 种类型，这里保留核心的 6 种

class Action(str, Enum):
    improve = "improve"            # 用户 → 后端: 新问题
    start = "start"                # 用户 → 后端: 确认执行
    activate_agent = "activate_agent"    # 后端 → 用户: Agent 开始工作
    deactivate_agent = "deactivate_agent"  # 后端 → 用户: Agent 完成工作
    end = "end"                    # 后端 → 用户: 任务完成
    stop = "stop"                  # 用户 → 后端: 停止


# ─── Action 数据结构 ──────────────────────────────────────────

@dataclass
class ActionData:
    """所有 Action 事件的通用载体"""
    action: Action
    data: dict[str, Any] = field(default_factory=dict)


# ─── TaskLock: 任务状态 + 队列 ──────────────────────────────

class TaskLock:
    """任务锁 — 持有异步队列和对话历史。

    原实现中 TaskLock 是全局字典 task_locks[project_id] 的值，
    每个项目一个实例。这里简化为单实例。
    """

    def __init__(self, task_id: str) -> None:
        self.id = task_id
        self.queue: asyncio.Queue[ActionData] = asyncio.Queue()
        self.conversation_history: list[dict[str, Any]] = []
        self.status = "idle"

    async def put_queue(self, item: ActionData) -> None:
        await self.queue.put(item)

    async def get_queue(self) -> ActionData:
        return await self.queue.get()

    def add_conversation(self, role: str, content: str) -> None:
        self.conversation_history.append({"role": role, "content": content})


# ─── SSE 格式化 ───────────────────────────────────────────────

def sse_json(event: str, data: dict) -> str:
    """格式化为 Server-Sent Events 格式。

    原实现: app/model/chat.py sse_json()
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ─── 复杂度判断 ────────────────────────────────────────────────

async def check_complexity(question: str) -> bool:
    """判断任务复杂度 — 简单问题直接回答，复杂任务走 Workforce。

    原实现中使用 question_confirm_agent（一个 LLM Agent）来判断，
    这里简化为基于关键词的规则判断。
    """
    complex_keywords = ["写代码", "创建", "调研", "分析", "部署", "build", "create", "research", "deploy"]
    return any(kw in question.lower() for kw in complex_keywords)


# ─── 模拟 Agent 执行 ──────────────────────────────────────────

async def run_simple_answer(question: str, task_lock: TaskLock) -> str:
    """简单问题 — 直接调用 LLM 回答。

    原实现中由 question_confirm_agent.step() 处理。
    """
    model = os.environ.get("DEMO_MODEL", "gpt-4o-mini")
    response = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
            {"role": "user", "content": question},
        ],
        max_tokens=200,
    )
    return response.choices[0].message.content


async def run_workforce(question: str, task_lock: TaskLock) -> str:
    """复杂任务 — 模拟 Workforce 分解 + 执行。

    原实现中:
    1. workforce.eigent_make_sub_tasks() 分解任务
    2. workforce.eigent_start() 并行执行
    3. 通过 ActionTaskStateData 报告子任务状态

    这里简化为: LLM 分解 → 模拟执行每个子任务。
    """
    model = os.environ.get("DEMO_MODEL", "gpt-4o-mini")

    # 1. 任务分解（模拟 eigent_make_sub_tasks）
    decompose_resp = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": (
                "You are a task coordinator. Break the task into 2-3 subtasks. "
                "Return ONLY a JSON array of strings, each being a subtask description. "
                "Example: [\"Research topic X\", \"Write code for Y\"]"
            )},
            {"role": "user", "content": question},
        ],
        max_tokens=200,
    )
    raw = decompose_resp.choices[0].message.content.strip()

    # 解析子任务
    try:
        subtasks = json.loads(raw)
        if not isinstance(subtasks, list):
            subtasks = [question]
    except json.JSONDecodeError:
        subtasks = [question]

    print(f"\n  📋 任务分解为 {len(subtasks)} 个子任务:")
    for i, st in enumerate(subtasks, 1):
        print(f"     {i}. {st}")

    # 2. 模拟并行执行（原实现通过 CAMEL TaskChannel 并行）
    results = []
    for i, subtask in enumerate(subtasks):
        # 发送 Agent 激活事件
        await task_lock.put_queue(ActionData(
            action=Action.activate_agent,
            data={"agent_name": f"worker_{i+1}", "task": subtask},
        ))

        # 模拟执行
        resp = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": "Complete this subtask concisely in 1-2 sentences."},
                {"role": "user", "content": subtask},
            ],
            max_tokens=100,
        )
        result = resp.choices[0].message.content

        # 发送 Agent 停用事件
        await task_lock.put_queue(ActionData(
            action=Action.deactivate_agent,
            data={"agent_name": f"worker_{i+1}", "result": result},
        ))
        results.append(f"[{subtask}]: {result}")

    return "\n".join(results)


# ─── 主事件循环 ──────────────────────────────────────────────

async def step_solve(task_lock: TaskLock) -> AsyncGenerator[str, None]:
    """队列驱动的主事件循环 — eigent 的核心。

    原实现: chat_service.step_solve()

    关键设计:
    - while True 循环从 queue 取事件
    - Action.improve: 判断复杂度 → 直接回答 or Workforce
    - Action.start: 启动 Workforce 执行
    - Action.end: 任务完成，但循环不退出（支持多轮）
    - Action.stop: 用户中断，循环退出
    - 内部事件（activate/deactivate）作为 SSE 流式推送
    """
    start_event_loop = True
    current_question = ""
    is_complex = False

    print("\n🔄 事件循环启动")

    while True:
        if start_event_loop:
            # 首次进入 — 从外部注入的初始问题
            item = ActionData(action=Action.improve, data={"question": task_lock.conversation_history[-1]["content"]})
            start_event_loop = False
        else:
            # 后续 — 从队列取事件
            item = await task_lock.get_queue()

        print(f"\n  ⚡ 收到事件: {item.action.value}")

        # ─── Action 分发 ─────────────────────────────────
        if item.action == Action.improve:
            current_question = item.data.get("question", "")
            print(f"  📝 问题: {current_question[:60]}...")

            # 复杂度判断（原实现: question_confirm）
            is_complex = await check_complexity(current_question)
            print(f"  🧠 复杂度判断: {'复杂任务 → Workforce' if is_complex else '简单问题 → 直接回答'}")

            if not is_complex:
                # 简单回答
                answer = await run_simple_answer(current_question, task_lock)
                task_lock.add_conversation("assistant", answer)
                yield sse_json("wait_confirm", {"content": answer, "question": current_question})
                print(f"  ✅ 回答完毕，等待追问...")

            else:
                # 复杂任务 — 确认后走 Workforce
                yield sse_json("confirmed", {"question": current_question})
                # 自动触发 start（原实现中由前端按钮触发）
                await task_lock.put_queue(ActionData(action=Action.start))

        elif item.action == Action.start:
            print("  🏭 Workforce 启动执行...")
            result = await run_workforce(current_question, task_lock)
            task_lock.add_conversation("task_result", result)

            # 任务完成 → 入队 end 事件
            await task_lock.put_queue(ActionData(action=Action.end, data={"result": result}))

        elif item.action == Action.activate_agent:
            agent = item.data.get("agent_name", "unknown")
            task = item.data.get("task", "")
            yield sse_json("activate_agent", {"agent_name": agent, "task": task})
            print(f"  🟢 Agent [{agent}] 激活: {task[:40]}...")

        elif item.action == Action.deactivate_agent:
            agent = item.data.get("agent_name", "unknown")
            result = item.data.get("result", "")
            yield sse_json("deactivate_agent", {"agent_name": agent, "result": result})
            print(f"  🔴 Agent [{agent}] 完成: {result[:40]}...")

        elif item.action == Action.end:
            result = item.data.get("result", "")
            yield sse_json("end", {"result": result})
            task_lock.status = "done"
            print(f"  🏁 任务完成！循环继续等待追问...")
            # 注意：循环不退出！等待下一个 improve 或 stop

        elif item.action == Action.stop:
            print("  ⏹️  用户停止，退出循环")
            break

    print("\n🔄 事件循环结束")


# ─── 模拟用户交互 ─────────────────────────────────────────────

async def simulate_user_session():
    """模拟一个完整的用户会话 — 多轮对话 + 停止。

    演示 eigent 事件循环的三个关键特性:
    1. 简单问题直接回答
    2. 复杂任务走 Workforce
    3. 多轮对话（循环不退出）
    """
    task_lock = TaskLock("demo-project-001")
    print("=" * 60)
    print("Eigent 队列驱动事件循环 Demo")
    print("=" * 60)

    # ─── 第 1 轮: 简单问题 ─────────────────────────────────
    print("\n" + "─" * 40)
    print("第 1 轮: 简单问题")
    print("─" * 40)

    question1 = "What is Python?"
    task_lock.add_conversation("user", question1)

    # 启动事件循环（模拟 POST /chat）
    loop_task = None
    sse_events = []

    async def consume_events():
        async for event in step_solve(task_lock):
            sse_events.append(event)

    loop_task = asyncio.create_task(consume_events())

    # 等待处理完成
    await asyncio.sleep(3)

    # ─── 第 2 轮: 复杂任务（追问，循环未退出）─────────────
    print("\n" + "─" * 40)
    print("第 2 轮: 复杂任务（追问）")
    print("─" * 40)

    question2 = "请创建一个 Python web scraper 来抓取新闻标题"
    task_lock.add_conversation("user", question2)
    await task_lock.put_queue(ActionData(
        action=Action.improve,
        data={"question": question2},
    ))

    # 等待 Workforce 执行完成
    await asyncio.sleep(8)

    # ─── 停止 ─────────────────────────────────────────────
    print("\n" + "─" * 40)
    print("发送停止信号")
    print("─" * 40)

    await task_lock.put_queue(ActionData(action=Action.stop))
    await asyncio.sleep(0.5)

    # 取消循环任务
    if loop_task and not loop_task.done():
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    # ─── 输出 SSE 事件汇总 ─────────────────────────────────
    print("\n" + "=" * 60)
    print(f"SSE 事件汇总 (共 {len(sse_events)} 个)")
    print("=" * 60)
    for i, event in enumerate(sse_events, 1):
        # 提取事件类型
        event_type = event.split("\n")[0].replace("event: ", "")
        data_line = event.split("\n")[1].replace("data: ", "")
        data = json.loads(data_line)
        summary = str(data)[:80] + "..." if len(str(data)) > 80 else str(data)
        print(f"  {i}. [{event_type}] {summary}")

    print("\n✅ Demo 完成")
    print(f"   对话历史: {len(task_lock.conversation_history)} 条")
    for entry in task_lock.conversation_history:
        role = entry["role"]
        content = entry["content"][:50] + "..." if len(entry["content"]) > 50 else entry["content"]
        print(f"   - [{role}] {content}")


if __name__ == "__main__":
    asyncio.run(simulate_user_session())
