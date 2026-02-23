"""
Codex CLI Retry-Backoff Demo

复现 Codex CLI 的指数退避重试机制：
- 指数退避函数（200ms × 2^n）
- ±10% 随机抖动（防惊群效应）
- 错误可重试性分类（CodexErr::is_retryable）
- 完整重试循环

Run: uv run python main.py
"""

import random
import time
from dataclasses import dataclass
from enum import Enum


# ── 指数退避函数 ─────────────────────────────────────────────────

INITIAL_DELAY_MS = 200
BACKOFF_FACTOR = 2.0
MAX_RETRIES = 8


def backoff_ms(attempt: int) -> float:
    """
    计算第 N 次重试的退避时间（毫秒）。
    对应 codex-cli core/src/util.rs 的 backoff() 函数。

    公式: INITIAL_DELAY_MS × BACKOFF_FACTOR^(attempt-1) × jitter(±10%)
    """
    if attempt <= 0:
        return 0
    exp = BACKOFF_FACTOR ** (attempt - 1)
    base = INITIAL_DELAY_MS * exp
    jitter = random.uniform(0.9, 1.1)  # ±10% 抖动
    return base * jitter


def backoff_sequence(max_retries: int = MAX_RETRIES) -> list[float]:
    """生成完整退避序列（毫秒）。"""
    return [backoff_ms(i) for i in range(1, max_retries + 1)]


# ── 错误可重试性分类 ─────────────────────────────────────────────

class ErrorKind(Enum):
    """对应 codex-cli 的 CodexErr 变体。"""
    # 可重试
    STREAM_FAILED = "stream_failed"               # SSE 断连
    TIMEOUT = "timeout"                            # 进程超时
    UNEXPECTED_STATUS = "unexpected_status"         # HTTP 非 200
    CONNECTION_FAILED = "connection_failed"         # 网络连接失败
    INTERNAL_SERVER_ERROR = "internal_server_error" # 5xx 错误
    RESPONSE_STREAM_FAILED = "response_stream_failed"  # 响应流失败

    # 不可重试
    TURN_ABORTED = "turn_aborted"                  # 用户中断
    CONTEXT_WINDOW_EXCEEDED = "context_exceeded"   # 上下文溢出
    QUOTA_EXCEEDED = "quota_exceeded"              # 配额用完
    INVALID_REQUEST = "invalid_request"            # 请求格式错误
    SANDBOX_DENIED = "sandbox_denied"              # 沙箱拒绝
    REFRESH_TOKEN_FAILED = "auth_failed"           # 认证失败


# 可重试错误集合
RETRYABLE_ERRORS = {
    ErrorKind.STREAM_FAILED,
    ErrorKind.TIMEOUT,
    ErrorKind.UNEXPECTED_STATUS,
    ErrorKind.CONNECTION_FAILED,
    ErrorKind.INTERNAL_SERVER_ERROR,
    ErrorKind.RESPONSE_STREAM_FAILED,
}


@dataclass
class CodexError:
    """模拟 codex-cli 的 CodexErr。"""
    kind: ErrorKind
    message: str = ""
    http_status: int = 0

    def is_retryable(self) -> bool:
        """对应 CodexErr::is_retryable()。"""
        return self.kind in RETRYABLE_ERRORS


# ── 重试循环 ─────────────────────────────────────────────────────

@dataclass
class RetryResult:
    """重试循环的结果。"""
    success: bool
    attempts: int
    total_delay_ms: float
    last_error: CodexError | None = None
    delays: list[float] = None

    def __post_init__(self):
        if self.delays is None:
            self.delays = []


def retry_loop(
    fn,  # () -> str | raises
    max_retries: int = MAX_RETRIES,
    simulate_delay: bool = False,
) -> RetryResult:
    """
    执行带指数退避的重试循环。
    对应 codex-cli 中 LLM 调用的重试逻辑。
    """
    attempts = 0
    total_delay = 0.0
    delays = []
    last_error = None

    for attempt in range(1, max_retries + 1):
        attempts = attempt
        try:
            result = fn()
            return RetryResult(
                success=True, attempts=attempts,
                total_delay_ms=total_delay, delays=delays,
            )
        except Exception as e:
            error = CodexError(
                kind=getattr(e, "kind", ErrorKind.CONNECTION_FAILED),
                message=str(e),
                http_status=getattr(e, "http_status", 0),
            )
            last_error = error

            if not error.is_retryable():
                return RetryResult(
                    success=False, attempts=attempts,
                    total_delay_ms=total_delay,
                    last_error=error, delays=delays,
                )

            # 计算退避延迟
            delay = backoff_ms(attempt)
            delays.append(delay)
            total_delay += delay

            if simulate_delay:
                time.sleep(delay / 1000)  # 转换为秒

    return RetryResult(
        success=False, attempts=attempts,
        total_delay_ms=total_delay,
        last_error=last_error, delays=delays,
    )


# ── Demo ─────────────────────────────────────────────────────────

def demo_backoff_sequence():
    """演示指数退避序列。"""
    print("=" * 60)
    print("Demo 1: Exponential Backoff Sequence")
    print("=" * 60)

    print(f"\n  Parameters:")
    print(f"    initial_delay: {INITIAL_DELAY_MS}ms")
    print(f"    backoff_factor: {BACKOFF_FACTOR}x")
    print(f"    jitter: ±10%")
    print(f"    max_retries: {MAX_RETRIES}")

    print(f"\n  Sequence (3 runs to show jitter variance):\n")
    print(f"  {'Attempt':>8s}  {'Base':>8s}  {'Run 1':>8s}  {'Run 2':>8s}  {'Run 3':>8s}")
    print(f"  {'─' * 8}  {'─' * 8}  {'─' * 8}  {'─' * 8}  {'─' * 8}")

    for i in range(1, MAX_RETRIES + 1):
        base = INITIAL_DELAY_MS * (BACKOFF_FACTOR ** (i - 1))
        r1 = backoff_ms(i)
        r2 = backoff_ms(i)
        r3 = backoff_ms(i)
        print(f"  {i:>8d}  {base:>7.0f}ms  {r1:>7.0f}ms  {r2:>7.0f}ms  {r3:>7.0f}ms")

    total_base = sum(INITIAL_DELAY_MS * (BACKOFF_FACTOR ** (i - 1)) for i in range(1, MAX_RETRIES + 1))
    print(f"\n  Total base delay: {total_base:.0f}ms ({total_base/1000:.1f}s)")


def demo_jitter_distribution():
    """演示 ±10% 抖动分布。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Jitter Distribution (±10%)")
    print("=" * 60)

    # 对同一个 attempt 采样 100 次
    attempt = 3  # base = 800ms
    base = INITIAL_DELAY_MS * (BACKOFF_FACTOR ** (attempt - 1))
    samples = [backoff_ms(attempt) for _ in range(100)]

    min_val = min(samples)
    max_val = max(samples)
    avg_val = sum(samples) / len(samples)

    print(f"\n  Attempt {attempt} (base={base:.0f}ms), 100 samples:")
    print(f"    min:  {min_val:.1f}ms ({min_val/base*100:.1f}% of base)")
    print(f"    max:  {max_val:.1f}ms ({max_val/base*100:.1f}% of base)")
    print(f"    avg:  {avg_val:.1f}ms ({avg_val/base*100:.1f}% of base)")
    print(f"    range: {max_val - min_val:.1f}ms")

    # ASCII 直方图
    bucket_size = (max_val - min_val) / 10
    if bucket_size > 0:
        buckets = [0] * 10
        for s in samples:
            idx = min(int((s - min_val) / bucket_size), 9)
            buckets[idx] += 1

        print(f"\n  Distribution:")
        for i, count in enumerate(buckets):
            lo = min_val + i * bucket_size
            hi = lo + bucket_size
            bar = "█" * count
            print(f"    {lo:>7.0f}-{hi:>6.0f}ms │{bar}")


def demo_error_classification():
    """演示错误可重试性分类。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Error Retryability Classification")
    print("=" * 60)

    errors = [
        CodexError(ErrorKind.STREAM_FAILED, "SSE connection dropped"),
        CodexError(ErrorKind.TIMEOUT, "Command timed out after 30s"),
        CodexError(ErrorKind.UNEXPECTED_STATUS, "HTTP 429 Too Many Requests", 429),
        CodexError(ErrorKind.CONNECTION_FAILED, "Connection refused"),
        CodexError(ErrorKind.INTERNAL_SERVER_ERROR, "HTTP 500", 500),
        CodexError(ErrorKind.RESPONSE_STREAM_FAILED, "Stream interrupted"),
        CodexError(ErrorKind.TURN_ABORTED, "User pressed Ctrl+C"),
        CodexError(ErrorKind.CONTEXT_WINDOW_EXCEEDED, "128k token limit"),
        CodexError(ErrorKind.QUOTA_EXCEEDED, "Monthly quota exceeded"),
        CodexError(ErrorKind.INVALID_REQUEST, "Malformed JSON"),
        CodexError(ErrorKind.SANDBOX_DENIED, "Seatbelt: file-write denied"),
        CodexError(ErrorKind.REFRESH_TOKEN_FAILED, "OAuth token expired"),
    ]

    print(f"\n  {'Error Kind':30s} {'Retryable':>10s}  {'Message'}")
    print(f"  {'─' * 30} {'─' * 10}  {'─' * 30}")
    for err in errors:
        retryable = "✓ YES" if err.is_retryable() else "✗ NO"
        print(f"  {err.kind.value:30s} {retryable:>10s}  {err.message}")


def demo_retry_success():
    """演示成功的重试场景。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Retry Success (transient failure → recovery)")
    print("=" * 60)

    call_count = [0]

    class RetryableError(Exception):
        kind = ErrorKind.CONNECTION_FAILED

    def flaky_api():
        call_count[0] += 1
        if call_count[0] <= 3:
            raise RetryableError(f"Connection failed (attempt {call_count[0]})")
        return "Success!"

    result = retry_loop(flaky_api, max_retries=5)

    print(f"\n  Scenario: API fails 3 times, succeeds on 4th attempt")
    print(f"  Success: {result.success}")
    print(f"  Attempts: {result.attempts}")
    print(f"  Delays:")
    for i, d in enumerate(result.delays):
        print(f"    retry {i+1}: {d:.0f}ms")
    print(f"  Total wait: {result.total_delay_ms:.0f}ms")


def demo_retry_permanent_failure():
    """演示不可重试错误的立即停止。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Non-Retryable Error (immediate stop)")
    print("=" * 60)

    call_count = [0]

    class PermanentError(Exception):
        kind = ErrorKind.CONTEXT_WINDOW_EXCEEDED

    def overflow_api():
        call_count[0] += 1
        if call_count[0] == 1:
            raise PermanentError("Context window exceeded (128k)")
        return "Never reached"

    result = retry_loop(overflow_api, max_retries=5)

    print(f"\n  Scenario: Context window overflow (non-retryable)")
    print(f"  Success: {result.success}")
    print(f"  Attempts: {result.attempts} (stopped immediately)")
    print(f"  Error: {result.last_error.kind.value} — {result.last_error.message}")
    print(f"  Delays: {result.delays} (no retry delay)")


def demo_retry_exhaustion():
    """演示重试耗尽。"""
    print(f"\n{'=' * 60}")
    print("Demo 6: Retry Exhaustion (all attempts failed)")
    print("=" * 60)

    class ServerError(Exception):
        kind = ErrorKind.INTERNAL_SERVER_ERROR

    def broken_api():
        raise ServerError("HTTP 500 Internal Server Error")

    result = retry_loop(broken_api, max_retries=5)

    print(f"\n  Scenario: Server always returns 500")
    print(f"  Success: {result.success}")
    print(f"  Attempts: {result.attempts} (all {result.attempts} exhausted)")
    print(f"  Delays:")
    for i, d in enumerate(result.delays):
        print(f"    retry {i+1}: {d:.0f}ms")
    print(f"  Total wait: {result.total_delay_ms:.0f}ms ({result.total_delay_ms/1000:.1f}s)")
    print(f"  Last error: {result.last_error.kind.value}")


def main():
    print("Codex CLI Retry-Backoff Demo")
    print("Reproduces exponential backoff + error classification\n")

    demo_backoff_sequence()
    demo_jitter_distribution()
    demo_error_classification()
    demo_retry_success()
    demo_retry_permanent_failure()
    demo_retry_exhaustion()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print(f"""
  Backoff formula:
    delay = {INITIAL_DELAY_MS}ms × {BACKOFF_FACTOR}^(attempt-1) × jitter(0.9..1.1)

  Error classification:
    Retryable:     stream, timeout, connection, 5xx, unexpected status
    Non-retryable: user abort, context overflow, quota, auth, sandbox

  Retry behavior:
    - Retryable error → wait backoff → try again (up to {MAX_RETRIES} times)
    - Non-retryable error → stop immediately, no retry
    - All retries exhausted → return last error
""")
    print("✓ Demo complete!")


if __name__ == "__main__":
    main()
