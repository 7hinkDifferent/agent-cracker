"""
OpenClaw — Auth Profile Rotation 机制复现

复现 OpenClaw 的多 API Key 优先级轮转：
- 多 Auth Profile 按 priority 排序
- 失败后标记 cooldown，自动切换到下一个
- Cooldown 追踪（按错误类型设置不同时长）
- Profile 健康监控

对应源码: src/agents/auth-profiles.ts, pi-embedded-runner/run.ts
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── 数据模型 ──────────────────────────────────────────────────────

class FailureType(str, Enum):
    RATE_LIMIT = "rate-limit"
    AUTH = "auth"
    BILLING = "billing"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server-error"


COOLDOWN_DURATIONS: dict[FailureType, float] = {
    FailureType.RATE_LIMIT: 60,
    FailureType.AUTH: 300,
    FailureType.BILLING: 3600,
    FailureType.TIMEOUT: 30,
    FailureType.SERVER_ERROR: 120,
}


@dataclass
class AuthProfile:
    """认证配置"""
    id: str
    provider: str
    api_key: str
    model: str
    priority: int = 0
    # 运行时状态
    cooldown_until: float = 0.0
    total_requests: int = 0
    total_failures: int = 0
    last_failure: Optional[FailureType] = None
    last_failure_time: float = 0.0

    @property
    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        return max(0, self.cooldown_until - time.time())

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return (self.total_requests - self.total_failures) / self.total_requests


# ── Auth Profile Manager ─────────────────────────────────────────

class AuthProfileManager:
    """
    OpenClaw Auth Profile 轮转管理器

    机制：
    1. 按 priority 排序 profile
    2. 选择第一个不在 cooldown 中的 profile
    3. 失败时按错误类型标记 cooldown
    4. 所有 profile 耗尽 → 返回 None
    """

    def __init__(self, profiles: list[AuthProfile]):
        self.profiles = sorted(profiles, key=lambda p: p.priority)
        self.rotation_log: list[str] = []

    def pick(self) -> Optional[AuthProfile]:
        """选择最佳可用 profile"""
        for p in self.profiles:
            if not p.in_cooldown:
                return p
        return None

    def mark_success(self, profile: AuthProfile):
        """标记请求成功"""
        profile.total_requests += 1

    def mark_failure(self, profile: AuthProfile, failure_type: FailureType):
        """标记请求失败，设置 cooldown"""
        profile.total_requests += 1
        profile.total_failures += 1
        profile.last_failure = failure_type
        profile.last_failure_time = time.time()

        duration = COOLDOWN_DURATIONS.get(failure_type, 60)
        profile.cooldown_until = time.time() + duration

        self.rotation_log.append(
            f"{profile.id} ({profile.provider}) → {failure_type.value} → cooldown {duration:.0f}s"
        )

    def health_report(self) -> list[dict]:
        """生成健康报告"""
        report = []
        for p in self.profiles:
            report.append({
                "id": p.id,
                "provider": p.provider,
                "model": p.model,
                "priority": p.priority,
                "in_cooldown": p.in_cooldown,
                "cooldown_remaining": f"{p.cooldown_remaining:.0f}s",
                "success_rate": f"{p.success_rate:.0%}",
                "requests": p.total_requests,
                "failures": p.total_failures,
            })
        return report

    def simulate_rotation(self, failure_sequence: list[tuple[str, FailureType]]) -> list[str]:
        """模拟一系列失败后的轮转过程"""
        results = []
        for profile_id, failure_type in failure_sequence:
            profile = next((p for p in self.profiles if p.id == profile_id), None)
            if profile:
                self.mark_failure(profile, failure_type)

            # 选择下一个
            next_profile = self.pick()
            if next_profile:
                results.append(f"  → 切换到 {next_profile.id} ({next_profile.provider}/{next_profile.model})")
            else:
                results.append(f"  → ⊘ 所有 profile 耗尽")
                break

        return results


# ── Demo ──────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("OpenClaw Auth Profile Rotation Demo")
    print("=" * 64)

    profiles = [
        AuthProfile("claude-primary", "anthropic", "sk-ant-1", "claude-sonnet-4-20250514", priority=0),
        AuthProfile("claude-backup", "anthropic", "sk-ant-2", "claude-sonnet-4-20250514", priority=1),
        AuthProfile("gpt4o-fallback", "openai", "sk-oai-1", "gpt-4o", priority=2),
        AuthProfile("gemini-last", "google", "goog-1", "gemini-2.5-pro", priority=3),
    ]

    mgr = AuthProfileManager(profiles)

    # ── 1. 正常选择 ──
    print("\n── 1. 正常选择（按 priority）──")
    picked = mgr.pick()
    print(f"  选中: {picked.id} (priority={picked.priority})")  # type: ignore

    # ── 2. 轮转模拟 ──
    print("\n── 2. Rate Limit 连锁轮转 ──")
    results = mgr.simulate_rotation([
        ("claude-primary", FailureType.RATE_LIMIT),
        ("claude-backup", FailureType.RATE_LIMIT),
        ("gpt4o-fallback", FailureType.RATE_LIMIT),
    ])
    for r in results:
        print(r)

    # ── 3. Cooldown 时长对比 ──
    print("\n── 3. 各错误类型 Cooldown 时长 ──")
    for ft, duration in COOLDOWN_DURATIONS.items():
        unit = "min" if duration >= 60 else "s"
        val = duration / 60 if duration >= 60 else duration
        print(f"  {ft.value:15s} → {val:.0f}{unit}")

    # ── 4. 所有 profile 耗尽 ──
    print("\n── 4. 所有 Profile 耗尽 ──")
    mgr2 = AuthProfileManager([
        AuthProfile("only-key", "anthropic", "sk-1", "claude-sonnet-4-20250514"),
    ])
    mgr2.mark_failure(mgr2.profiles[0], FailureType.BILLING)
    picked = mgr2.pick()
    print(f"  可用 profile: {'None' if picked is None else picked.id}")

    # ── 5. 健康报告 ──
    print("\n── 5. 健康报告 ──")
    # 模拟一些成功和失败
    mgr3 = AuthProfileManager([
        AuthProfile("prod-1", "anthropic", "sk-1", "claude-sonnet-4-20250514", priority=0),
        AuthProfile("prod-2", "openai", "sk-2", "gpt-4o", priority=1),
    ])
    for _ in range(8):
        mgr3.mark_success(mgr3.profiles[0])
    mgr3.mark_failure(mgr3.profiles[0], FailureType.RATE_LIMIT)
    mgr3.mark_failure(mgr3.profiles[0], FailureType.TIMEOUT)
    for _ in range(3):
        mgr3.mark_success(mgr3.profiles[1])

    print(f"  {'ID':15s} {'Provider':10s} {'Model':12s} {'Pri':3s} {'成功率':8s} {'请求':4s} {'失败':4s} {'Cooldown':10s}")
    print(f"  {'─'*15} {'─'*10} {'─'*12} {'─'*3} {'─'*8} {'─'*4} {'─'*4} {'─'*10}")
    for r in mgr3.health_report():
        print(
            f"  {r['id']:15s} {r['provider']:10s} {r['model']:12s} "
            f"{r['priority']:3d} {r['success_rate']:8s} {r['requests']:4d} "
            f"{r['failures']:4d} {r['cooldown_remaining']:>10s}"
        )


if __name__ == "__main__":
    main()
