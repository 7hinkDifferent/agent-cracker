"""
Aider Context Window Demo

复现 Aider 的上下文窗口管理机制：
- Token 采样估算（小文件精确计数，大文件 ~100 行采样）
- RepoMap token 预算二分搜索约束
- 三层 RepoMap 降级（聚焦→全局→纯 PageRank）
- 消息上下文完整组装顺序
- 超限处理（ContextWindowExceededError）

Run: uv run python main.py
"""

from dataclasses import dataclass, field


# ── Token 估算（采样优化）────────────────────────────────────────

EXACT_COUNT_THRESHOLD = 200  # 字符数低于此值时精确计数


def precise_token_count(text: str) -> int:
    """精确 token 计数（模拟 tiktoken）。"""
    # 简化版：bytes/4
    return (len(text.encode("utf-8")) + 3) // 4


def sampled_token_count(text: str) -> int:
    """
    采样估算 token 数（大文件优化）。
    对应 aider base_coder.py 的 token_count()。

    策略：等间隔采样 ~100 行，按比例放大。
    """
    if len(text) < EXACT_COUNT_THRESHOLD:
        return precise_token_count(text)

    lines = text.splitlines(keepends=True)
    step = max(len(lines) // 100, 1)
    sample = "".join(lines[::step])
    sample_tokens = precise_token_count(sample)

    if len(sample) == 0:
        return 0

    ratio = len(text) / len(sample)
    return int(sample_tokens * ratio)


# ── RepoMap Token 预算 ──────────────────────────────────────────

DEFAULT_REPOMAP_TOKENS = 1024  # RepoMap 默认 token 预算


@dataclass
class RepoMapEntry:
    """RepoMap 中的一个文件条目。"""
    path: str
    definitions: list[str] = field(default_factory=list)  # 定义的符号
    references: list[str] = field(default_factory=list)    # 引用的符号
    rank: float = 0.0       # PageRank 分数
    tokens: int = 0         # 渲染后的 token 数


def render_entry(entry: RepoMapEntry) -> str:
    """渲染一个 RepoMap 条目。"""
    lines = [f"{entry.path}:"]
    for d in entry.definitions:
        lines.append(f"  {d}")
    return "\n".join(lines)


def binary_search_budget(
    entries: list[RepoMapEntry],
    token_budget: int,
) -> list[RepoMapEntry]:
    """
    二分搜索找到能塞进 token 预算的最优文件子集。
    对应 aider repomap.py 的 token 约束逻辑。
    """
    # 按 rank 降序排列
    sorted_entries = sorted(entries, key=lambda e: e.rank, reverse=True)

    # 二分搜索：找最大的 k 使得前 k 个条目的 token 总和 ≤ budget
    lo, hi = 0, len(sorted_entries)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        total = sum(e.tokens for e in sorted_entries[:mid])
        if total <= token_budget:
            lo = mid
        else:
            hi = mid - 1

    return sorted_entries[:lo]


# ── 三层 RepoMap 降级 ───────────────────────────────────────────

class RepoMapTier:
    """
    三层 RepoMap 降级策略。
    对应 aider base_coder.py 的三层 get_repo_map 调用。
    """

    def __init__(self, all_entries: list[RepoMapEntry], token_budget: int = DEFAULT_REPOMAP_TOKENS):
        self.all_entries = all_entries
        self.token_budget = token_budget

    def tier1_focused(
        self,
        chat_files: set[str],
        mentioned_idents: set[str],
    ) -> list[RepoMapEntry]:
        """
        Tier 1: 聚焦地图 — 基于聊天文件 + 提及的标识符。
        最相关的文件获得最高 PageRank 权重。
        """
        scored = []
        for entry in self.all_entries:
            rank = entry.rank

            # 聊天文件引用的符号 → 50x 加权
            if entry.path in chat_files:
                rank *= 50.0

            # 提及的标识符 → 10x 加权
            for ref in entry.references:
                if ref in mentioned_idents:
                    rank *= 10.0
                    break

            scored.append(RepoMapEntry(
                entry.path, entry.definitions, entry.references,
                rank=rank, tokens=entry.tokens,
            ))

        return binary_search_budget(scored, self.token_budget)

    def tier2_global(self) -> list[RepoMapEntry]:
        """
        Tier 2: 全局地图 — 忽略聊天文件上下文，只看依赖关系。
        """
        return binary_search_budget(self.all_entries, self.token_budget)

    def tier3_pagerank(self) -> list[RepoMapEntry]:
        """
        Tier 3: 纯 PageRank — 无提及信息，最后降级。
        """
        return binary_search_budget(self.all_entries, self.token_budget)

    def get_best(
        self,
        chat_files: set[str] | None = None,
        mentioned_idents: set[str] | None = None,
    ) -> tuple[list[RepoMapEntry], int]:
        """
        尝试三层降级，返回 (entries, tier)。
        """
        if chat_files and mentioned_idents:
            result = self.tier1_focused(chat_files, mentioned_idents)
            if result:
                return result, 1

        result = self.tier2_global()
        if result:
            return result, 2

        result = self.tier3_pagerank()
        return result, 3


# ── 消息上下文组装 ───────────────────────────────────────────────

@dataclass
class ContextConfig:
    """上下文窗口配置。"""
    max_context_tokens: int = 128000  # 模型最大 token
    repomap_tokens: int = DEFAULT_REPOMAP_TOKENS
    system_prompt: str = "You are a helpful coding assistant."
    repo_map_text: str = ""
    readonly_files: dict[str, str] = field(default_factory=dict)
    chat_files: dict[str, str] = field(default_factory=dict)
    done_messages: list[dict] = field(default_factory=list)  # 历史（可能已被摘要）
    cur_messages: list[dict] = field(default_factory=list)   # 当前轮


class ContextWindowExceededError(Exception):
    """上下文窗口超限错误。"""
    def __init__(self, total_tokens: int, max_tokens: int):
        self.total_tokens = total_tokens
        self.max_tokens = max_tokens
        super().__init__(f"Context window exceeded: {total_tokens} > {max_tokens}")


def assemble_context(config: ContextConfig) -> list[dict]:
    """
    组装完整消息上下文。
    对应 aider base_coder.py 的消息组装顺序。

    组装顺序:
    1. [system] main_system + example_messages + system_reminder
    2. [user/asst] done_messages（历史对话）
    3. [user] repo_content（RepoMap 输出）
    4. [user] read_only_files（只读文件内容）
    5. [user] files_content（聊天文件内容）
    6. [user/asst] cur_messages（当前轮对话）
    7. [system] system_reminder（末尾再次提醒）
    """
    messages = []

    # 1. System prompt
    messages.append({"role": "system", "content": config.system_prompt})

    # 2. 历史对话（已可能被 ChatSummary 压缩）
    messages.extend(config.done_messages)

    # 3. RepoMap
    if config.repo_map_text:
        messages.append({
            "role": "user",
            "content": f"# Repository map\n\n{config.repo_map_text}",
        })

    # 4. 只读文件
    for path, content in config.readonly_files.items():
        messages.append({
            "role": "user",
            "content": f"# Read-only file: {path}\n\n```\n{content}\n```",
        })

    # 5. 聊天文件（可被 LLM 编辑）
    for path, content in config.chat_files.items():
        messages.append({
            "role": "user",
            "content": f"# Editable file: {path}\n\n```\n{content}\n```",
        })

    # 6. 当前轮对话
    messages.extend(config.cur_messages)

    # 7. System reminder（末尾重复）
    messages.append({
        "role": "system",
        "content": "Remember: use the correct edit format.",
    })

    return messages


def check_context_tokens(messages: list[dict], max_tokens: int) -> int:
    """检查消息总 token 数，超限则抛异常。"""
    total = 0
    for msg in messages:
        total += sampled_token_count(msg.get("content", ""))
        total += 4  # overhead
    if total > max_tokens:
        raise ContextWindowExceededError(total, max_tokens)
    return total


# ── Demo ─────────────────────────────────────────────────────────

def demo_token_estimation():
    """演示 token 采样估算。"""
    print("=" * 60)
    print("Demo 1: Token Estimation (Sampling vs Precise)")
    print("=" * 60)

    texts = [
        ("Short (50 chars)", "x = 1\n" * 8),
        ("Medium (500 chars)", "def func():\n    return 42\n" * 20),
        ("Large (5000 chars)", "# comment line\n" * 333),
        ("Very large (50000 chars)", "data = [1, 2, 3, 4, 5]\n" * 2174),
    ]

    print(f"\n  Threshold: {EXACT_COUNT_THRESHOLD} chars (below = precise, above = sampled)\n")
    print(f"  {'Text':25s} {'Chars':>8s} {'Precise':>8s} {'Sampled':>8s} {'Diff':>6s}")
    print(f"  {'─' * 25} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 6}")

    for label, text in texts:
        chars = len(text)
        precise = precise_token_count(text)
        sampled = sampled_token_count(text)
        diff = abs(sampled - precise) / precise * 100 if precise > 0 else 0
        method = "precise" if chars < EXACT_COUNT_THRESHOLD else "sampled"
        print(f"  {label:25s} {chars:>8d} {precise:>8d} {sampled:>8d} {diff:>5.1f}%  ({method})")


def demo_repomap_budget():
    """演示 RepoMap token 预算二分搜索。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: RepoMap Token Budget (Binary Search)")
    print("=" * 60)

    entries = [
        RepoMapEntry("main.py", ["main()", "parse_args()"], ["utils.helper"], rank=0.8, tokens=120),
        RepoMapEntry("utils.py", ["helper()", "format()"], [], rank=0.5, tokens=80),
        RepoMapEntry("models.py", ["User", "Order", "Product"], ["db.connect"], rank=0.9, tokens=200),
        RepoMapEntry("api.py", ["get_users()", "create_order()"], ["models.User"], rank=0.7, tokens=150),
        RepoMapEntry("db.py", ["connect()", "query()"], [], rank=0.6, tokens=100),
        RepoMapEntry("tests.py", ["test_main()", "test_api()"], ["main.main"], rank=0.3, tokens=180),
        RepoMapEntry("config.py", ["Settings", "load_config()"], [], rank=0.4, tokens=60),
        RepoMapEntry("middleware.py", ["auth()", "logging()"], ["api.get_users"], rank=0.2, tokens=90),
    ]

    budgets = [200, 400, 600, 1024]
    total_tokens = sum(e.tokens for e in entries)

    print(f"\n  Total entries: {len(entries)}, total tokens: {total_tokens}")
    print(f"\n  {'Budget':>8s}  {'Files':>6s}  {'Tokens':>7s}  Included files (by rank)")
    print(f"  {'─' * 8}  {'─' * 6}  {'─' * 7}  {'─' * 40}")

    for budget in budgets:
        selected = binary_search_budget(entries, budget)
        used_tokens = sum(e.tokens for e in selected)
        file_list = ", ".join(e.path for e in selected)
        print(f"  {budget:>8d}  {len(selected):>6d}  {used_tokens:>7d}  {file_list}")


def demo_three_tier():
    """演示三层 RepoMap 降级。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Three-Tier RepoMap Degradation")
    print("=" * 60)

    entries = [
        RepoMapEntry("main.py", ["main()"], ["utils.helper"], rank=0.3, tokens=100),
        RepoMapEntry("utils.py", ["helper()"], [], rank=0.2, tokens=80),
        RepoMapEntry("models.py", ["User", "Order"], ["db.connect"], rank=0.5, tokens=150),
        RepoMapEntry("api.py", ["get_users()"], ["models.User"], rank=0.4, tokens=120),
        RepoMapEntry("db.py", ["connect()"], [], rank=0.1, tokens=60),
    ]

    repo_map = RepoMapTier(entries, token_budget=300)

    # Tier 1: 聚焦（聊天文件 + 提及）
    chat_files = {"main.py"}
    mentioned = {"helper", "User"}

    t1_result, _ = repo_map.tier1_focused(chat_files, mentioned), 1
    t1_result = repo_map.tier1_focused(chat_files, mentioned)
    print(f"\n  Tier 1: Focused (chat_files={chat_files}, mentioned={mentioned})")
    print(f"    PageRank weighting: chat_file=50x, mentioned_ident=10x")
    for e in t1_result:
        print(f"      {e.path:15s} rank={e.rank:>8.1f}  tokens={e.tokens}")

    # Tier 2: 全局
    t2_result = repo_map.tier2_global()
    print(f"\n  Tier 2: Global (no chat context)")
    for e in t2_result:
        print(f"      {e.path:15s} rank={e.rank:>6.2f}  tokens={e.tokens}")

    # Tier 3: 纯 PageRank
    t3_result = repo_map.tier3_pagerank()
    print(f"\n  Tier 3: Pure PageRank (fallback)")
    for e in t3_result:
        print(f"      {e.path:15s} rank={e.rank:>6.2f}  tokens={e.tokens}")

    # 自动选择最佳层
    best, tier = repo_map.get_best(chat_files, mentioned)
    print(f"\n  Auto-selected: Tier {tier} ({len(best)} files)")


def demo_context_assembly():
    """演示完整上下文组装。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Context Assembly Order")
    print("=" * 60)

    config = ContextConfig(
        max_context_tokens=4000,
        system_prompt="You are an expert Python developer. Use SEARCH/REPLACE format.",
        repo_map_text="main.py:\n  main()\n  parse_args()\nutils.py:\n  helper()",
        readonly_files={"README.md": "# My Project\nA demo project."},
        chat_files={"main.py": 'def main():\n    print("hello")\n'},
        done_messages=[
            {"role": "user", "content": "[Summary] I asked you to fix a bug."},
            {"role": "assistant", "content": "[Summary] I fixed the parse_args issue."},
        ],
        cur_messages=[
            {"role": "user", "content": "Now add error handling to main()"},
        ],
    )

    messages = assemble_context(config)

    print(f"\n  Assembly order (aider base_coder.py):\n")
    for i, msg in enumerate(messages):
        role = msg["role"]
        content = msg["content"]
        preview = content[:50].replace("\n", "\\n")
        if len(content) > 50:
            preview += "..."
        tokens = sampled_token_count(content)
        print(f"  [{i+1:2d}] {role:10s} ~{tokens:4d} tok  \"{preview}\"")

    total = check_context_tokens(messages, config.max_context_tokens)
    print(f"\n  Total: ~{total} tokens (limit: {config.max_context_tokens})")


def demo_overflow_handling():
    """演示上下文超限处理。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Context Window Overflow Handling")
    print("=" * 60)

    # 创建一个会超限的配置
    large_file = "x = 1\n" * 500  # 大文件

    config = ContextConfig(
        max_context_tokens=500,  # 很低的限制
        system_prompt="System prompt",
        chat_files={"big_file.py": large_file},
        cur_messages=[{"role": "user", "content": "Fix the bug"}],
    )

    messages = assemble_context(config)

    print(f"\n  Scenario: max_tokens=500, but file is ~{sampled_token_count(large_file)} tokens")

    try:
        check_context_tokens(messages, config.max_context_tokens)
        print(f"  Result: OK (within budget)")
    except ContextWindowExceededError as e:
        print(f"  Result: ContextWindowExceededError!")
        print(f"    total={e.total_tokens}, max={e.max_tokens}")
        print(f"\n  Aider's response to overflow:")
        print(f"    1. Suggest user to /drop files to reduce context")
        print(f"    2. Suggest user to /clear chat history")
        print(f"    3. NOT auto-truncate (user stays in control)")


def main():
    print("Aider Context Window Demo")
    print("Reproduces token sampling + RepoMap budget + 3-tier degradation\n")

    demo_token_estimation()
    demo_repomap_budget()
    demo_three_tier()
    demo_context_assembly()
    demo_overflow_handling()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("""
  Token estimation:
    - < 200 chars: precise count (bytes/4)
    - ≥ 200 chars: sample ~100 lines, extrapolate

  RepoMap budget:
    - Binary search: find max files fitting token budget
    - Files sorted by PageRank score
    - Budget independent from file content budget

  Three-tier degradation:
    Tier 1: Focused (chat_files 50x + mentioned_idents 10x weighting)
    Tier 2: Global (all files, no personalization)
    Tier 3: Pure PageRank (last resort)

  Context assembly order:
    system → done_messages → repo_map → readonly → chat_files → cur → reminder

  Overflow: ContextWindowExceededError → user /drop or /clear
""")
    print("✓ Demo complete!")


if __name__ == "__main__":
    main()
