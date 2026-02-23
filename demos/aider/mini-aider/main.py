"""
Mini-Aider — 串联 4 个 MVP 组件的最小完整 Coding Agent

通过 import 兄弟 MVP demo 模块实现组合：
1. prompt-assembly → ChatChunks + PromptAssembler（prompt 组装）
2. search-replace  → find_edit_blocks + apply_edit（解析与应用编辑）
3. llm-response-parsing → generate_reflection（反思反馈生成）
4. core-loop       → 本文件实现（REPL + 反思循环 + LLM 调用）

Run: uv run --with litellm python main.py [files...]
"""

import os
import sys

# ── 添加兄弟 demo 目录到 import 路径 ─────────────────────────────

_DEMO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _subdir in ("prompt-assembly", "search-replace", "llm-response-parsing"):
    _path = os.path.join(_DEMO_DIR, _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)

# ── 从兄弟 demo 导入 MVP 组件 ────────────────────────────────────

# 组件 1: Prompt Assembly
from assembler import PromptAssembler

# 组件 2: SEARCH/REPLACE 解析（来自 search-replace demo）
from parser import EditBlock, find_edit_blocks

# 组件 3: 编辑应用（来自 search-replace demo）
from replacer import apply_edit

# 组件 4: 反思反馈生成（来自 llm-response-parsing demo）
from parsers import generate_reflection

import litellm

# ── 配置 ────────────────────────────────────────────────────────────

MODEL = os.environ.get("DEMO_MODEL", "openai/gpt-4o-mini")
MAX_REFLECTIONS = 3


# ── Lint 检查 ───────────────────────────────────────────────────────

def lint_check(filenames: list[str]) -> str | None:
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


# ── Core Loop（组件 4: 三层主循环）──────────────────────────────────

def call_llm(messages: list[dict]) -> str:
    """调用 LLM。"""
    resp = litellm.completion(model=MODEL, messages=messages, temperature=0)
    return resp.choices[0].message.content


def run_one(user_message: str, file_contents: dict, done_messages: list):
    """
    内层：单次交互 + 反思循环。
    组装 prompt → 调用 LLM → 解析 → 应用 → 检查 → 反思。
    """
    # ── Prompt Assembly（组件 1）──
    assembler = PromptAssembler(model_lazy=True)
    chunks = assembler.assemble(
        user_message=user_message,
        chat_files=file_contents,
        done_messages=done_messages,
    )
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

        # ── LLM Response Parsing（组件 2）──
        edits = find_edit_blocks(response)
        if not edits:
            print("(No edits)")
            break

        # ── Search/Replace Apply（组件 3）──
        applied, failed = [], []
        for edit in edits:
            if apply_edit(edit.filename, edit.search_text, edit.replace_text):
                applied.append(edit.filename)
                # 刷新内存中的文件内容
                if edit.filename in file_contents and os.path.exists(edit.filename):
                    with open(edit.filename) as f:
                        file_contents[edit.filename] = f.read()
            else:
                failed.append(edit.filename)

        # ── 反思循环 ──
        reflected = None

        if failed:
            # 使用 generate_reflection 生成详细反馈（组件 4 的反思能力）
            reflection = generate_reflection(edits, [], file_contents)
            if reflection:
                reflected = reflection
            else:
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
            chunks = assembler.assemble(
                user_message=reflected,
                chat_files=file_contents,
                done_messages=done_messages,
            )
            messages = chunks.all_messages()


def run(initial_files: list[str] | None = None):
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
    print("\nImported components:")
    print("  • prompt-assembly/assembler.py  → PromptAssembler")
    print("  • search-replace/parser.py      → find_edit_blocks")
    print("  • search-replace/replacer.py    → apply_edit")
    print("  • llm-response-parsing/parsers.py → generate_reflection")

    # 从命令行参数加载文件
    files = sys.argv[1:] if len(sys.argv) > 1 else []
    run(initial_files=files)


if __name__ == "__main__":
    main()
