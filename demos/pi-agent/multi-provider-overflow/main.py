"""
Pi-Agent Multi-Provider Overflow Demo

复现 Pi-Agent 的多 Provider Overflow 检测机制：
- 5+ Provider 错误模式匹配（Anthropic/OpenAI/Google/xAI/Mistral）
- 静默溢出检测（usage > contextWindow）
- 重试延迟提取（Retry-After / 错误消息）
- 溢出触发自动 compaction + 重试

Run: uv run python main.py
"""

import re
from dataclasses import dataclass


# ── Overflow 检测 ─────────────────────────────────────────────────

@dataclass
class OverflowResult:
    """溢出检测结果。"""
    is_overflow: bool
    provider: str = ""
    detail: str = ""
    input_tokens: int = 0
    max_tokens: int = 0


# Provider 错误模式（正则匹配）
OVERFLOW_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("anthropic", re.compile(r"prompt is too long: (\d+) tokens > (\d+) maximum")),
    ("openai", re.compile(r"(?:exceeds|exceeded) the (?:context window|maximum context length|token limit)")),
    ("openai", re.compile(r"maximum context length is (\d+) tokens.*?(\d+) tokens", re.DOTALL)),
    ("google", re.compile(r"input token count \((\d+)\) exceeds the maximum \((\d+)\)")),
    ("google", re.compile(r"exceeds the maximum number of tokens")),
    ("xai", re.compile(r"maximum prompt length is (\d+)")),
    ("mistral", re.compile(r"Input token count")),
]


def detect_overflow_from_error(error_msg: str) -> OverflowResult:
    """
    从错误消息检测 context overflow。
    对应 pi-agent 的 packages/ai/src/utils/overflow.ts。
    """
    for provider, pattern in OVERFLOW_PATTERNS:
        match = pattern.search(error_msg)
        if match:
            groups = match.groups()
            input_tokens = int(groups[0]) if len(groups) > 0 and groups[0].isdigit() else 0
            max_tokens = int(groups[1]) if len(groups) > 1 and groups[1].isdigit() else 0
            return OverflowResult(
                is_overflow=True,
                provider=provider,
                detail=match.group(0),
                input_tokens=input_tokens,
                max_tokens=max_tokens,
            )
    return OverflowResult(is_overflow=False)


def detect_silent_overflow(usage_input: int, context_window: int) -> OverflowResult:
    """
    静默溢出检测：部分 provider 不报错但实际溢出。
    通过 usage.input > contextWindow 检测。
    """
    if usage_input > context_window:
        return OverflowResult(
            is_overflow=True,
            provider="unknown",
            detail=f"Silent overflow: usage {usage_input} > window {context_window}",
            input_tokens=usage_input,
            max_tokens=context_window,
        )
    return OverflowResult(is_overflow=False)


# ── 重试延迟提取 ──────────────────────────────────────────────────

RETRY_PATTERNS = [
    re.compile(r"Please retry in (\d+\.?\d*)s"),
    re.compile(r"retryDelay.*?(\d+\.?\d*)s"),
    re.compile(r"try again in (\d+\.?\d*)\s*seconds?"),
    re.compile(r"rate limit.*?(\d+\.?\d*)\s*seconds?"),
]


def extract_retry_delay(
    error_msg: str,
    headers: dict[str, str] | None = None,
    max_delay: float = 60.0,
) -> float | None:
    """
    从错误消息和 HTTP 头提取重试延迟。
    对应 pi-agent 的 retryDelay 提取逻辑。
    """
    # 1. 检查 HTTP 头
    if headers:
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
                return min(delay, max_delay)
            except ValueError:
                pass

        # x-ratelimit-reset（Unix timestamp）
        reset = headers.get("x-ratelimit-reset")
        if reset:
            try:
                import time
                delay = float(reset) - time.time()
                if delay > 0:
                    return min(delay, max_delay)
            except ValueError:
                pass

    # 2. 从错误消息提取
    for pattern in RETRY_PATTERNS:
        match = pattern.search(error_msg)
        if match:
            delay = float(match.group(1))
            return min(delay, max_delay)

    return None


# ── HTTP 状态码检测 ───────────────────────────────────────────────

def is_overflow_status(status_code: int, body: str) -> bool:
    """
    通过 HTTP 状态码检测溢出。
    Cerebras/Mistral 等 provider 返回 400/413 无详细 body。
    """
    if status_code == 413:
        return True
    if status_code == 400 and (not body or len(body) < 50):
        return True  # 无 body 的 400 可能是溢出
    return False


# ── 可重试性分类 ──────────────────────────────────────────────────

def classify_error(status_code: int, error_msg: str) -> str:
    """
    分类错误的可重试性。
    对应 pi-agent 的 _isRetryableError()。
    """
    # 溢出：需要 compaction 后重试
    overflow = detect_overflow_from_error(error_msg)
    if overflow.is_overflow:
        return "overflow_retry"

    # 速率限制：指数退避重试
    if status_code == 429:
        return "rate_limit_retry"

    # 服务过载：指数退避重试
    if status_code in (500, 502, 503):
        return "server_retry"

    # 不可重试
    if status_code in (401, 403):
        return "auth_error"
    if status_code == 404:
        return "not_found"

    return "unknown"


# ── Demo ──────────────────────────────────────────────────────────

def demo_overflow_detection():
    """演示多 provider overflow 检测。"""
    print("=" * 60)
    print("Demo 1: Multi-Provider Overflow Detection")
    print("=" * 60)

    errors = [
        ("Anthropic", "prompt is too long: 250000 tokens > 200000 maximum"),
        ("OpenAI", "This model's maximum context length is 128000 tokens. However, your messages resulted in 150000 tokens."),
        ("OpenAI", "Your input exceeds the context window for this model."),
        ("Google", "The input token count (180000) exceeds the maximum (128000) allowed."),
        ("xAI", "This model's maximum prompt length is 131072 tokens."),
        ("Mistral", "Input token count exceeds the limit"),
        ("Normal", "Connection timeout after 30 seconds"),
    ]

    for label, msg in errors:
        result = detect_overflow_from_error(msg)
        status = "✓ OVERFLOW" if result.is_overflow else "  normal"
        detail = f"provider={result.provider}" if result.is_overflow else ""
        if result.input_tokens:
            detail += f" ({result.input_tokens} > {result.max_tokens})"
        print(f"\n  [{label}]")
        print(f"    msg: \"{msg[:70]}{'...' if len(msg) > 70 else ''}\"")
        print(f"    {status} {detail}")


def demo_silent_overflow():
    """演示静默溢出检测。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Silent Overflow Detection")
    print("=" * 60)

    cases = [
        (100000, 128000, "正常"),
        (130000, 128000, "静默溢出"),
        (200000, 128000, "严重溢出"),
    ]

    for usage, window, label in cases:
        result = detect_silent_overflow(usage, window)
        status = "✓ OVERFLOW" if result.is_overflow else "  normal"
        print(f"\n  [{label}] usage={usage:,} window={window:,}")
        print(f"    {status}")


def demo_retry_delay():
    """演示重试延迟提取。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Retry Delay Extraction")
    print("=" * 60)

    cases = [
        ("HTTP Header", "", {"Retry-After": "5"}),
        ("Error message", "Rate limited. Please retry in 34.074824224s", None),
        ("Error message", "Too many requests, try again in 10 seconds", None),
        ("Google style", 'retryDelay: "2.5s"', None),
        ("No delay info", "Internal server error", None),
    ]

    for label, msg, headers in cases:
        delay = extract_retry_delay(msg, headers)
        if delay is not None:
            print(f"\n  [{label}] → wait {delay:.1f}s")
        else:
            print(f"\n  [{label}] → no delay found")
        if msg:
            print(f"    msg: \"{msg}\"")
        if headers:
            print(f"    headers: {headers}")


def demo_error_classification():
    """演示错误分类。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Error Classification (可重试性)")
    print("=" * 60)

    cases = [
        (400, "prompt is too long: 250000 tokens > 200000 maximum"),
        (429, "Rate limit exceeded"),
        (503, "Service temporarily unavailable"),
        (401, "Invalid API key"),
        (200, "Normal response"),
    ]

    for code, msg in cases:
        category = classify_error(code, msg)
        print(f"\n  HTTP {code}: \"{msg[:50]}\"")
        print(f"    → {category}")


def demo_full_pipeline():
    """演示完整的溢出检测 + compaction + 重试流水线。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Full Pipeline (溢出 → compaction → 重试)")
    print("=" * 60)

    # 模拟一个 overflow 场景
    print("\n  Scenario: LLM call returns overflow error")

    error_msg = "prompt is too long: 250000 tokens > 200000 maximum"
    headers = {"Retry-After": "2"}

    # Step 1: 检测溢出
    overflow = detect_overflow_from_error(error_msg)
    print(f"\n  Step 1: Detect overflow")
    print(f"    Result: is_overflow={overflow.is_overflow}, {overflow.input_tokens} > {overflow.max_tokens}")

    # Step 2: 分类错误
    category = classify_error(400, error_msg)
    print(f"\n  Step 2: Classify error")
    print(f"    Category: {category}")

    # Step 3: 提取重试延迟
    delay = extract_retry_delay(error_msg, headers)
    print(f"\n  Step 3: Extract retry delay")
    print(f"    Delay: {delay}s (from Retry-After header)")

    # Step 4: 触发 compaction
    tokens_to_remove = overflow.input_tokens - overflow.max_tokens + 16384  # reserve
    print(f"\n  Step 4: Trigger compaction")
    print(f"    Need to remove: ~{tokens_to_remove:,} tokens")
    print(f"    Strategy: structured summary (keep recent 20000 tokens)")

    # Step 5: 重试
    print(f"\n  Step 5: Retry after compaction")
    print(f"    Wait {delay}s → re-send with compacted context")
    print(f"    If still overflow → compact more aggressively")

    # 多层重试策略表
    print(f"\n  ── Multi-layer retry strategy ──")
    print(f"    {'Layer':<20s} {'Error':<25s} {'Strategy':<30s}")
    print(f"    {'─' * 75}")
    print(f"    {'LLM Provider':<20s} {'Rate limit':<25s} {'Exponential backoff (1s base)':<30s}")
    print(f"    {'LLM Provider':<20s} {'Server overload':<25s} {'Retry up to 3 times':<30s}")
    print(f"    {'Agent Session':<20s} {'Retryable error':<25s} {'agent.continue()':<30s}")
    print(f"    {'Agent Session':<20s} {'Context overflow':<25s} {'Compact → retry':<30s}")


def main():
    print("Pi-Agent Multi-Provider Overflow Demo")
    print("Reproduces overflow detection across 5+ LLM providers\n")

    demo_overflow_detection()
    demo_silent_overflow()
    demo_retry_delay()
    demo_error_classification()
    demo_full_pipeline()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("\n  Multi-provider overflow handling:")
    print("    1. Error pattern matching (5+ providers)")
    print("    2. Silent overflow via usage stats")
    print("    3. Retry delay from headers + error messages")
    print("    4. Error classification (overflow/rate-limit/server/auth)")
    print("    5. Full pipeline: detect → classify → compact → retry")
    print("\n✓ Demo complete!")


if __name__ == "__main__":
    main()
