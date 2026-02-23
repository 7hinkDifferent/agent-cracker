"""
Aider Fuzzy Match Demo

复现 Aider 的多级容错匹配机制：
- 5 级逐步降级（精确 → 空白容忍 → 省略号 → 编辑距离 → 跨文件）
- 编辑距离 80% 相似度阈值
- 省略号（...）通配符展开
- SEARCH/REPLACE 块的鲁棒解析

Run: uv run python main.py
"""

import re
from dataclasses import dataclass


# ── 编辑距离（Levenshtein）────────────────────────────────────────

def levenshtein_ratio(s1: str, s2: str) -> float:
    """计算两个字符串的相似度（0.0 ~ 1.0）。"""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    rows = len(s1) + 1
    cols = len(s2) + 1
    prev = list(range(cols))

    for i in range(1, rows):
        curr = [i] + [0] * (cols - 1)
        for j in range(1, cols):
            if s1[i - 1] == s2[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev = curr

    max_len = max(len(s1), len(s2))
    return 1.0 - prev[-1] / max_len


# ── 匹配级别 ─────────────────────────────────────────────────────

SIMILARITY_THRESHOLD = 0.80  # 80% 相似度阈值


@dataclass
class MatchResult:
    """匹配结果。"""
    level: str           # 匹配级别名称
    matched: bool        # 是否匹配成功
    position: int = -1   # 匹配位置（行号）
    similarity: float = 1.0  # 相似度
    details: str = ""


# ── Level 1: 精确匹配 ────────────────────────────────────────────

def exact_match(search_text: str, file_content: str) -> MatchResult:
    """Level 1: 精确逐字匹配。"""
    pos = file_content.find(search_text)
    if pos >= 0:
        line_no = file_content[:pos].count("\n") + 1
        return MatchResult("exact", True, line_no, 1.0, "Exact character-by-character match")
    return MatchResult("exact", False)


# ── Level 2: 空白容忍匹配 ────────────────────────────────────────

def normalize_whitespace(text: str) -> str:
    """规范化空白：去除行首尾空白，统一空格。"""
    lines = text.splitlines()
    return "\n".join(line.strip() for line in lines)


def whitespace_tolerant_match(search_text: str, file_content: str) -> MatchResult:
    """Level 2: 忽略首尾空白差异。"""
    norm_search = normalize_whitespace(search_text)
    norm_file = normalize_whitespace(file_content)

    pos = norm_file.find(norm_search)
    if pos >= 0:
        line_no = norm_file[:pos].count("\n") + 1
        return MatchResult("whitespace", True, line_no, 0.99,
                          "Matched after normalizing whitespace")
    return MatchResult("whitespace", False)


# ── Level 3: 省略号展开匹配 ──────────────────────────────────────

def ellipsis_match(search_text: str, file_content: str) -> MatchResult:
    """
    Level 3: 将 `...` 行作为通配符，匹配任意中间内容。
    对应 aider editblock_coder.py 的省略号处理。
    """
    search_lines = search_text.splitlines()
    file_lines = file_content.splitlines()

    # 检查是否包含省略号行
    has_ellipsis = any(line.strip() == "..." for line in search_lines)
    if not has_ellipsis:
        return MatchResult("ellipsis", False, details="No ellipsis found in search")

    # 拆分为多个片段（以 ... 为分隔）
    segments = []
    current = []
    for line in search_lines:
        if line.strip() == "...":
            if current:
                segments.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        segments.append("\n".join(current))

    if not segments:
        return MatchResult("ellipsis", False, details="No content segments found")

    # 依次匹配每个片段
    search_from = 0
    first_pos = -1
    for seg in segments:
        remaining = "\n".join(file_lines[search_from:])
        pos = remaining.find(seg)
        if pos < 0:
            return MatchResult("ellipsis", False,
                              details=f"Segment not found: '{seg[:30]}...'")
        line_offset = remaining[:pos].count("\n")
        abs_pos = search_from + line_offset
        if first_pos < 0:
            first_pos = abs_pos
        search_from = abs_pos + seg.count("\n") + 1

    return MatchResult("ellipsis", True, first_pos + 1, 0.95,
                       f"Matched {len(segments)} segments with ellipsis gaps")


# ── Level 4: 编辑距离匹配 ────────────────────────────────────────

def fuzzy_edit_distance_match(
    search_text: str,
    file_content: str,
    threshold: float = SIMILARITY_THRESHOLD,
) -> MatchResult:
    """
    Level 4: 编辑距离模糊匹配（80% 相似度阈值）。
    对应 aider 的 editblock_coder.py fuzzy matching。
    """
    search_lines = search_text.splitlines()
    file_lines = file_content.splitlines()
    search_len = len(search_lines)

    if search_len == 0:
        return MatchResult("edit_distance", False)

    best_ratio = 0.0
    best_pos = -1

    # 滑动窗口比较
    for i in range(len(file_lines) - search_len + 1):
        window = "\n".join(file_lines[i:i + search_len])
        ratio = levenshtein_ratio(search_text, window)
        if ratio > best_ratio:
            best_ratio = ratio
            best_pos = i

    if best_ratio >= threshold:
        return MatchResult("edit_distance", True, best_pos + 1, best_ratio,
                          f"Best similarity: {best_ratio:.1%} (threshold: {threshold:.0%})")
    return MatchResult("edit_distance", False, -1, best_ratio,
                      f"Best similarity: {best_ratio:.1%} < threshold {threshold:.0%}")


# ── Level 5: 跨文件搜索 ──────────────────────────────────────────

def cross_file_match(
    search_text: str,
    target_file: str,
    all_files: dict[str, str],
) -> MatchResult:
    """
    Level 5: 如果目标文件匹配失败，在所有聊天文件中搜索。
    对应 aider 的跨文件搜索逻辑。
    """
    for path, content in all_files.items():
        if path == target_file:
            continue
        result = exact_match(search_text, content)
        if result.matched:
            return MatchResult("cross_file", True, result.position, 0.90,
                              f"Found in {path} instead of {target_file}")

        result = whitespace_tolerant_match(search_text, content)
        if result.matched:
            return MatchResult("cross_file", True, result.position, 0.85,
                              f"Found (whitespace-tolerant) in {path}")

    return MatchResult("cross_file", False, details="Not found in any chat file")


# ── 统一多级匹配 ─────────────────────────────────────────────────

def multi_level_match(
    search_text: str,
    file_content: str,
    target_file: str = "target.py",
    all_files: dict[str, str] | None = None,
) -> MatchResult:
    """
    5 级逐步降级匹配。
    每级失败后尝试下一级，直到匹配成功或全部失败。
    """
    # Level 1: 精确匹配
    result = exact_match(search_text, file_content)
    if result.matched:
        return result

    # Level 2: 空白容忍
    result = whitespace_tolerant_match(search_text, file_content)
    if result.matched:
        return result

    # Level 3: 省略号展开
    result = ellipsis_match(search_text, file_content)
    if result.matched:
        return result

    # Level 4: 编辑距离 80%
    result = fuzzy_edit_distance_match(search_text, file_content)
    if result.matched:
        return result

    # Level 5: 跨文件搜索
    if all_files:
        result = cross_file_match(search_text, target_file, all_files)
        if result.matched:
            return result

    return MatchResult("all_failed", False, details="No match at any level")


# ── Demo ─────────────────────────────────────────────────────────

def demo_exact_match():
    """演示精确匹配。"""
    print("=" * 60)
    print("Demo 1: Level 1 — Exact Match")
    print("=" * 60)

    content = 'def greet(name):\n    return f"Hello, {name}!"\n'
    search = 'def greet(name):\n    return f"Hello, {name}!"'

    result = exact_match(search, content)
    print(f"\n  File content: {repr(content[:60])}")
    print(f"  Search text:  {repr(search[:60])}")
    print(f"  Match: {result.matched} (line {result.position})")
    print(f"  Similarity: {result.similarity:.0%}")


def demo_whitespace_tolerance():
    """演示空白容忍匹配。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Level 2 — Whitespace Tolerance")
    print("=" * 60)

    content = '    def greet(name):\n        return f"Hello, {name}!"\n'
    # LLM 输出没有正确缩进
    search = 'def greet(name):\nreturn f"Hello, {name}!"'

    print(f"\n  File (indented):   {repr(content[:60])}")
    print(f"  Search (no indent): {repr(search[:60])}")

    # 精确匹配失败
    r1 = exact_match(search, content)
    print(f"\n  Exact match: {r1.matched}")

    # 空白容忍成功
    r2 = whitespace_tolerant_match(search, content)
    print(f"  Whitespace-tolerant: {r2.matched} (line {r2.position})")


def demo_ellipsis():
    """演示省略号通配符匹配。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Level 3 — Ellipsis Expansion")
    print("=" * 60)

    content = """class Calculator:
    def __init__(self):
        self.history = []
        self.mode = "basic"

    def add(self, a, b):
        result = a + b
        self.history.append(result)
        return result

    def multiply(self, a, b):
        result = a * b
        self.history.append(result)
        return result
"""

    # LLM 使用 ... 省略中间代码
    search = """class Calculator:
    def __init__(self):
...
    def multiply(self, a, b):
        result = a * b"""

    print(f"\n  Search with ellipsis:")
    for line in search.splitlines():
        marker = " ← wildcard" if line.strip() == "..." else ""
        print(f"    {line}{marker}")

    result = ellipsis_match(search, content)
    print(f"\n  Match: {result.matched}")
    print(f"  Details: {result.details}")


def demo_edit_distance():
    """演示编辑距离模糊匹配。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Level 4 — Edit Distance (80% threshold)")
    print("=" * 60)

    content = 'def calculate_total(items, tax_rate=0.1):\n    subtotal = sum(item.price for item in items)\n    return subtotal * (1 + tax_rate)\n'

    # LLM 输出有轻微偏差（变量名拼写、格式差异）
    cases = [
        ("Exact", 'def calculate_total(items, tax_rate=0.1):\n    subtotal = sum(item.price for item in items)\n    return subtotal * (1 + tax_rate)'),
        ("Minor diff", 'def calculate_total(items, tax_rate=0.10):\n    sub_total = sum(item.price for item in items)\n    return sub_total * (1 + tax_rate)'),
        ("Moderate diff", 'def calc_total(items, rate=0.1):\n    total = sum(i.price for i in items)\n    return total * (1 + rate)'),
        ("Major diff", 'def process_order(order):\n    return order.total()\n'),
    ]

    print(f"\n  File: {repr(content[:60])}...")
    print(f"\n  {'Case':15s} {'Similarity':>11s} {'Match':>6s}  {'Threshold': >10s}")
    print(f"  {'─' * 15} {'─' * 11} {'─' * 6}  {'─' * 10}")

    for label, search in cases:
        ratio = levenshtein_ratio(search, content.strip())
        matched = ratio >= SIMILARITY_THRESHOLD
        print(f"  {label:15s} {ratio:>10.1%} {'✓ YES' if matched else '✗ NO':>6s}  {SIMILARITY_THRESHOLD:>9.0%}")


def demo_cross_file():
    """演示跨文件搜索。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Level 5 — Cross-File Search")
    print("=" * 60)

    files = {
        "main.py": 'from utils import helper\n\ndef main():\n    helper()\n',
        "utils.py": 'def helper():\n    return "I help!"\n',
        "test.py": 'def test_helper():\n    assert helper() == "I help!"\n',
    }

    # LLM 以为代码在 main.py，实际在 utils.py
    search = 'def helper():\n    return "I help!"'
    target = "main.py"

    print(f"\n  Target file: {target}")
    print(f"  Search: {repr(search)}")

    # 在目标文件中找不到
    r = exact_match(search, files[target])
    print(f"\n  In {target}: {r.matched}")

    # 跨文件找到
    r = cross_file_match(search, target, files)
    print(f"  Cross-file: {r.matched}")
    print(f"  Details: {r.details}")


def demo_full_pipeline():
    """演示完整 5 级降级管线。"""
    print(f"\n{'=' * 60}")
    print("Demo 6: Full 5-Level Pipeline")
    print("=" * 60)

    content = """def process(data):
    validated = validate(data)
    result = transform(validated)
    return format_output(result)
"""

    test_cases = [
        ("Exact match", 'def process(data):\n    validated = validate(data)'),
        ("Whitespace diff", 'def process(data):\nvalidated = validate(data)'),
        ("With ellipsis", 'def process(data):\n...\n    return format_output(result)'),
        ("Typo (fuzzy)", 'def proccess(data):\n    validated = validatte(data)'),
        ("Totally wrong", 'class Foo:\n    pass'),
    ]

    all_files = {"target.py": content}

    print(f"\n  Pipeline: exact → whitespace → ellipsis → edit_distance → cross_file\n")

    for label, search in test_cases:
        result = multi_level_match(search, content, "target.py", all_files)
        status = "✓" if result.matched else "✗"
        sim = f"{result.similarity:.0%}" if result.matched else "—"
        print(f"  {status} {label:20s} → level={result.level:15s} sim={sim:>4s}  {result.details[:40]}")


def main():
    print("Aider Fuzzy Match Demo")
    print("Reproduces 5-level tolerance matching for SEARCH/REPLACE\n")

    demo_exact_match()
    demo_whitespace_tolerance()
    demo_ellipsis()
    demo_edit_distance()
    demo_cross_file()
    demo_full_pipeline()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print(f"""
  5-level matching pipeline:
    1. Exact match         — character-by-character comparison
    2. Whitespace tolerance — strip leading/trailing whitespace per line
    3. Ellipsis expansion  — treat '...' as wildcard matching any lines
    4. Edit distance 80%   — Levenshtein similarity ≥ {SIMILARITY_THRESHOLD:.0%}
    5. Cross-file search   — search all chat files if target fails

  Key insight:
    LLMs often produce slightly incorrect SEARCH blocks.
    Multi-level matching dramatically improves edit success rate.
    Combined with reflection (retry on failure), this makes
    aider's edit application very robust.
""")
    print("✓ Demo complete!")


if __name__ == "__main__":
    main()
