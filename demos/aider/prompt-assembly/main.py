"""
Aider Prompt Assembly Demo

复现 Aider 的多层 Prompt 组装机制：
- ChatChunks: 8 个消息段按序拼接
- 模板变量动态替换（fence、platform、language）
- system_reminder 首尾双重注入
- 文件内容 + RepoMap 上下文注入

Run: python main.py
"""

from assembler import ChatChunks, PromptAssembler


# ── Demo ─────────────────────────────────────────────────────────

def print_message(msg, index):
    """格式化输出单条消息。"""
    role = msg["role"].upper()
    content = msg["content"]
    # 截断长内容
    if len(content) > 200:
        content = content[:200] + f"... ({len(msg['content'])} chars total)"
    print(f"  [{index}] {role}:")
    for line in content.splitlines():
        print(f"      {line}")
    print()


def main():
    print("=" * 60)
    print("Aider Prompt Assembly Demo")
    print("=" * 60)
    print("\nReproduces Aider's ChatChunks-based prompt assembly.\n")

    # ── 模拟输入 ──
    chat_files = {
        "app.py": 'from flask import Flask\n\napp = Flask(__name__)\n\n@app.route("/")\ndef index():\n    return "Hello"\n',
    }

    readonly_files = {
        "config.py": 'DEBUG = True\nPORT = 8080\n',
    }

    repo_map = """\
app.py:
  class: -
  def: index

config.py:
  DEBUG, PORT

utils.py:
  def: format_response, validate_input"""

    done_messages = [
        {"role": "user", "content": "Add a /health endpoint"},
        {"role": "assistant", "content": "I'll add a health check endpoint.\n\napp.py\n```\n<<<<<<< SEARCH\n...\n=======\n...\n>>>>>>> REPLACE\n```"},
    ]

    user_message = "Now add input validation to the index route"

    # ── 组装 ──
    assembler = PromptAssembler(
        model_lazy=True,
        user_language="Chinese",
        suggest_shell=True,
    )

    chunks = assembler.assemble(
        user_message=user_message,
        chat_files=chat_files,
        readonly_files=readonly_files,
        repo_map=repo_map,
        done_messages=done_messages,
    )

    # ── 输出结果 ──
    messages = chunks.all_messages()

    print(f"Total messages: {len(messages)}\n")
    print("── ChatChunks breakdown ──\n")

    sections = [
        ("system", chunks.system),
        ("examples", chunks.examples),
        ("readonly_files", chunks.readonly_files),
        ("repo", chunks.repo),
        ("done", chunks.done),
        ("chat_files", chunks.chat_files),
        ("cur", chunks.cur),
        ("reminder", chunks.reminder),
    ]

    msg_index = 0
    for name, msgs in sections:
        if msgs:
            print(f"▸ {name} ({len(msgs)} messages)")
            for msg in msgs:
                print_message(msg, msg_index)
                msg_index += 1
        else:
            print(f"▸ {name} (empty)")
            print()

    # ── 统计 ──
    total_chars = sum(len(m["content"]) for m in messages)
    print("── Summary ──\n")
    print(f"  Messages:         {len(messages)}")
    print(f"  Total characters: {total_chars}")
    print(f"  System reminder:  appears 2x (in system + reminder)")
    print(f"  Fence style:      {assembler.fence}")
    print(f"  Model flags:      lazy={assembler.model_lazy}, overeager={assembler.model_overeager}")
    print(f"  Shell commands:   {'enabled' if assembler.suggest_shell else 'disabled'}")
    print(f"  User language:    {assembler.user_language or 'default'}")

    print("\n✓ Demo complete!")


if __name__ == "__main__":
    main()
