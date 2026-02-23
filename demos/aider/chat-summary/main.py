"""
Aider Chat Summary Demo

复现 Aider 的 LLM 驱动历史摘要机制：
- 二分递归压缩（split → summarize head → recurse）
- Token 预算管理（独立的摘要 token 限制）
- 后台异步执行（不阻塞用户交互）
- 摘要 prompt 策略（第一人称、保留关键标识符）

Run: uv run python main.py
"""

import asyncio
from dataclasses import dataclass, field


# ── Token 估算 ───────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """bytes/4 近似 token 估算。"""
    return (len(text.encode("utf-8")) + 3) // 4


def messages_token_count(messages: list[dict]) -> int:
    """估算消息列表的总 token 数。"""
    total = 0
    for msg in messages:
        total += estimate_tokens(msg.get("content", ""))
        total += 4  # role/separator overhead
    return total


# ── 摘要 Prompt 模板 ─────────────────────────────────────────────

SUMMARY_PROMPT = """Summarize the following conversation.
Write it as the user would, using first person ("I asked you to...", "You suggested...").
Preserve all specific details: function names, library names, file names, variable names.
Be concise but complete."""


# ── ChatSummary 核心类 ───────────────────────────────────────────

@dataclass
class SummaryResult:
    """摘要结果。"""
    original_count: int
    summarized_count: int
    original_tokens: int
    summarized_tokens: int
    depth: int  # 递归深度


class ChatSummary:
    """
    LLM 驱动的聊天历史摘要器。
    对应 aider/history.py 的 ChatSummary 类。
    """

    def __init__(
        self,
        max_tokens: int = 1024,
        summarize_fn=None,  # (messages) -> str
    ):
        self.max_tokens = max_tokens
        self.summarize_fn = summarize_fn or self._default_summarize

    def _default_summarize(self, messages: list[dict]) -> str:
        """默认摘要函数（模拟 LLM 调用）。"""
        # 提取关键信息
        topics = []
        files = set()
        functions = set()

        for msg in messages:
            content = msg.get("content", "")
            # 提取文件名
            for word in content.split():
                if "." in word and any(word.endswith(ext) for ext in
                    (".py", ".js", ".ts", ".md", ".rs", ".go")):
                    files.add(word.strip(".,;:\"'()"))
            # 提取函数名（简单启发式）
            for word in content.split():
                if "(" in word and not word.startswith("("):
                    functions.add(word.split("(")[0].strip(".,;:\"'"))

            if msg["role"] == "user":
                # 简化用户消息
                preview = content[:80].replace("\n", " ")
                topics.append(f"I asked: {preview}")
            elif msg["role"] == "assistant":
                preview = content[:60].replace("\n", " ")
                topics.append(f"You said: {preview}")

        parts = ["[Summary of previous conversation]"]
        if files:
            parts.append(f"Files discussed: {', '.join(sorted(files))}")
        if functions:
            parts.append(f"Functions mentioned: {', '.join(sorted(functions))}")
        parts.append("Key points:")
        parts.extend(f"- {t}" for t in topics[:5])  # 最多保留 5 个要点
        if len(topics) > 5:
            parts.append(f"- ... and {len(topics) - 5} more exchanges")

        return "\n".join(parts)

    def find_split_point(self, messages: list[dict], budget_tokens: int) -> int:
        """
        二分搜索找分割点：使 tail 部分不超过 budget_tokens。
        对应 aider history.py 的 find_split_point。
        """
        total = messages_token_count(messages)
        if total <= budget_tokens:
            return 0  # 不需要分割

        # 从后往前累加，找到 tail 占 budget 的分割点
        cumulative = 0
        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = estimate_tokens(messages[i].get("content", "")) + 4
            cumulative += msg_tokens
            if cumulative > budget_tokens:
                return i + 1  # tail 从 i+1 开始

        return 1  # 至少保留第一条

    def summarize_real(
        self,
        messages: list[dict],
        depth: int = 0,
    ) -> tuple[list[dict], int]:
        """
        二分递归压缩。对应 aider/history.py 的 summarize_real()。

        算法：
        1. 如果总 token ≤ max_tokens → 不需要摘要
        2. 二分：half_budget = max_tokens // 2
        3. find_split_point → head (旧) / tail (新)
        4. LLM 摘要 head → summary 消息
        5. 递归处理 [summary] + tail
        """
        total_tokens = messages_token_count(messages)

        if total_tokens <= self.max_tokens:
            return messages, depth

        # 二分
        half_budget = self.max_tokens // 2
        split = self.find_split_point(messages, half_budget)

        if split <= 0:
            split = 1  # 至少摘要一条
        if split >= len(messages):
            return messages, depth  # 无法再分割

        head = messages[:split]
        tail = messages[split:]

        # LLM 摘要 head 部分
        summary_text = self.summarize_fn(head)
        summary_msg = {"role": "user", "content": summary_text}

        # 递归处理
        combined = [summary_msg] + tail
        return self.summarize_real(combined, depth + 1)


# ── 异步后台摘要 ─────────────────────────────────────────────────

class AsyncSummarizer:
    """
    后台异步摘要执行器。
    对应 aider 的后台线程摘要（不阻塞用户交互）。
    """

    def __init__(self, summary: ChatSummary):
        self.summary = summary
        self._task: asyncio.Task | None = None
        self._result: list[dict] | None = None

    async def summarize_background(self, messages: list[dict]) -> list[dict]:
        """在后台执行摘要。"""
        await asyncio.sleep(0)  # yield to event loop
        result, depth = self.summary.summarize_real(list(messages))
        self._result = result
        return result

    def start(self, messages: list[dict]):
        """启动后台摘要任务。"""
        self._task = asyncio.ensure_future(self.summarize_background(messages))

    async def wait(self) -> list[dict] | None:
        """等待后台摘要完成。"""
        if self._task:
            return await self._task
        return self._result


# ── Demo ─────────────────────────────────────────────────────────

def make_conversation(n_turns: int) -> list[dict]:
    """生成模拟对话。"""
    messages = []
    topics = [
        ("Fix the bug in main.py where parse_args() fails", "I found the issue in parse_args(). The problem is..."),
        ("Add error handling to database.py connect()", "I'll add try/except blocks to the connect() function..."),
        ("Refactor the UserService class in services/user.py", "Let me restructure the UserService class..."),
        ("Write tests for the calculate_tax() function", "Here are the test cases for calculate_tax()..."),
        ("Update the README.md with installation steps", "I'll add the installation section to README.md..."),
        ("Optimize the search_index() query in search.py", "The search_index() function can be optimized by..."),
        ("Add logging to the payment_processor.py module", "I'll add structured logging to payment_processor.py..."),
        ("Fix the race condition in async_worker.py", "The race condition in async_worker.py occurs when..."),
    ]
    for i in range(n_turns):
        user_msg, assistant_msg = topics[i % len(topics)]
        # 加些细节让 token 更多
        messages.append({"role": "user", "content": f"Turn {i+1}: {user_msg}"})
        messages.append({"role": "assistant", "content": f"Turn {i+1}: {assistant_msg} " + "Details. " * 20})
    return messages


def demo_binary_split():
    """演示二分递归压缩。"""
    print("=" * 60)
    print("Demo 1: Binary Recursive Compression")
    print("=" * 60)

    messages = make_conversation(8)  # 16 条消息
    total_tokens = messages_token_count(messages)

    print(f"\n  Input: {len(messages)} messages, ~{total_tokens} tokens")
    print(f"  Budget: 300 tokens")

    summary = ChatSummary(max_tokens=300)

    # 手动展示分割过程
    half_budget = 300 // 2
    split = summary.find_split_point(messages, half_budget)

    print(f"\n  Binary split:")
    print(f"    half_budget: {half_budget} tokens")
    print(f"    split_point: index {split}")
    print(f"    head (old): {split} messages → will be summarized")
    print(f"    tail (new): {len(messages) - split} messages → preserved")

    # 执行完整压缩
    result, depth = summary.summarize_real(messages)

    result_tokens = messages_token_count(result)
    print(f"\n  Result: {len(result)} messages, ~{result_tokens} tokens")
    print(f"  Recursion depth: {depth}")
    print(f"  Compression: {total_tokens} → {result_tokens} tokens ({result_tokens/total_tokens*100:.0f}%)")


def demo_summary_content():
    """演示摘要内容保留策略。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Summary Content (Key Info Preservation)")
    print("=" * 60)

    messages = [
        {"role": "user", "content": "Fix the bug in parser.py where parse_config() crashes on empty input"},
        {"role": "assistant", "content": "I found the issue in parse_config(). Adding a None check before json.loads():"},
        {"role": "user", "content": "Also update the test_parser.py with a test for empty input"},
        {"role": "assistant", "content": "Added test_parse_config_empty() to test_parser.py using pytest.raises()"},
        {"role": "user", "content": "Good. Now refactor database.py to use connection pooling via sqlalchemy"},
        {"role": "assistant", "content": "Refactored database.py: replaced raw connections with sqlalchemy.create_engine() pool"},
    ]

    summary = ChatSummary(max_tokens=100)
    summary_text = summary.summarize_fn(messages)

    print(f"\n  Original: {len(messages)} messages")
    print(f"\n  Summary (first person, preserving identifiers):")
    for line in summary_text.split("\n"):
        print(f"    {line}")

    # 验证关键信息保留
    key_terms = ["parser.py", "parse_config", "test_parser.py", "database.py", "sqlalchemy"]
    preserved = [t for t in key_terms if t in summary_text]
    print(f"\n  Key terms preserved: {len(preserved)}/{len(key_terms)}")
    for t in key_terms:
        status = "✓" if t in summary_text else "✗"
        print(f"    {status} {t}")


def demo_incremental_growth():
    """演示消息增长与摘要触发。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Incremental Growth & Summary Trigger")
    print("=" * 60)

    summary = ChatSummary(max_tokens=200)
    messages = []

    print(f"\n  Budget: 200 tokens")
    print(f"  Adding messages one by one:\n")

    topics = [
        "Fix login.py authentication bug",
        "Add rate limiting to api.py",
        "Refactor models.py User class",
        "Write tests for utils.py",
        "Update deploy.sh script",
        "Add caching to search.py",
        "Fix memory leak in worker.py",
        "Optimize query in reports.py",
    ]

    for i, topic in enumerate(topics):
        messages.append({"role": "user", "content": topic})
        messages.append({"role": "assistant", "content": f"Done with {topic}. " + "x " * 15})
        tokens = messages_token_count(messages)
        over = tokens > summary.max_tokens

        if over:
            result, depth = summary.summarize_real(list(messages))
            new_tokens = messages_token_count(result)
            print(f"  [{i+1}] {len(messages):2d} msgs, ~{tokens:4d} tok → SUMMARIZE → {len(result):2d} msgs, ~{new_tokens:4d} tok (depth={depth})")
            messages = result
        else:
            print(f"  [{i+1}] {len(messages):2d} msgs, ~{tokens:4d} tok")


def demo_recursion_depth():
    """演示不同数据量的递归深度。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Recursion Depth vs Message Count")
    print("=" * 60)

    print(f"\n  Budget: 200 tokens\n")
    print(f"  {'Messages':>10s}  {'Tokens':>8s}  {'After':>8s}  {'Depth':>6s}  {'Ratio':>6s}")
    print(f"  {'─' * 10}  {'─' * 8}  {'─' * 8}  {'─' * 6}  {'─' * 6}")

    for n in [4, 8, 16, 32, 64]:
        messages = make_conversation(n)
        tokens = messages_token_count(messages)

        summary = ChatSummary(max_tokens=200)
        result, depth = summary.summarize_real(messages)
        result_tokens = messages_token_count(result)
        ratio = result_tokens / tokens if tokens > 0 else 0

        print(f"  {len(messages):>10d}  {tokens:>8d}  {result_tokens:>8d}  {depth:>6d}  {ratio:>5.0%}")


async def demo_async_background():
    """演示后台异步摘要。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Async Background Summarization")
    print("=" * 60)

    messages = make_conversation(10)
    tokens = messages_token_count(messages)

    summary = ChatSummary(max_tokens=200)
    async_summarizer = AsyncSummarizer(summary)

    print(f"\n  Input: {len(messages)} messages, ~{tokens} tokens")
    print(f"  Starting background summarization...")

    # 启动后台任务
    async_summarizer.start(list(messages))

    # 模拟用户继续交互
    print(f"  [User continues typing while summary runs in background]")
    await asyncio.sleep(0)

    # 等待结果
    result = await async_summarizer.wait()
    if result:
        result_tokens = messages_token_count(result)
        print(f"  Background summary complete: {len(result)} messages, ~{result_tokens} tokens")
    else:
        print(f"  No result (unexpected)")

    print(f"\n  Key insight: User interaction is NOT blocked during summarization")


def main():
    print("Aider Chat Summary Demo")
    print("Reproduces binary recursive compression + async execution\n")

    demo_binary_split()
    demo_summary_content()
    demo_incremental_growth()
    demo_recursion_depth()
    asyncio.run(demo_async_background())

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("""
  Binary recursive compression:
    1. Check total_tokens <= max_tokens → done
    2. half_budget = max_tokens // 2
    3. find_split_point(messages, half_budget)
    4. head (old) → LLM summarize → summary message
    5. tail (new) → preserve as-is
    6. Recurse on [summary] + tail

  Summary strategy:
    - First person ("I asked you to...")
    - Preserve function names, file names, library names
    - Use weak_model (cheap/fast) when available

  Async execution:
    - Runs in background thread
    - Does not block user interaction
""")
    print("✓ Demo complete!")


if __name__ == "__main__":
    main()
