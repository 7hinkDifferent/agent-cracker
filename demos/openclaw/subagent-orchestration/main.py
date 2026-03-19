"""
OpenClaw — Subagent Orchestration 机制复现

复现 OpenClaw 的子 Agent 生命周期管理：
- spawn（one-shot / persistent 两种模式）
- steer（运行中方向调整）
- kill（终止子 agent）
- 深度限制（防止无限递归派生）
- 跨 session 通信（结果自动 announce）

对应源码: src/agents/subagent-spawn.ts, src/agents/tools/subagents-tool.ts
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── 数据模型 ──────────────────────────────────────────────────────

class SpawnMode(str, Enum):
    RUN = "run"           # 一次性执行后返回结果
    SESSION = "session"   # 持久会话，可后续交互


class SubagentStatus(str, Enum):
    SPAWNING = "spawning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


@dataclass
class Subagent:
    """子 Agent 实例"""
    agent_id: str
    session_key: str       # 独立的 session key
    parent_id: str         # 父 agent ID
    mode: SpawnMode
    task: str              # 初始任务
    status: SubagentStatus = SubagentStatus.SPAWNING
    depth: int = 0         # 派生深度
    created_at: float = 0.0
    completed_at: float = 0.0
    result: str = ""
    steer_history: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()


@dataclass
class AnnounceEvent:
    """结果通知事件"""
    from_agent: str
    to_agent: str
    event_type: str   # "subagent_completed" / "subagent_failed"
    result: str
    timestamp: float = 0.0


# ── 编排引擎 ──────────────────────────────────────────────────────

class SubagentOrchestrator:
    """
    OpenClaw 子 Agent 编排器复现

    核心功能：
    1. spawn — 派生独立 agent（one-shot / persistent）
    2. steer — 运行中方向调整
    3. kill — 终止子 agent
    4. depth control — 防止无限递归
    5. auto-announce — 结果自动通知父 agent
    """

    MAX_SPAWN_DEPTH = 3
    MAX_CHILDREN_PER_AGENT = 5

    def __init__(self):
        self.agents: dict[str, Subagent] = {}
        self.events: list[AnnounceEvent] = []
        self._children_count: dict[str, int] = {}  # parent_id → count

    def spawn(
        self,
        parent_id: str,
        task: str,
        mode: SpawnMode = SpawnMode.RUN,
        parent_depth: int = 0,
    ) -> tuple[Optional[Subagent], str]:
        """
        派生子 Agent

        检���：
        1. 深度限制
        2. 每个 agent 的子 agent 数量限制
        """
        # 深度检查
        new_depth = parent_depth + 1
        if new_depth > self.MAX_SPAWN_DEPTH:
            return None, f"Depth limit exceeded: {new_depth} > {self.MAX_SPAWN_DEPTH}"

        # 子 agent 数量检查
        current_children = self._children_count.get(parent_id, 0)
        if current_children >= self.MAX_CHILDREN_PER_AGENT:
            return None, f"Max children reached: {current_children} >= {self.MAX_CHILDREN_PER_AGENT}"

        # 创建子 agent
        child_id = f"sub-{uuid.uuid4().hex[:6]}"
        session_key = f"agent:{parent_id}:subagent:{child_id}"

        agent = Subagent(
            agent_id=child_id,
            session_key=session_key,
            parent_id=parent_id,
            mode=mode,
            task=task,
            depth=new_depth,
            status=SubagentStatus.RUNNING,
        )
        self.agents[child_id] = agent
        self._children_count[parent_id] = current_children + 1

        return agent, f"Spawned {child_id} (depth={new_depth}, mode={mode.value})"

    def steer(self, agent_id: str, message: str) -> tuple[bool, str]:
        """向运行中的子 agent 发送方向调整"""
        agent = self.agents.get(agent_id)
        if not agent:
            return False, f"Agent not found: {agent_id}"
        if agent.status != SubagentStatus.RUNNING:
            return False, f"Agent not running: {agent.status.value}"

        agent.steer_history.append(message)
        return True, f"Steered {agent_id}: {message}"

    def kill(self, agent_id: str) -> tuple[bool, str]:
        """终止子 agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return False, f"Agent not found: {agent_id}"
        if agent.status not in (SubagentStatus.RUNNING, SubagentStatus.SPAWNING):
            return False, f"Agent already finished: {agent.status.value}"

        agent.status = SubagentStatus.KILLED
        agent.completed_at = time.time()
        self._children_count[agent.parent_id] = max(
            0, self._children_count.get(agent.parent_id, 1) - 1
        )
        return True, f"Killed {agent_id}"

    def complete(self, agent_id: str, result: str, success: bool = True):
        """子 agent 完成（模拟）→ 自动 announce"""
        agent = self.agents.get(agent_id)
        if not agent:
            return

        agent.status = SubagentStatus.COMPLETED if success else SubagentStatus.FAILED
        agent.result = result
        agent.completed_at = time.time()

        # 自动 announce 回父 agent
        event = AnnounceEvent(
            from_agent=agent_id,
            to_agent=agent.parent_id,
            event_type="subagent_completed" if success else "subagent_failed",
            result=result,
            timestamp=time.time(),
        )
        self.events.append(event)
        self._children_count[agent.parent_id] = max(
            0, self._children_count.get(agent.parent_id, 1) - 1
        )

    def list_children(self, parent_id: str) -> list[Subagent]:
        """列出某个 agent 的所有子 agent"""
        return [a for a in self.agents.values() if a.parent_id == parent_id]


# ── Demo ──────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("OpenClaw Subagent Orchestration Demo")
    print("=" * 64)

    orch = SubagentOrchestrator()

    # ── 1. Spawn ──
    print("\n── 1. Spawn 子 Agent ──")

    agent_a, msg = orch.spawn("main", "分析日志中的错误模式", SpawnMode.RUN)
    print(f"  {msg}")
    print(f"    session_key: {agent_a.session_key}")  # type: ignore

    agent_b, msg = orch.spawn("main", "监控 CPU 使用率", SpawnMode.SESSION)
    print(f"  {msg}")

    # ── 2. 嵌套 Spawn（深度控制） ──
    print("\n── 2. 深度控制 ──")

    # depth 0 → 1 → 2 → 3 (max)
    child_1, msg = orch.spawn(agent_a.agent_id, "子任务1", parent_depth=1)  # type: ignore
    print(f"  depth=2: {msg}")

    child_2, msg = orch.spawn(child_1.agent_id, "子子任务", parent_depth=2)  # type: ignore
    print(f"  depth=3: {msg}")

    child_3, msg = orch.spawn(child_2.agent_id, "子子子任务", parent_depth=3)  # type: ignore
    print(f"  depth=4: {msg}")

    # ── 3. Steer ──
    print("\n── 3. Steer 方向调整 ──")

    ok, msg = orch.steer(agent_b.agent_id, "优先关注 Node.js 进程")  # type: ignore
    print(f"  {msg}")

    ok, msg = orch.steer(agent_b.agent_id, "忽略系统进程")  # type: ignore
    print(f"  {msg}")

    print(f"  Steer 历史: {agent_b.steer_history}")  # type: ignore

    # ── 4. Complete + Auto-announce ──
    print("\n── 4. 完成 + 自动通知 ──")

    orch.complete(agent_a.agent_id, "发现 3 种错误模式: OOM, 超时, 连接重置")  # type: ignore
    print(f"  {agent_a.agent_id} 完成: {agent_a.result}")  # type: ignore

    # 检查 announce 事件
    for event in orch.events:
        print(f"  📨 {event.from_agent} → {event.to_agent}: {event.event_type}")
        print(f"     结果: {event.result}")

    # ── 5. Kill ──
    print("\n── 5. Kill 终止 ──")

    ok, msg = orch.kill(agent_b.agent_id)  # type: ignore
    print(f"  {msg} (status={agent_b.status.value})")  # type: ignore

    # 已终止的不能 steer
    ok, msg = orch.steer(agent_b.agent_id, "这条消息不会送达")  # type: ignore
    print(f"  steer 已终止 agent: {msg}")

    # ── 6. 子 agent 列表 ──
    print("\n── 6. Main 的子 Agent 列表 ──")
    children = orch.list_children("main")
    for child in children:
        print(f"  {child.agent_id}: mode={child.mode.value}, status={child.status.value}, task={child.task[:30]}")

    # ── 7. 数量限制 ──
    print("\n── 7. 数量限制测试 ──")
    for i in range(6):
        agent, msg = orch.spawn("limit-test", f"任务-{i+1}")
        status = "✓" if agent else "✗"
        print(f"  {status} 第{i+1}个: {msg}")


if __name__ == "__main__":
    main()
