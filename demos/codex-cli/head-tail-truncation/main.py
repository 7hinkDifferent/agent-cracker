"""
Codex CLI — 首尾保留截断 Demo

复现 codex-rs/core/src/truncate.rs 的核心逻辑：
- bytes/4 token 估算
- 首尾均分预算（head 一半 + tail 一半）
- UTF-8 字符边界对齐
- 截断标记插入（…N tokens truncated…）
- 多输出项截断（多个 tool 输出共享 token 预算）

Run: uv run python main.py
"""

# ── 常量 ──────────────────────────────────────────────────────────

APPROX_BYTES_PER_TOKEN = 4  # 与 codex-cli truncate.rs 一致


# ── Token 估算 ───────────────────────────────────────────────────

def approx_token_count(text: str) -> int:
    """估算文本的 token 数（bytes / 4，向上取整）。

    与 codex-cli truncate.rs 的 approx_token_count() 一致：
    (text.len() + 3) / 4
    """
    byte_len = len(text.encode("utf-8"))
    return (byte_len + 3) // 4


# ── 首尾保留截断 ──────────────────────────────────────────────────

def split_string(text: str, left_budget: int, right_budget: int) -> tuple[int, str, str]:
    """在字符边界上切割文本，保留首尾各 N 字节。

    返回 (被移除的字符数, 前缀, 后缀)。
    Python 字符串天然 Unicode 安全，但我们按 UTF-8 字节预算切割。

    与 codex-cli truncate.rs 的 split_string() 一致。
    """
    encoded = text.encode("utf-8")
    total_bytes = len(encoded)

    # 如果文本在预算内，不需截断
    if total_bytes <= left_budget + right_budget:
        return (0, text, "")

    # 找到左侧切割点（不超过 left_budget 字节的最大字符位置）
    byte_count = 0
    left_char_end = 0
    for i, ch in enumerate(text):
        ch_bytes = len(ch.encode("utf-8"))
        if byte_count + ch_bytes > left_budget:
            break
        byte_count += ch_bytes
        left_char_end = i + 1

    # 找到右侧切割点（最后 right_budget 字节对应的字符位置）
    byte_count = 0
    right_char_start = len(text)
    for i in range(len(text) - 1, -1, -1):
        ch_bytes = len(text[i].encode("utf-8"))
        if byte_count + ch_bytes > right_budget:
            break
        byte_count += ch_bytes
        right_char_start = i

    # 确保不重叠
    if left_char_end >= right_char_start:
        return (0, text, "")

    prefix = text[:left_char_end]
    suffix = text[right_char_start:]
    removed = len(text) - left_char_end - (len(text) - right_char_start)

    return (removed, prefix, suffix)


def truncate_text(text: str, token_budget: int) -> str:
    """按 token 预算截断文本，保留首尾各一半。

    与 codex-cli truncate.rs 的 truncate_with_byte_estimate() 一致。
    """
    estimated_tokens = approx_token_count(text)
    if estimated_tokens <= token_budget:
        return text

    # 将 token 预算转换为字节预算
    byte_budget = token_budget * APPROX_BYTES_PER_TOKEN
    left_budget = byte_budget // 2
    right_budget = byte_budget - left_budget

    removed_chars, prefix, suffix = split_string(text, left_budget, right_budget)
    if removed_chars == 0:
        return text

    # 估算被截断的 token 数
    removed_tokens = approx_token_count(text[len(prefix):len(text) - len(suffix)])

    return f"{prefix}\n…{removed_tokens} tokens truncated…\n{suffix}"


# ── 多输出项截断 ──────────────────────────────────────────────────

def truncate_outputs(outputs: list[str], total_budget: int) -> list[str]:
    """截断多个 tool 输出，共享 token 预算。

    与 codex-cli truncate.rs 的 truncate_function_output_items_with_policy() 一致。
    """
    results = []
    remaining = total_budget

    for i, text in enumerate(outputs):
        tokens = approx_token_count(text)
        if tokens <= remaining:
            results.append(text)
            remaining -= tokens
        elif remaining > 0:
            results.append(truncate_text(text, remaining))
            remaining = 0
        else:
            results.append(f"[omitted: output {i + 1}, ~{tokens} tokens]")

    return results


# ── Demo ──────────────────────────────────────────────────────────

def print_section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Codex CLI — 首尾保留截断 Demo")
    print("  复现 truncate.rs 的 bytes/4 估算 + 首尾保留截断")
    print("=" * 60)

    # ── Demo 1: Token 估算 ────────────────────────────────────────

    print_section("Demo 1: bytes/4 Token 估算")

    test_texts = [
        ("Hello, world!", "ASCII 纯文本"),
        ("你好世界", "中文（每字 3 bytes UTF-8）"),
        ("Hello 你�� World 世界", "混合文本"),
        ("a" * 100, "100 个 ASCII 字符"),
        ("你" * 100, "100 个中文字符（300 bytes）"),
    ]

    for text, desc in test_texts:
        byte_len = len(text.encode("utf-8"))
        tokens = approx_token_count(text)
        print(f"  {desc:<30s}  bytes={byte_len:<5d} tokens≈{tokens}")

    # ── Demo 2: 首尾保留截断 ──────────────────────────────────────

    print_section("Demo 2: 首尾保留截断")

    # 生成一段较长的文本
    long_text = "\n".join(f"Line {i:03d}: {'x' * 60}" for i in range(1, 51))
    total_tokens = approx_token_count(long_text)

    print(f"\n  原始文本: {len(long_text)} bytes, ~{total_tokens} tokens, 50 行")

    for budget in [200, 100, 50]:
        result = truncate_text(long_text, budget)
        lines = result.split("\n")
        print(f"\n  Budget={budget} tokens → {len(result)} bytes, {len(lines)} 行")
        # 显示前 3 行 + 截断标记 + 后 3 行
        for line in lines[:3]:
            print(f"    {line[:70]}")
        # 找截断标记
        for line in lines[3:]:
            if "truncated" in line:
                print(f"    {line}")
                break
        for line in lines[-3:]:
            if "truncated" not in line:
                print(f"    {line[:70]}")

    # ── Demo 3: UTF-8 边界安全 ───────────────────────────────────

    print_section("Demo 3: UTF-8 边界安全（多字节字符不被切断）")

    # 混合文本：ASCII + 中文 + emoji
    mixed = "Hello 你好世界 " + "🎉" * 10 + " end"
    byte_len = len(mixed.encode("utf-8"))
    tokens = approx_token_count(mixed)

    print(f"\n  原始: {mixed}")
    print(f"  bytes={byte_len}, tokens≈{tokens}")

    result = truncate_text(mixed, 5)
    print(f"  Budget=5 tokens → {result}")

    # ── Demo 4: 多输出项共享预算 ─────────────────────────────────

    print_section("Demo 4: 多输出项共享 token 预算")

    outputs = [
        "$ ls -la\ntotal 42\ndrwxr-xr-x 5 user staff 160 Jan 1 main.py\n" * 3,
        "$ cat README.md\n# My Project\n\nA great project.\n" * 5,
        "$ grep -r TODO\nsrc/main.py:12: # TODO: fix this\n" * 8,
    ]

    total_budget = 80

    print(f"\n  总预算: {total_budget} tokens")
    for i, out in enumerate(outputs):
        print(f"  输出 {i + 1}: ~{approx_token_count(out)} tokens")

    results = truncate_outputs(outputs, total_budget)

    print(f"\n  截断后:")
    for i, result in enumerate(results):
        tokens = approx_token_count(result)
        lines = result.split("\n")
        preview = lines[0][:50] + ("..." if len(lines[0]) > 50 else "")
        print(f"  输出 {i + 1}: ~{tokens} tokens — {preview}")

    print(f"\n{'=' * 60}")
    print("  Demo 完成")
    print(f"{'=' * 60}")
