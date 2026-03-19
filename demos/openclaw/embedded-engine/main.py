"""
OpenClaw — Embedded Engine 机制复现

复现 OpenClaw 内嵌 pi-agent 的调用链：
- runEmbeddedPiAgent → buildPayloads → runWithModelFallback → attempt
- Model Fallback（主 provider 失败 → 自动切换备用）
- Auth Profile 轮转（多 API key 按优先级尝试 + cooldown 追踪）
- Failover 分类器（按错误类型选择恢复策略）

对应源码: src/agents/pi-embedded-runner/run.ts, run/attempt.ts
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ── Failover 分类 ─────────────────────────────────────────────────

class FailoverReason(str, Enum):
    AUTH = "auth"
    BILLING = "billing"
    RATE_LIMIT = "rate-limit"
    TIMEOUT = "timeout"
    CONTEXT_OVERFLOW = "context-overflow"
    UNKNOWN = "unknown"


def classify_failover_reason(error_msg: str) -> FailoverReason:
    """
    错误分类器：根据错误消息判断失败原因

    对应源码: classifyFailoverReason() in run.ts
    """
    lower = error_msg.lower()
    if "invalid api key" in lower or "unauthorized" in lower or "authentication" in lower:
        return FailoverReason.AUTH
    if "billing" in lower or "quota" in lower or "insufficient" in lower:
        return FailoverReason.BILLING
    if "rate limit" in lower or "too many requests" in lower or "429" in lower:
        return FailoverReason.RATE_LIMIT
    if "timeout" in lower or "timed out" in lower:
        return FailoverReason.TIMEOUT
    if "context" in lower and ("overflow" in lower or "too long" in lower or "exceed" in lower):
        return FailoverReason.CONTEXT_OVERFLOW
    return FailoverReason.UNKNOWN


# ── Auth Profile ──────────────────────────────────────────────────

@dataclass
class AuthProfile:
    """API 认证配置"""
    profile_id: str
    provider: str          # "anthropic" / "openai" / "google"
    api_key: str
    model: str
    priority: int = 0      # 越小优先级越高
    cooldown_until: float = 0.0  # Unix timestamp
    failure_count: int = 0

    @property
    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    def mark_failure(self, reason: FailoverReason):
        """标记失败，设置 cooldown"""
        self.failure_count += 1
        # 按错误类型设置不同的 cooldown 时长
        cooldown_map = {
            FailoverReason.RATE_LIMIT: 60,     # 60s
            FailoverReason.AUTH: 300,           # 5min（可能是 key 过期）
            FailoverReason.BILLING: 3600,       # 1h（需要充值）
            FailoverReason.TIMEOUT: 30,         # 30s
        }
        duration = cooldown_map.get(reason, 15)
        self.cooldown_until = time.time() + duration


# ── 模拟 LLM 调用 ────────────────────────────────────────────────

@dataclass
class AttemptResult:
    success: bool
    response: str = ""
    error: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    profile_id: str = ""
    model: str = ""


class MockLLM:
    """模拟 LLM provider（可配置失败行为）"""

    def __init__(self, failure_schedule: dict[str, str] | None = None):
        # profile_id → 错误消息（None 表示成功）
        self._failures = failure_schedule or {}

    def call(self, profile: AuthProfile, prompt: str) -> AttemptResult:
        error = self._failures.get(profile.profile_id)
        if error:
            return AttemptResult(
                success=False, error=error,
                profile_id=profile.profile_id, model=profile.model,
            )
        tokens = random.randint(100, 500)
        return AttemptResult(
            success=True,
            response=f"[{profile.provider}/{profile.model}] Processed: {prompt[:30]}...",
            usage={"input_tokens": tokens, "output_tokens": tokens // 2},
            profile_id=profile.profile_id, model=profile.model,
        )


# ── 内嵌引擎 ──────────────────────────────────────────────────────

@dataclass
class EmbeddedRunResult:
    """内嵌运行结果"""
    success: bool
    response: str = ""
    attempts: int = 0
    final_profile: str = ""
    final_model: str = ""
    total_usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    failover_log: list[str] = field(default_factory=list)


class EmbeddedEngine:
    """
    OpenClaw 内嵌引擎复现

    核心调用链:
    runEmbeddedPiAgent()
      → 遍历 Auth Profiles（按 priority 排序，跳过 cooldown）
        → runEmbeddedAttempt()
          → 调用 LLM API
          → 成功 → 返回结果
          → 失败 → classifyFailoverReason() → 标记 cooldown → 切换 profile
    """

    def __init__(self, profiles: list[AuthProfile], llm: MockLLM):
        self.profiles = sorted(profiles, key=lambda p: p.priority)
        self.llm = llm

    def run(self, prompt: str, max_attempts: int = 5) -> EmbeddedRunResult:
        """
        执行内嵌 pi-agent 调用（含 model fallback + auth 轮转）

        对应源码: runEmbeddedPiAgent() in run.ts
        """
        result = EmbeddedRunResult(success=False)

        for attempt_num in range(1, max_attempts + 1):
            # 选择可用的 profile（跳过 cooldown 中的）
            profile = self._pick_profile()
            if profile is None:
                result.failover_log.append(f"[尝试{attempt_num}] 所有 Profile 都在 cooldown 中，终止")
                break

            result.attempts = attempt_num
            result.failover_log.append(
                f"[尝试{attempt_num}] 使用 {profile.profile_id} ({profile.provider}/{profile.model})"
            )

            # 执行单次尝试（对应 runEmbeddedAttempt）
            attempt = self.llm.call(profile, prompt)

            if attempt.success:
                result.success = True
                result.response = attempt.response
                result.final_profile = attempt.profile_id
                result.final_model = attempt.model
                result.total_usage["input_tokens"] += attempt.usage.get("input_tokens", 0)
                result.total_usage["output_tokens"] += attempt.usage.get("output_tokens", 0)
                result.failover_log.append(f"  ✓ 成功")
                break

            # 失败 → 分类并标记 cooldown
            reason = classify_failover_reason(attempt.error)
            profile.mark_failure(reason)
            result.failover_log.append(
                f"  ✗ 失败: {attempt.error} → 分类: {reason.value} → cooldown {profile.failure_count}次"
            )

            # Billing 错误不可恢复
            if reason == FailoverReason.BILLING:
                result.failover_log.append(f"  ⊘ Billing 错误不可恢复，终止")
                break

        return result

    def _pick_profile(self) -> Optional[AuthProfile]:
        """选择第一个不在 cooldown 中的 profile"""
        for p in self.profiles:
            if not p.in_cooldown:
                return p
        return None


# ── Demo ──────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("OpenClaw Embedded Engine Demo")
    print("=" * 64)

    # ── 场景 1: 正常调用（首个 profile 成功） ──
    print("\n── 场景 1: 正常调用 ──")
    profiles = [
        AuthProfile("anthropic-main", "anthropic", "sk-ant-xxx", "claude-sonnet-4-20250514", priority=0),
        AuthProfile("openai-backup", "openai", "sk-oai-xxx", "gpt-4o", priority=1),
    ]
    engine = EmbeddedEngine(profiles, MockLLM())
    result = engine.run("请分析这段代码的性能问题")
    for line in result.failover_log:
        print(f"  {line}")
    print(f"  结果: {result.response}")

    # ── 场景 2: 主 provider rate limit → 自动 fallback ──
    print("\n── 场景 2: Rate Limit Fallback ──")
    profiles = [
        AuthProfile("anthropic-main", "anthropic", "sk-ant-xxx", "claude-sonnet-4-20250514", priority=0),
        AuthProfile("openai-backup", "openai", "sk-oai-xxx", "gpt-4o", priority=1),
        AuthProfile("google-backup", "google", "goog-xxx", "gemini-2.5-pro", priority=2),
    ]
    llm = MockLLM(failure_schedule={
        "anthropic-main": "Error 429: Too many requests - rate limit exceeded",
    })
    engine = EmbeddedEngine(profiles, llm)
    result = engine.run("重构 user service 模块")
    for line in result.failover_log:
        print(f"  {line}")
    print(f"  最终: profile={result.final_profile}, model={result.final_model}")

    # ── 场景 3: Auth 失败连锁 → 多次轮转 ──
    print("\n── 场景 3: Auth 连锁失败 ──")
    profiles = [
        AuthProfile("key-1", "anthropic", "sk-expired", "claude-sonnet-4-20250514", priority=0),
        AuthProfile("key-2", "anthropic", "sk-revoked", "claude-sonnet-4-20250514", priority=1),
        AuthProfile("key-3", "openai", "sk-valid", "gpt-4o", priority=2),
    ]
    llm = MockLLM(failure_schedule={
        "key-1": "Unauthorized: Invalid API key",
        "key-2": "Authentication failed: key revoked",
    })
    engine = EmbeddedEngine(profiles, llm)
    result = engine.run("修复登录 bug")
    for line in result.failover_log:
        print(f"  {line}")
    print(f"  最终: profile={result.final_profile}, model={result.final_model}")

    # ── 场景 4: Billing 错误（不可恢复） ──
    print("\n── 场景 4: Billing 不可恢复 ──")
    profiles = [
        AuthProfile("only-key", "anthropic", "sk-broke", "claude-sonnet-4-20250514", priority=0),
    ]
    llm = MockLLM(failure_schedule={
        "only-key": "Billing error: insufficient quota",
    })
    engine = EmbeddedEngine(profiles, llm)
    result = engine.run("生成单元测试")
    for line in result.failover_log:
        print(f"  {line}")
    print(f"  成功: {result.success}")

    # ── 场景 5: Failover 分类器 ──
    print("\n── Failover 分类器 ──")
    test_errors = [
        "Error 429: Too many requests",
        "Unauthorized: Invalid API key",
        "Billing error: insufficient quota",
        "Request timed out after 30s",
        "Context length exceeded: 200k tokens too long",
        "Internal server error",
    ]
    for err in test_errors:
        reason = classify_failover_reason(err)
        print(f"  {err:50s} → {reason.value}")


if __name__ == "__main__":
    main()
