"""
Aider Core Loop Demo

复现 Aider 的三层嵌套主循环骨架：
- 外层: Coder 切换（SwitchCoder 异常）
- 中层: REPL 交互循环（用户输入 → 处理 → 反馈）
- 内层: 反思循环（编辑 → 检查 → 自动修复，最多 3 次）

Run: uv run --with litellm python main.py
"""

import os
import sys
import litellm

# ── 配置 ────────────────────────────────────────────────────────────

MODEL = os.environ.get("LITELLM_MODEL", "openai/gpt-4o-mini")
MAX_REFLECTIONS = 3

SYSTEM_PROMPT = """\
You are an expert code editor. When the user asks for code changes, output them as SEARCH/REPLACE blocks:

filepath
<<<<<<< SEARCH
original code
=======
new code
>>>>>>> REPLACE

Only output SEARCH/REPLACE blocks for code changes. Explain briefly before the blocks."""

# ── 编辑解析与应用（极简版）────────────────────────────────────────

import re

HEAD_PAT = re.compile(r"^<{5,9} SEARCH\s*$")
DIVIDER_PAT = re.compile(r"^={5,9}\s*$")
UPDATED_PAT = re.compile(r"^>{5,9} REPLACE\s*$")


def parse_edits(response_text):
    """从 LLM 响应中提取 SEARCH/REPLACE 块。"""
    edits = []
    lines = response_text.splitlines()
    i = 0
    while i < len(lines):
        if HEAD_PAT.match(lines[i].strip()):
            # 向上查找文件名
            filename = None
            for j in range(i - 1, max(i - 4, -1), -1):
                candidate = lines[j].strip().strip("`").strip("*").strip()
                if candidate and ("." in candidate or "/" in candidate):
                    filename = candidate
                    break

            # 收集 SEARCH 内容
            i += 1
            search_lines = []
            while i < len(lines) and not DIVIDER_PAT.match(lines[i].strip()):
                search_lines.append(lines[i])
                i += 1
            i += 1  # 跳过 =======

            # 收集 REPLACE 内容
            replace_lines = []
            while i < len(lines) and not UPDATED_PAT.match(lines[i].strip()):
                replace_lines.append(lines[i])
                i += 1
            i += 1  # 跳过 >>>>>>> REPLACE

            edits.append({
                "filename": filename,
                "search": "\n".join(search_lines),
                "replace": "\n".join(replace_lines),
            })
        else:
            i += 1
    return edits


def apply_edits(edits):
    """应用编辑到文件。返回 (成功列表, 失败列表)。"""
    applied, failed = [], []
    for edit in edits:
        fname = edit["filename"]
        if not fname or not os.path.exists(fname):
            failed.append(f"File not found: {fname}")
            continue
        with open(fname) as f:
            content = f.read()
        if edit["search"] in content:
            content = content.replace(edit["search"], edit["replace"], 1)
            with open(fname, "w") as f:
                f.write(content)
            applied.append(fname)
        else:
            failed.append(
                f"SEARCH block not found in {fname}:\n{edit['search'][:100]}..."
            )
    return applied, failed


# ── 简易 lint 检查 ────────────────────────────────────────────────

def lint_check(filenames):
    """对 Python 文件做语法检查，返回错误信息或 None。"""
    errors = []
    for fname in filenames:
        if fname.endswith(".py"):
            try:
                with open(fname) as f:
                    compile(f.read(), fname, "exec")
            except SyntaxError as e:
                errors.append(f"SyntaxError in {fname}:{e.lineno}: {e.msg}")
    return "\n".join(errors) if errors else None


# ── LLM 调用 ──────────────────────────────────────────────────────

def call_llm(messages):
    """调用 LLM 并返回文本响应。"""
    response = litellm.completion(
        model=MODEL,
        messages=messages,
        temperature=0,
    )
    return response.choices[0].message.content


# ── 三层主循环 ────────────────────────────────────────────────────

class SwitchMode(Exception):
    """模拟 Aider 的 SwitchCoder 异常，用于切换模式。"""
    def __init__(self, mode):
        self.mode = mode


def run_one(user_message, messages, mode):
    """
    内层 + 处理单次交互：调用 LLM → 解析 → 应用 → 反思循环。
    对应 aider 的 run_one() + send_message()。
    """
    messages.append({"role": "user", "content": user_message})
    reflected_message = user_message
    num_reflections = 0

    while reflected_message:
        print(f"\n→ Calling LLM ({MODEL})...")
        response = call_llm(messages)
        messages.append({"role": "assistant", "content": response})

        # 显示响应
        print(f"\n{'─' * 50}")
        print(response)
        print(f"{'─' * 50}")

        # 解析并应用编辑
        edits = parse_edits(response)
        if not edits:
            print("(No edits in response)")
            break

        applied, failed = apply_edits(edits)
        if applied:
            print(f"\n✓ Applied edits to: {', '.join(applied)}")
        if failed:
            print(f"\n✗ Failed: {'; '.join(failed)}")

        # ── 反思循环入口 ──
        reflected_message = None

        # 1. 编辑失败 → 反思
        if failed:
            reflected_message = (
                "These SEARCH/REPLACE blocks failed:\n" + "\n".join(failed)
                + "\nPlease fix and retry."
            )

        # 2. lint 检查失败 → 反思
        if not reflected_message and applied:
            lint_errors = lint_check(applied)
            if lint_errors:
                reflected_message = (
                    f"Lint errors after your edit:\n{lint_errors}\nPlease fix."
                )

        if reflected_message:
            num_reflections += 1
            if num_reflections >= MAX_REFLECTIONS:
                print(f"\n⚠ Reached max reflections ({MAX_REFLECTIONS}), stopping.")
                break
            print(f"\n↻ Reflection {num_reflections}/{MAX_REFLECTIONS}: {reflected_message[:80]}...")
            messages.append({"role": "user", "content": reflected_message})


def run(mode="code"):
    """
    中层 REPL 循环：获取用户输入 → 分发处理。
    对应 aider 的 run()。
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"\nMode: {mode} | Model: {MODEL}")
    print("Commands: /mode <name>, /add <file>, /drop <file>, /quit")
    print("Type your request:\n")

    added_files = set()

    while True:
        try:
            user_input = input(f"[{mode}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            return

        if not user_input:
            continue

        # 简易命令处理（对应 aider 的 Commands 系统）
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd in ("/quit", "/exit"):
                print("Bye!")
                return
            elif cmd == "/mode":
                raise SwitchMode(arg or "code")
            elif cmd == "/add":
                if arg and os.path.exists(arg):
                    added_files.add(arg)
                    # 把文件内容加入上下文
                    with open(arg) as f:
                        content = f.read()
                    messages.append({
                        "role": "user",
                        "content": f"I've added `{arg}` to the chat:\n```\n{content}\n```"
                    })
                    messages.append({
                        "role": "assistant",
                        "content": f"Ok, I can see `{arg}`."
                    })
                    print(f"Added: {arg}")
                else:
                    print(f"File not found: {arg}")
            elif cmd == "/drop":
                added_files.discard(arg)
                print(f"Dropped: {arg}")
            else:
                print(f"Unknown command: {cmd}")
            continue

        # 正常消息 → 进入 run_one
        run_one(user_input, messages, mode)
        print()


def main():
    """
    外层循环：处理 SwitchMode 异常，重建 Coder。
    对应 aider main.py 的外层 while True。
    """
    print("=" * 50)
    print("Aider Core Loop Demo")
    print("=" * 50)
    print("\nReproduces Aider's 3-layer nested loop:")
    print("  Outer: Mode switching (SwitchCoder exception)")
    print("  Middle: REPL interaction loop")
    print("  Inner: Reflection loop (edit → check → fix)")

    mode = "code"
    while True:
        try:
            run(mode)
            break
        except SwitchMode as e:
            mode = e.mode
            print(f"\n↻ Switched to mode: {mode}")


if __name__ == "__main__":
    main()
