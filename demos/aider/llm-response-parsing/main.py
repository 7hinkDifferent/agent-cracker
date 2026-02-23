"""
Aider LLM Response Parsing Demo

复现 Aider 从 LLM 自由文本响应中提取结构化编辑指令的机制：
- 多格式适配器模式（EditBlock / WholeFile / UnifiedDiff）
- SEARCH/REPLACE 块提取（状态机 + 正则）
- 文件名提取与模糊匹配
- 解析错误生成反思反馈

Run: python main.py
"""

from parsers import (
    EditBlock, WholeFileEdit, UnifiedDiffEdit,
    PARSERS, parse_response, generate_reflection,
)

# ── Demo 数据 ────────────────────────────────────────────────────

# 三种格式的示例 LLM 响应
SAMPLE_EDITBLOCK = '''\
I'll fix the divide-by-zero issue.

calculator.py
```python
<<<<<<< SEARCH
    def divide(self, a, b):
        return a / b
=======
    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
>>>>>>> REPLACE
```

And add a power method:

calculator.py
```python
<<<<<<< SEARCH
    def multiply(self, a, b):
        return a * b
=======
    def multiply(self, a, b):
        return a * b

    def power(self, base, exp):
        return base ** exp
>>>>>>> REPLACE
```
'''

SAMPLE_WHOLEFILE = '''\
Here's the updated file:

calculator.py
```python
class Calculator:
    def add(self, a, b):
        return a + b

    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
```
'''

SAMPLE_UDIFF = '''\
Here are the changes:

```diff
--- a/calculator.py
+++ b/calculator.py
@@ -3,2 +3,4 @@
     def divide(self, a, b):
-        return a / b
+        if b == 0:
+            raise ValueError("Cannot divide by zero")
+        return a / b
```
'''

FILE_CONTENTS = {
    "calculator.py": """\
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    def multiply(self, a, b):
        return a * b

    def divide(self, a, b):
        return a / b
""",
}


# ── Demo 函数 ────────────────────────────────────────────────────

def demo_format(name, response, format_name):
    """运行单个格式的解析 demo。"""
    print(f"\n{'=' * 60}")
    print(f"Format: {format_name} ({name})")
    print(f"{'=' * 60}")

    print(f"\n── LLM Response (truncated) ──")
    print(response[:300] + ("..." if len(response) > 300 else ""))

    edits, errors = parse_response(response, format_name, valid_fnames=list(FILE_CONTENTS.keys()))

    print(f"\n── Parsed: {len(edits)} edit(s), {len(errors)} error(s) ──\n")

    for i, edit in enumerate(edits, 1):
        if isinstance(edit, EditBlock):
            print(f"  [{i}] EditBlock")
            print(f"      File:    {edit.filename}")
            print(f"      Search:  {edit.search_text[:60]}{'...' if len(edit.search_text) > 60 else ''}")
            print(f"      Replace: {edit.replace_text[:60]}{'...' if len(edit.replace_text) > 60 else ''}")
        elif isinstance(edit, WholeFileEdit):
            print(f"  [{i}] WholeFileEdit")
            print(f"      File:    {edit.filename}")
            print(f"      Content: {len(edit.content)} chars")
        elif isinstance(edit, UnifiedDiffEdit):
            print(f"  [{i}] UnifiedDiffEdit")
            print(f"      File:    {edit.filename}")
            print(f"      Removed: {len(edit.original_lines)} lines")
            print(f"      Added:   {len(edit.modified_lines)} lines")
        print()

    for err in errors:
        print(f"  ERROR: {err}")

    return edits, errors


def demo_reflection():
    """演示解析失败时的反思反馈生成。"""
    print(f"\n{'=' * 60}")
    print("Reflection feedback (when SEARCH block doesn't match)")
    print(f"{'=' * 60}")

    # 故意制造一个不匹配的 SEARCH 块
    bad_response = '''\
calculator.py
<<<<<<< SEARCH
    def dividee(self, a, b):
        return a / b
=======
    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
>>>>>>> REPLACE
'''

    edits, errors = parse_response(bad_response, "editblock")
    reflection = generate_reflection(edits, errors, FILE_CONTENTS)

    if reflection:
        print(f"\n── Reflection message (sent back to LLM) ──\n")
        print(reflection)
    else:
        print("\n  No reflection needed (all edits matched)")


def main():
    print("Aider LLM Response Parsing Demo")
    print("Reproduces the multi-format parsing and reflection mechanism\n")

    # Demo 1: EditBlock 格式（默认）
    demo_format("SEARCH/REPLACE blocks", SAMPLE_EDITBLOCK, "editblock")

    # Demo 2: WholeFile 格式
    demo_format("Whole file replacement", SAMPLE_WHOLEFILE, "wholefile")

    # Demo 3: UnifiedDiff 格式
    demo_format("Unified diff patches", SAMPLE_UDIFF, "udiff")

    # Demo 4: 反思反馈
    demo_reflection()

    # 总结
    print(f"\n{'=' * 60}")
    print("Summary: Multi-format adapter pattern")
    print(f"{'=' * 60}")
    print(f"\n  Registered formats: {', '.join(PARSERS.keys())}")
    print("  Each format has its own parser (get_edits method)")
    print("  All share the same interface: response_text → edits + errors")
    print("  Failed matches generate reflection feedback for LLM retry")

    print("\n✓ Demo complete!")


if __name__ == "__main__":
    main()
