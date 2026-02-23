"""
Aider LLM Response Parsing Demo

复现 Aider 从 LLM 自由文本响应中提取结构化编辑指令的机制：
- 多格式适配器模式（EditBlock / WholeFile / UnifiedDiff）
- SEARCH/REPLACE 块提取（状态机 + 正则）
- 文件名提取与模糊匹配
- 解析错误生成反思反馈

Run: python main.py
"""

import re
from dataclasses import dataclass
from difflib import get_close_matches

# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class EditBlock:
    filename: str
    search_text: str
    replace_text: str


@dataclass
class WholeFileEdit:
    filename: str
    content: str


@dataclass
class UnifiedDiffEdit:
    filename: str
    original_lines: list
    modified_lines: list


# ── 格式适配器基类（多态模式）────────────────────────────────────

class BaseParser:
    """所有格式解析器的基类，对应 Aider 的 Coder 子类多态。"""
    name = "base"

    def get_edits(self, response_text, valid_fnames=None):
        raise NotImplementedError


# ── EditBlock 格式解析器 ─────────────────────────────────────────

class EditBlockParser(BaseParser):
    """
    解析 SEARCH/REPLACE 块格式。
    对应 aider/coders/editblock_coder.py:find_original_update_blocks()
    """
    name = "editblock"

    HEAD_PAT = re.compile(r"^<{5,9} SEARCH>?\s*$")
    DIVIDER_PAT = re.compile(r"^={5,9}\s*$")
    UPDATED_PAT = re.compile(r"^>{5,9} REPLACE\s*$")

    def get_edits(self, response_text, valid_fnames=None):
        edits = []
        errors = []
        lines = response_text.splitlines()
        i = 0

        while i < len(lines):
            if not self.HEAD_PAT.match(lines[i].strip()):
                i += 1
                continue

            # ── 文件名提取（向上查找 1-3 行）──
            filename = self._find_filename(lines, i, valid_fnames)

            # ── SEARCH 内容收集 ──
            i += 1
            search_lines = []
            while i < len(lines) and not self.DIVIDER_PAT.match(lines[i].strip()):
                search_lines.append(lines[i])
                i += 1

            if i >= len(lines):
                errors.append("Expected ======= divider, but reached end of response")
                break
            i += 1  # 跳过 =======

            # ── REPLACE 内容收集 ──
            replace_lines = []
            while i < len(lines) and not self.UPDATED_PAT.match(lines[i].strip()):
                # 处理连续的 SEARCH/REPLACE 块（中间用 ======= 分隔）
                if self.DIVIDER_PAT.match(lines[i].strip()):
                    # 当前 REPLACE 结束，新 SEARCH 开始（同文件连续编辑）
                    edits.append(EditBlock(filename, "\n".join(search_lines), "\n".join(replace_lines)))
                    search_lines = replace_lines
                    replace_lines = []
                    i += 1
                    continue
                replace_lines.append(lines[i])
                i += 1

            if i >= len(lines):
                errors.append("Expected >>>>>>> REPLACE, but reached end of response")
                break
            i += 1  # 跳过 >>>>>>> REPLACE

            edits.append(EditBlock(filename, "\n".join(search_lines), "\n".join(replace_lines)))

        return edits, errors

    def _find_filename(self, lines, search_idx, valid_fnames=None):
        """
        向上查找文件名。
        对应 editblock_coder.py:find_filename() + strip_filename()
        """
        for j in range(search_idx - 1, max(search_idx - 4, -1), -1):
            candidate = lines[j].strip()
            # 跳过围栏行
            if candidate.startswith("```"):
                continue
            # 清理 markdown 格式
            candidate = candidate.strip("`").strip("*").strip("#").strip(":").strip()
            if not candidate:
                continue

            # 有效文件名特征：含 . 或 /
            if "." in candidate or "/" in candidate:
                # 如果有已知文件列表，做模糊匹配
                if valid_fnames:
                    return self._match_filename(candidate, valid_fnames)
                return candidate
        return "<unknown>"

    def _match_filename(self, candidate, valid_fnames):
        """
        文件名模糊匹配。
        对应 editblock_coder.py:find_filename() 的匹配逻辑。
        """
        # 1. 精确匹配
        if candidate in valid_fnames:
            return candidate

        # 2. basename 匹配
        for fname in valid_fnames:
            if fname.split("/")[-1] == candidate.split("/")[-1]:
                return fname

        # 3. 模糊匹配（80% 相似度）
        matches = get_close_matches(candidate, valid_fnames, n=1, cutoff=0.8)
        if matches:
            return matches[0]

        return candidate


# ── WholeFile 格式解析器 ─────────────────────────────────────────

class WholeFileParser(BaseParser):
    """
    解析整文件输出格式。
    对应 aider/coders/wholefile_coder.py:get_edits()
    """
    name = "wholefile"

    FENCE_PAT = re.compile(r"^```\w*\s*$")

    def get_edits(self, response_text, valid_fnames=None):
        edits = []
        errors = []
        lines = response_text.splitlines()
        i = 0

        while i < len(lines):
            # 查找文件名行（紧接在 ``` 之前的非空行）
            if self.FENCE_PAT.match(lines[i].strip()):
                # 向上找文件名
                filename = None
                if i > 0:
                    candidate = lines[i - 1].strip().strip("`").strip("*").strip()
                    if candidate and ("." in candidate or "/" in candidate):
                        filename = candidate

                # 收集文件内容直到闭合围栏
                i += 1
                content_lines = []
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    content_lines.append(lines[i])
                    i += 1
                i += 1  # 跳过闭合围栏

                if filename:
                    edits.append(WholeFileEdit(filename, "\n".join(content_lines)))
            else:
                i += 1

        return edits, errors


# ── UnifiedDiff 格式解析器 ───────────────────────────────────────

class UnifiedDiffParser(BaseParser):
    """
    解析 unified diff 格式。
    对应 aider/coders/udiff_coder.py:find_diffs()
    """
    name = "udiff"

    DIFF_HEADER = re.compile(r"^---\s+a/(.+)")
    DIFF_HEADER2 = re.compile(r"^\+\+\+\s+b/(.+)")
    HUNK_HEADER = re.compile(r"^@@\s+.*\s+@@")

    def get_edits(self, response_text, valid_fnames=None):
        edits = []
        errors = []
        lines = response_text.splitlines()
        i = 0

        while i < len(lines):
            m = self.DIFF_HEADER.match(lines[i])
            if not m:
                i += 1
                continue

            filename = m.group(1)
            i += 1

            # 跳过 +++ b/... 行
            if i < len(lines) and self.DIFF_HEADER2.match(lines[i]):
                i += 1

            original, modified = [], []
            while i < len(lines):
                line = lines[i]
                if self.DIFF_HEADER.match(line):
                    break  # 下一个文件的 diff
                if line.startswith("-"):
                    original.append(line[1:])
                elif line.startswith("+"):
                    modified.append(line[1:])
                elif line.startswith(" "):
                    original.append(line[1:])
                    modified.append(line[1:])
                elif self.HUNK_HEADER.match(line):
                    pass  # 跳过 hunk header
                else:
                    break
                i += 1

            edits.append(UnifiedDiffEdit(filename, original, modified))

        return edits, errors


# ── 格式注册表（工厂模式）────────────────────────────────────────

PARSERS = {
    "editblock": EditBlockParser(),
    "wholefile": WholeFileParser(),
    "udiff": UnifiedDiffParser(),
}


def parse_response(response_text, format_name="editblock", valid_fnames=None):
    """
    统一入口：选择格式解析器，解析 LLM 响应。
    对应 base_coder.py:apply_updates() → get_edits()
    """
    parser = PARSERS.get(format_name)
    if not parser:
        raise ValueError(f"Unknown format: {format_name}")
    return parser.get_edits(response_text, valid_fnames)


# ── 反思反馈生成 ─────────────────────────────────────────────────

def generate_reflection(edits, errors, file_contents):
    """
    当解析的编辑无法匹配文件时，生成反思反馈消息。
    对应 editblock_coder.py 的 apply_edits() 错误分支。
    """
    failed = []
    for edit in edits:
        if not isinstance(edit, EditBlock):
            continue
        content = file_contents.get(edit.filename, "")
        if edit.search_text and edit.search_text not in content:
            # 找到最相似的行
            similar = _find_similar_lines(edit.search_text, content)
            msg = f"SEARCH block failed in {edit.filename}:\n"
            msg += f"  Search text not found: {edit.search_text[:80]}...\n"
            if similar:
                msg += f"  Did you mean: {similar}\n"
            failed.append(msg)

    if errors:
        failed.extend(errors)

    if failed:
        return (
            f"# {len(failed)} edit(s) failed!\n\n"
            + "\n".join(failed)
            + "\n\nPlease review and retry with corrected SEARCH/REPLACE blocks."
        )
    return None


def _find_similar_lines(search_text, content):
    """在文件内容中找到与 search_text 最相似的片段。"""
    search_lines = search_text.splitlines()
    if not search_lines:
        return None
    content_lines = content.splitlines()
    first_line = search_lines[0].strip()
    for cl in content_lines:
        if get_close_matches(first_line, [cl.strip()], n=1, cutoff=0.6):
            return cl.strip()
    return None


# ── Demo ─────────────────────────────────────────────────────────

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
