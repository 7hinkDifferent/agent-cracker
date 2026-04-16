from __future__ import annotations

"""Fresh-session cron delivery demo for Hermes."""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CronJob:
    job_id: str
    schedule: str
    prompt: str
    delivery_platform: str
    delivery_target: str
    injected_skills: list[str] = field(default_factory=list)


class DeliveryRouter:
    def send(self, platform: str, target: str, text: str) -> str:
        return f"delivered to {platform}:{target} -> {text}"


class CronRunner:
    """Run each job in a fresh session and deliver the result."""

    def __init__(self, agent_run: Callable[[str, list[str]], str]):
        self.agent_run = agent_run
        self.router = DeliveryRouter()

    def execute(self, job: CronJob) -> str:
        fresh_session_id = f"cron::{job.job_id}"
        result = self.agent_run(job.prompt, job.injected_skills)
        return self.router.send(
            job.delivery_platform,
            job.delivery_target,
            f"[{fresh_session_id}] {result}",
        )
