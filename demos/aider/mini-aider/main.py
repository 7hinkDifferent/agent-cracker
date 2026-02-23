"""
Mini-Aider — 串联 4 个 MVP 组件的最小完整 Coding Agent

组装了 Aider 的四大核心机制：
1. core-loop:      三层嵌套主循环（模式切换 / REPL / 反思）
2. prompt-assembly: ChatChunks 8 段 prompt 组装
3. search-replace:  SEARCH/REPLACE 块解析 + 两级模糊匹配应用
4. llm-response-parsing: 从 LLM 自由文本提取编辑指令

Run: uv run --with litellm python main.py [files...]
"""

import os
import sys
import re
from dataclasses import dataclass, field
from difflib import get_close_matches

import litellm

# ── 配置 ────────────────────────────────────────────────────────────

MODEL = os.environ.get("LITELLM_MODEL", "openai/gpt-4o-mini")
MAX_REFLECTIONS = 3

# ═══════════════════════════════════════════════════════════════════
# 组件 1: Prompt Assembly（ChatChunks 组装）
# ══════���════════════════════════════════════════════════════════════

MAIN_SYSTEM = """\
Act as an expert software developer.
Always use best practices when coding.
Respect and use existing conventions, libraries, etc that are already present in the code base.

You are diligent and tireless!
You NEVER leave comments like "// rest of code here" or "// existing code".
Always output the COMPLETE code in SEARCH/REPLACE blocks.

Take requests for changes to the supplied code.
If the request is ambiguous, ask questions.

Once you understand the request you MUST:
1. Think step-by-step and explain the needed changes in a few short sentences.
2. Describe each change with a *SEARCH/REPLACE block*.

All changes to files must use this *SEARCH/REPLACE block* format.
ONLY EVER RETURN CODE IN A *SEARCH/REPLACE BLOCK*!"""

SYSTEM_REMINDER = """\
# *SEARCH/REPLACE block* Rules:

Every *SEARCH/REPLACE block* must use this format:
1. The file path alone on a line, verbatim.
2. The opening fence and code language, eg: ```python
3. The start of search block: <<<<<<< SEARCH
4. A contiguous chunk of lines to search for in the existing source code
5. The dividing line: =======
6. The lines to replace into the source code
7. The end of the replace block: >>>>>>> REPLACE
8. The closing fence: ```

Every SEARCH section must EXACTLY MATCH the existing file content, character for character.
Include enough lines to uniquely identify the section to change.
Keep SEARCH/REPLACE blocks concise — break large changes into multiple blocks.
To create a new file, use an empty SEARCH section."""

EXAMPLE_MESSAGES = [
    {"role": "user", "content": "Change get_factorial() to use math.factorial"},
    {"role": "assistant", "content": """\
To make this change we need to modify `mathweb/flask/app.py`:

mathweb/flask/app.py
```python
<<<<<<< SEARCH
from flask import Flask

def get_factorial(n):
    if n == 0:
        return 1
    return n * get_factorial(n-1)
=======
import math
from flask import Flask

def get_factorial(n):
    return math.factorial(n)
>>>>>>> REPLACE
```"""},
]

FILES_CONTENT_PREFIX = "These are the *editable* files:\n\n"


@dataclass
class ChatChunks:
    system: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    done: list = field(default_factory=list)
    chat_files: list = field(default_factory=list)
    cur: list = field(default_factory=list)
    reminder: list = field(default_factory=list)

    def all_messages(self):
        return (self.system + self.examples + self.done
                + self.chat_files + self.cur + self.reminder)


def assemble_prompt(user_message, file_contents, done_messages):
    """组装完整 prompt，返回 ChatChunks。"""
    chunks = ChatChunks()

    # 1. System（含首次 reminder）
    main_sys = MAIN_SYSTEM + "\n\n" + SYSTEM_REMINDER
    chunks.system = [{"role": "system", "content": main_sys}]

    # 2. Few-shot 示例 + 分隔
    chunks.examples = list(EXAMPLE_MESSAGES) + [
        {"role": "user", "content": "I switched to a new code base."},
        {"role": "assistant", "content": "Ok."},
    ]

    # 3. 历史对话
    chunks.done = done_messages

    # 4. 可编辑文件内容
    if file_contents:
        parts = []
        for path, text in file_contents.items():
            parts.append(f"{path}\n```\n{text}\n```")
        chunks.chat_files = [
            {"role": "user", "content": FILES_CONTENT_PREFIX + "\n\n".join(parts)},
            {"role": "assistant", "content": "Ok, any changes I propose will be to those files."},
        ]

    # 5. 当前消息
    chunks.cur = [{"role": "user", "content": user_message}]

    # 6. 末尾 reminder（双重注入）
    chunks.reminder = [{"role": "system", "content": SYSTEM_REMINDER}]

    return chunks


# ═══════════════════════════════════════════════════════════════════
# 组件 2: SEARCH/REPLACE 解析（LLM Response Parsing）
# ═══════════════════════════════════════════════════════════════════

@dataclass
class EditBlock:
    filename: str
    search_text: str
    replace_text: str

HEAD_PAT = re.compile(r"^<{5,9} SEARCH>?\s*$")
DIVIDER_PAT = re.compile(r"^={5,9}\s*$")
UPDATED_PAT = re.compile(r"^>{5,9} REPLACE\s*$")


def parse_edits(response_text, valid_fnames=None):
    """从 LLM 响应中提取 SEARCH/REPLACE 块。"""
    edits = []
    lines = response_text.splitlines()
    i = 0

    while i < len(lines):
        if not HEAD_PAT.match(lines[i].strip()):
            i += 1
            continue

        # 向上查找文件名
        filename = _find_filename(lines, i, valid_fnames)
        i += 1

        # SEARCH 内容
        search_lines = []
        while i < len(lines) and not DIVIDER_PAT.match(lines[i].strip()):
            search_lines.append(lines[i])
            i += 1
        if i >= len(lines):
            break
        i += 1

        # REPLACE 内容
        replace_lines = []
        while i < len(lines) and not UPDATED_PAT.match(lines[i].strip()):
            replace_lines.append(lines[i])
            i += 1
        if i >= len(lines):
            break
        i += 1

        edits.append(EditBlock(filename, "\n".join(search_lines), "\n".join(replace_lines)))

    return edits


def _find_filename(lines, head_idx, valid_fnames=None):
    """向上 1-3 行查找文件名，支持模糊匹配。"""
    for j in range(head_idx - 1, max(head_idx - 4, -1), -1):
        candidate = lines[j].strip()
        if candidate.startswith("```"):
            continue
        candidate = candidate.strip("`").strip("*").strip("#").strip(":").strip()
        if not candidate or ("." not in candidate and "/" not in candidate):
            continue
        if valid_fnames:
            if candidate in valid_fnames:
                return candidate
            for f in valid_fnames:
                if os.path.basename(f) == os.path.basename(candidate):
                    return f
            matches = get_close_matches(candidate, valid_fnames, n=1, cutoff=0.8)
            if matches:
                return matches[0]
        return candidate
    return "<unknown>"


# ═══════════════════════════════════════════════════════════════════
# 组件 3: 编辑应用（Search/Replace + 模糊匹配）
# ═══════════════════════════════════════════════════════════════════

def apply_edit(filepath, search_text, replace_text):
    """应用单个编辑，两级匹配。返回 True/False。"""
    # 新文件（空 SEARCH）
    if not search_text.strip():
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            f.write(replace_text)
        return True

    if not os.path.exists(filepath):
        return False

    with open(filepath) as f:
        content = f.read()

    # Tier 1: 精确匹配
    if search_text in content:
        content = content.replace(search_text, replace_text, 1)
        with open(filepath, "w") as f:
            f.write(content)
        return True

    # Tier 2: 空白容忍匹配
    pos = _find_normalized(content, search_text)
    if pos:
        start, end = pos
        matched = content[start:end]
        adjusted = _reindent(replace_text, search_text, matched)
        content = content[:start] + adjusted + content[end:]
        with open(filepath, "w") as f:
            f.write(content)
        return True

    return False


def _find_normalized(content, search):
    """空白归一化后查找。"""
    s_lines = [l.rstrip() for l in search.strip().splitlines()]
    c_lines = content.splitlines()
    n = len(s_lines)
    if not n:
        return None
    for i in range(len(c_lines) - n + 1):
        if [l.rstrip() for l in c_lines[i:i + n]] == s_lines:
            start = sum(len(l) + 1 for l in c_lines[:i])
            end = sum(len(l) + 1 for l in c_lines[:i + n])
            return start, min(end, len(content))
    return None


def _reindent(replace_text, search_text, matched_text):
    """根据实际匹配位置调整缩进。"""
    def _first_indent(text):
        for line in text.splitlines():
            if line.strip():
                return len(line) - len(line.lstrip())
        return 0
    diff = _first_indent(matched_text) - _first_indent(search_text)
    if diff == 0:
        return replace_text
    result = []
    for line in replace_text.splitlines():
        if not line.strip():
            result.append(line)
        elif diff > 0:
            result.append(" " * diff + line)
        else:
            rm = min(-diff, len(line) - len(line.lstrip()))
            result.append(line[rm:])
    return "\n".join(result)


def lint_check(filenames):
    """Python 文件语法检查。"""
    errors = []
    for f in filenames:
        if f.endswith(".py"):
            try:
                with open(f) as fh:
                    compile(fh.read(), f, "exec")
            except SyntaxError as e:
                errors.append(f"SyntaxError in {f}:{e.lineno}: {e.msg}")
    return "\n".join(errors) if errors else None


# ═══════════════════════════════════════════════════════════════════
# 组件 4: 三层主循环（Core Loop）
# ═══════════════════════════════════════════════════════════════════

def call_llm(messages):
    """调用 LLM。"""
    resp = litellm.completion(model=MODEL, messages=messages, temperature=0)
    return resp.choices[0].message.content


def run_one(user_message, file_contents, done_messages):
    """
    内层：单次交互 + 反思循环。
    组装 prompt → 调用 LLM → 解析 → 应用 → 检查 → 反思。
    """
    # 组装 prompt
    chunks = assemble_prompt(user_message, file_contents, done_messages)
    messages = chunks.all_messages()

    reflected = user_message
    num_reflections = 0

    while reflected:
        print(f"\n→ Calling {MODEL}...")
        response = call_llm(messages)

        # 追加到历史
        done_messages.append({"role": "user", "content": reflected})
        done_messages.append({"role": "assistant", "content": response})

        # 显示响应
        print(f"\n{'─' * 50}")
        print(response)
        print(f"{'─' * 50}")

        # 解析编辑
        edits = parse_edits(response, valid_fnames=list(file_contents.keys()))
        if not edits:
            print("(No edits)")
            break

        # 应用编辑
        applied, failed = [], []
        for edit in edits:
            if apply_edit(edit.filename, edit.search_text, edit.replace_text):
                applied.append(edit.filename)
                print(f"  ✓ {edit.filename}")
                # 刷新内存中的文件内容
                if edit.filename in file_contents:
                    with open(edit.filename) as f:
                        file_contents[edit.filename] = f.read()
            else:
                failed.append(edit.filename)
                print(f"  ✗ {edit.filename}: SEARCH not found")

        # ── 反思 ──
        reflected = None

        if failed:
            reflected = (
                f"{len(failed)} SEARCH/REPLACE block(s) failed to match!\n"
                + "\n".join(f"- {f}" for f in failed)
                + "\nPlease check the SEARCH text matches the file exactly and retry."
            )

        if not reflected and applied:
            lint_err = lint_check(applied)
            if lint_err:
                reflected = f"Lint errors after edit:\n{lint_err}\nPlease fix."

        if reflected:
            num_reflections += 1
            if num_reflections >= MAX_REFLECTIONS:
                print(f"\n⚠ Max reflections ({MAX_REFLECTIONS}), stopping.")
                break
            print(f"\n↻ Reflection {num_reflections}/{MAX_REFLECTIONS}")
            # 重新组装 prompt（包含更新后的文件内容）
            chunks = assemble_prompt(reflected, file_contents, done_messages)
            messages = chunks.all_messages()


def run(initial_files=None):
    """中层：REPL 交互循环。"""
    file_contents = {}
    done_messages = []

    # 加载初始文件
    for f in (initial_files or []):
        if os.path.exists(f):
            with open(f) as fh:
                file_contents[f] = fh.read()
            print(f"  Added: {f}")

    print(f"\nModel: {MODEL}")
    print(f"Files: {', '.join(file_contents.keys()) or '(none)'}")
    print("Commands: /add <file>  /drop <file>  /files  /quit")
    print("─" * 50)

    while True:
        try:
            inp = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            return

        if not inp:
            continue

        # 斜杠命令
        if inp.startswith("/"):
            parts = inp.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd in ("/quit", "/exit", "/q"):
                print("Bye!")
                return
            elif cmd == "/add":
                if arg and os.path.exists(arg):
                    with open(arg) as f:
                        file_contents[arg] = f.read()
                    print(f"  Added: {arg}")
                else:
                    print(f"  File not found: {arg}")
            elif cmd == "/drop":
                if arg in file_contents:
                    del file_contents[arg]
                    print(f"  Dropped: {arg}")
                else:
                    print(f"  Not in chat: {arg}")
            elif cmd == "/files":
                for f in file_contents:
                    print(f"  {f}")
            else:
                print(f"  Unknown: {cmd}")
            continue

        # 正常消息
        run_one(inp, file_contents, done_messages)


def main():
    """外层：入口。"""
    print("╔══════════════════════════════════════════╗")
    print("║          mini-aider                      ║")
    print("║   Minimal Coding Agent (4 MVP modules)   ║")
    print("╚══════════════════════════════════════════╝")

    # 从命令行参数加载文件
    files = sys.argv[1:] if len(sys.argv) > 1 else []
    run(initial_files=files)


if __name__ == "__main__":
    main()
