"""
Eigent — 触发器系统 Demo

复现 eigent 的外部事件触发机制：
1. 三种触发器类型：webhook, slack, cron（定时调度）
2. Trigger 数据模型：id, name, type, status, webhook_url, config
3. 速率限制（每用户/每项目最大触发器数）
4. Webhook 处理器：验证触发器 → 创建执行记录
5. 模拟 Celery Beat 定时调度器

原实现: server/app/controller/trigger/trigger_controller.py
       server/app/controller/trigger/webhook_controller.py
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ─── 触发器类型与状态 ──────────────────────────────────────────

class TriggerType(str, Enum):
    """触发器类型。

    原实现: server/app/model/trigger.py
    """
    WEBHOOK = "webhook"
    SLACK = "slack"
    CRON = "cron"


class TriggerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    RATE_LIMITED = "rate_limited"


# ─── 触发器数据模型 ────────────────────────────────────────────

@dataclass
class TriggerConfig:
    """触发器配置 — 不同类型有不同配置。"""
    cron_expression: str = ""       # cron 类型的调度表达式
    slack_channel: str = ""         # slack 类型的频道
    headers: dict[str, str] = field(default_factory=dict)  # webhook 验证头


@dataclass
class Trigger:
    """触发器模型 — 对应 eigent 的 Trigger 数据库模型。

    原实现: server/app/model/trigger.py
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    trigger_type: TriggerType = TriggerType.WEBHOOK
    status: TriggerStatus = TriggerStatus.ACTIVE
    project_id: str = ""
    user_id: str = ""
    webhook_url: str = ""          # 自动生成的 webhook URL
    webhook_secret: str = ""       # 用于签名验证
    config: TriggerConfig = field(default_factory=TriggerConfig)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.webhook_url and self.trigger_type == TriggerType.WEBHOOK:
            self.webhook_url = f"/api/webhook/{self.id}"
        if not self.webhook_secret:
            self.webhook_secret = hashlib.sha256(self.id.encode()).hexdigest()[:16]


@dataclass
class TriggerExecution:
    """触发器执行记录。

    原实现: 每次触发时创建执行记录，关联到 task
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trigger_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"        # pending, running, completed, failed
    task_id: str = ""              # 关联的 Agent 任务
    created_at: float = field(default_factory=time.time)


# ─── 速率限制 ─────────────────────────────────────────────────

class RateLimiter:
    """触发器速率限制 — 防止滥用。

    原实现: trigger_controller.py 中的 MAX_TRIGGERS_PER_USER 等限制
    """
    MAX_PER_USER = 10
    MAX_PER_PROJECT = 5
    MAX_EXECUTIONS_PER_MINUTE = 30

    def __init__(self) -> None:
        self._execution_log: list[float] = []

    def check_create_limit(self, triggers: list[Trigger], user_id: str,
                           project_id: str) -> tuple[bool, str]:
        """检查是否可以创建新触发器。"""
        user_count = sum(1 for t in triggers if t.user_id == user_id)
        if user_count >= self.MAX_PER_USER:
            return False, f"User limit reached ({self.MAX_PER_USER})"

        project_count = sum(1 for t in triggers if t.project_id == project_id)
        if project_count >= self.MAX_PER_PROJECT:
            return False, f"Project limit reached ({self.MAX_PER_PROJECT})"

        return True, "OK"

    def check_execution_limit(self) -> tuple[bool, str]:
        """检查执行速率限制。"""
        now = time.time()
        # 清理一分钟前的记录
        self._execution_log = [t for t in self._execution_log if now - t < 60]

        if len(self._execution_log) >= self.MAX_EXECUTIONS_PER_MINUTE:
            return False, f"Rate limit: {self.MAX_EXECUTIONS_PER_MINUTE}/min"

        self._execution_log.append(now)
        return True, "OK"


# ─── 触发器管理器 ─────────────────────────────────────────────

class TriggerManager:
    """触发器 CRUD + Webhook 处理 + Cron 调度。

    原实现: trigger_controller.py (CRUD)
           webhook_controller.py (webhook 处理)
    """

    def __init__(self) -> None:
        self.triggers: dict[str, Trigger] = {}
        self.executions: list[TriggerExecution] = []
        self.rate_limiter = RateLimiter()

    # ─── CRUD ──────────────────────────────────────────

    def create_trigger(self, name: str, trigger_type: TriggerType,
                       user_id: str, project_id: str,
                       config: TriggerConfig | None = None) -> Trigger | str:
        """创建触发器 — 含速率限制检查。"""
        ok, msg = self.rate_limiter.check_create_limit(
            list(self.triggers.values()), user_id, project_id)
        if not ok:
            return msg

        trigger = Trigger(
            name=name,
            trigger_type=trigger_type,
            user_id=user_id,
            project_id=project_id,
            config=config or TriggerConfig(),
        )
        self.triggers[trigger.id] = trigger
        return trigger

    def list_triggers(self, project_id: str = "") -> list[Trigger]:
        if project_id:
            return [t for t in self.triggers.values() if t.project_id == project_id]
        return list(self.triggers.values())

    def delete_trigger(self, trigger_id: str) -> bool:
        return self.triggers.pop(trigger_id, None) is not None

    # ─── Webhook 处理 ──────────────────────────────────

    def handle_webhook(self, trigger_id: str,
                       payload: dict[str, Any]) -> TriggerExecution | str:
        """处理 Webhook 请求 — 验证 → 创建执行记录 → 模拟任务创建。

        原实现: webhook_controller.py webhook_handler()
        流程:
        1. 查找触发器
        2. 验证状态（active）
        3. 速率限制检查
        4. 创建执行记录
        5. 异步启动 Agent 任务
        """
        trigger = self.triggers.get(trigger_id)
        if not trigger:
            return f"Trigger '{trigger_id}' not found"

        if trigger.status != TriggerStatus.ACTIVE:
            return f"Trigger '{trigger.name}' is {trigger.status.value}"

        ok, msg = self.rate_limiter.check_execution_limit()
        if not ok:
            trigger.status = TriggerStatus.RATE_LIMITED
            return msg

        execution = TriggerExecution(
            trigger_id=trigger_id,
            payload=payload,
            task_id=f"task-{str(uuid.uuid4())[:8]}",
        )
        self.executions.append(execution)

        # 模拟异步任务启动
        execution.status = "running"
        print(f"    -> Created task {execution.task_id} from trigger '{trigger.name}'")

        return execution

    # ─── Cron 调度器 ───────────────────────────────────

    def run_cron_check(self, current_minute: int = 0) -> list[TriggerExecution]:
        """模拟 Celery Beat 定时检查 — 每分钟扫描 cron 触发器。

        原实现: Celery Beat 定时任务扫描 cron 类型触发器
        """
        triggered = []
        for trigger in self.triggers.values():
            if (trigger.trigger_type == TriggerType.CRON
                    and trigger.status == TriggerStatus.ACTIVE
                    and trigger.config.cron_expression):
                # 简化的 cron 匹配：仅检查 */N 分钟模式
                expr = trigger.config.cron_expression
                if expr.startswith("*/"):
                    interval = int(expr.split()[0].replace("*/", ""))
                    if current_minute % interval == 0:
                        result = self.handle_webhook(
                            trigger.id,
                            {"source": "cron", "minute": current_minute},
                        )
                        if isinstance(result, TriggerExecution):
                            triggered.append(result)
        return triggered


# ─── Demo ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Eigent 触发器系统 Demo")
    print("=" * 60)

    manager = TriggerManager()

    # 1. 创建不同类型的触发器
    print("\n--- 创建触发器 ---\n")

    wh = manager.create_trigger(
        "Deploy Notification", TriggerType.WEBHOOK,
        user_id="user-1", project_id="proj-1",
    )
    print(f"  [webhook] {wh.name} (id={wh.id}, url={wh.webhook_url})")

    slack = manager.create_trigger(
        "Slack Command", TriggerType.SLACK,
        user_id="user-1", project_id="proj-1",
        config=TriggerConfig(slack_channel="#dev-ops"),
    )
    print(f"  [slack]   {slack.name} (id={slack.id}, channel={slack.config.slack_channel})")

    cron = manager.create_trigger(
        "Hourly Report", TriggerType.CRON,
        user_id="user-1", project_id="proj-1",
        config=TriggerConfig(cron_expression="*/15 * * * *"),
    )
    print(f"  [cron]    {cron.name} (id={cron.id}, expr={cron.config.cron_expression})")

    # 2. Webhook 触发
    print(f"\n{'─' * 40}")
    print("--- Webhook 触发 ---\n")

    result = manager.handle_webhook(wh.id, {
        "event": "push",
        "repository": "eigent-ai/eigent",
        "branch": "main",
    })
    if isinstance(result, TriggerExecution):
        print(f"  Execution: id={result.id}, task={result.task_id}, status={result.status}")

    # 3. Cron 调度模拟
    print(f"\n{'─' * 40}")
    print("--- Cron 调度模拟 (0-30 分钟) ---\n")

    for minute in range(0, 31, 5):
        triggered = manager.run_cron_check(minute)
        if triggered:
            for ex in triggered:
                print(f"  [min={minute:02d}] Cron fired: {cron.name} -> task={ex.task_id}")
        else:
            print(f"  [min={minute:02d}] No cron triggers")

    # 4. 速率限制测试
    print(f"\n{'─' * 40}")
    print("--- 速率限制测试 ---\n")

    # 项目级限制
    for i in range(3):
        result = manager.create_trigger(
            f"Extra-{i}", TriggerType.WEBHOOK,
            user_id="user-1", project_id="proj-1",
        )
        if isinstance(result, str):
            print(f"  Trigger #{i+4} rejected: {result}")
        else:
            print(f"  Trigger #{i+4} created: {result.name}")

    # 5. 触发器列表
    print(f"\n{'─' * 40}")
    print("--- 项目 proj-1 的触发器 ---\n")

    for t in manager.list_triggers("proj-1"):
        print(f"  [{t.trigger_type.value:7s}] {t.name:20s} status={t.status.value}")

    # 6. 执行记录
    print(f"\n{'─' * 40}")
    print(f"--- 执行记录 (共 {len(manager.executions)} 条) ---\n")
    for ex in manager.executions[:5]:
        trigger = manager.triggers.get(ex.trigger_id)
        name = trigger.name if trigger else "?"
        source = ex.payload.get("source", ex.payload.get("event", "?"))
        print(f"  {ex.id} | trigger={name:20s} | source={source:6s} | task={ex.task_id}")

    print(f"\nDemo 完成")


if __name__ == "__main__":
    main()
