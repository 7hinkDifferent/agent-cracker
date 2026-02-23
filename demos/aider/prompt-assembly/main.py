"""
Aider Prompt Assembly Demo

复现 Aider 的多层 Prompt 组装机制：
- ChatChunks: 8 个消息段按序拼接
- 模板变量动态替换（fence、platform、language）
- system_reminder 首尾双重注入
- 文件内容 + RepoMap 上下文注入

Run: python main.py
"""

from dataclasses import dataclass, field

# ── Prompt 模板（简化自 editblock_prompts.py）─────────────────────

MAIN_SYSTEM = """\
Act as an expert software developer.
Always use best practices when coding.
Respect and use existing conventions, libraries, etc that are already present in the code base.
{final_reminders}
Take requests for changes to the supplied code.
If the request is ambiguous, ask questions.

Once you understand the request you MUST:
1. Think step-by-step and explain the needed changes in a few short sentences.
2. Describe each change with a *SEARCH/REPLACE block*.

All changes to files must use this *SEARCH/REPLACE block* format.
ONLY EVER RETURN CODE IN A *SEARCH/REPLACE BLOCK*!
{shell_cmd_prompt}"""

SYSTEM_REMINDER = """\
# *SEARCH/REPLACE block* Rules:

Every *SEARCH/REPLACE block* must use this format:
1. The file path alone on a line, verbatim.
2. The opening fence: {fence}
3. The start of search block: <<<<<<< SEARCH
4. A contiguous chunk of lines to search for in the existing source code
5. The dividing line: =======
6. The lines to replace into the source code
7. The end of the replace block: >>>>>>> REPLACE
8. The closing fence: {fence}

Every SEARCH section must EXACTLY MATCH the existing source code, character for character.
Every SEARCH/REPLACE block must be fenced with {fence} ... {fence}
{shell_cmd_reminder}"""

SHELL_CMD_PROMPT = """\

If the user's request can be accomplished with shell commands, suggest them.
Platform: {platform}"""

SHELL_CMD_REMINDER = """\
If a shell command is needed, suggest it in a bash code block."""

NO_SHELL_CMD_PROMPT = """\

Do NOT suggest shell commands. Platform: {platform}"""

LAZY_PROMPT = "You are diligent and tireless! You NEVER leave comments like '// rest of code here'."
OVEREAGER_PROMPT = "Do what they ask, but no more. Do NOT add features, fix unrelated bugs, or make unsolicited improvements."

EXAMPLE_MESSAGES = [
    {
        "role": "user",
        "content": "Change get_factorial() to use math.factorial",
    },
    {
        "role": "assistant",
        "content": """\
To make this change we need to modify `mathweb/flask/app.py`:

mathweb/flask/app.py
```
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
```""",
    },
]

REPO_CONTENT_PREFIX = "Here is a map of the repository showing the most relevant files and their key definitions:\n\n"
FILES_CONTENT_PREFIX = "These are the *editable* files:\n\n"
READONLY_CONTENT_PREFIX = "These are *read-only* files for reference:\n\n"

EXAMPLE_SEPARATOR = [
    {"role": "user", "content": "I switched to a new code base. Please don't consider the above files."},
    {"role": "assistant", "content": "Ok."},
]


# ── ChatChunks 数据结构 ──────────────────────────────────────────

@dataclass
class ChatChunks:
    """
    对应 Aider 的 ChatChunks，将 prompt 分为 8 段。
    all_messages() 按固定顺序拼接为最终消息列表。
    """
    system: list = field(default_factory=list)          # 1. System prompt
    examples: list = field(default_factory=list)        # 2. Few-shot 示例
    readonly_files: list = field(default_factory=list)  # 3. 只读参考文件
    repo: list = field(default_factory=list)            # 4. RepoMap 仓库概览
    done: list = field(default_factory=list)            # 5. 历史对话
    chat_files: list = field(default_factory=list)      # 6. 可编辑文件
    cur: list = field(default_factory=list)             # 7. 当前轮消息
    reminder: list = field(default_factory=list)        # 8. 末尾提醒

    def all_messages(self):
        return (
            self.system
            + self.examples
            + self.readonly_files
            + self.repo
            + self.done
            + self.chat_files
            + self.cur
            + self.reminder
        )


# ── Prompt 组装引擎 ──────────────────────────────────────────────

@dataclass
class PromptAssembler:
    """
    简化版 Aider prompt 组装器。
    对应 base_coder.py 的 format_chat_chunks() + fmt_system_prompt()。
    """
    fence: str = "```"
    platform: str = "macOS"
    user_language: str = ""
    suggest_shell: bool = True
    model_lazy: bool = False
    model_overeager: bool = False
    use_system_role: bool = True
    examples_as_sys_msg: bool = False

    def fmt_system_prompt(self, template):
        """模板变量替换，对应 base_coder.py:fmt_system_prompt()。"""
        # 构建 final_reminders
        final_reminders = []
        if self.model_lazy:
            final_reminders.append(LAZY_PROMPT)
        if self.model_overeager:
            final_reminders.append(OVEREAGER_PROMPT)
        if self.user_language:
            final_reminders.append(f"Reply in {self.user_language}.\n")

        # Shell 命令提示
        if self.suggest_shell:
            shell_cmd_prompt = SHELL_CMD_PROMPT.format(platform=self.platform)
            shell_cmd_reminder = SHELL_CMD_REMINDER
        else:
            shell_cmd_prompt = NO_SHELL_CMD_PROMPT.format(platform=self.platform)
            shell_cmd_reminder = ""

        return template.format(
            fence=self.fence,
            final_reminders="\n\n".join(final_reminders),
            platform=self.platform,
            shell_cmd_prompt=shell_cmd_prompt,
            shell_cmd_reminder=shell_cmd_reminder,
        )

    def assemble(
        self,
        user_message,
        chat_files=None,
        readonly_files=None,
        repo_map=None,
        done_messages=None,
    ):
        """
        组装完��� prompt，返回 ChatChunks。
        对应 base_coder.py:format_chat_chunks()。
        """
        chunks = ChatChunks()

        # ── 1. System prompt ──
        main_sys = self.fmt_system_prompt(MAIN_SYSTEM)

        # 附加 example（模式 A：嵌入 system）
        if self.examples_as_sys_msg:
            main_sys += "\n\n# Example conversations:\n\n"
            for msg in EXAMPLE_MESSAGES:
                main_sys += f"## {msg['role'].upper()}: {msg['content']}\n\n"

        # 附加 system_reminder（首次）
        main_sys += "\n\n" + self.fmt_system_prompt(SYSTEM_REMINDER)

        if self.use_system_role:
            chunks.system = [{"role": "system", "content": main_sys}]
        else:
            # 不支持 system role 的模型，用 user/assistant 对模拟
            chunks.system = [
                {"role": "user", "content": main_sys},
                {"role": "assistant", "content": "Ok."},
            ]

        # ── 2. Example messages（模式 B：独立消息）──
        if not self.examples_as_sys_msg:
            for msg in EXAMPLE_MESSAGES:
                chunks.examples.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })
            chunks.examples.extend(EXAMPLE_SEPARATOR)

        # ── 3. 只读文件 ──
        if readonly_files:
            content_parts = []
            for path, text in readonly_files.items():
                content_parts.append(f"{path}\n{self.fence}\n{text}\n{self.fence}")
            chunks.readonly_files = [
                {"role": "user", "content": READONLY_CONTENT_PREFIX + "\n\n".join(content_parts)},
                {"role": "assistant", "content": "Ok, I will use these files as references."},
            ]

        # ── 4. RepoMap ──
        if repo_map:
            chunks.repo = [
                {"role": "user", "content": REPO_CONTENT_PREFIX + repo_map},
                {"role": "assistant", "content": "Ok, I won't try to edit those files without asking first."},
            ]

        # ── 5. 历史对话 ──
        chunks.done = done_messages or []

        # ── 6. 可编辑文件 ──
        if chat_files:
            content_parts = []
            for path, text in chat_files.items():
                content_parts.append(f"{path}\n{self.fence}\n{text}\n{self.fence}")
            chunks.chat_files = [
                {"role": "user", "content": FILES_CONTENT_PREFIX + "\n\n".join(content_parts)},
                {"role": "assistant", "content": "Ok, any changes I propose will be to those files."},
            ]

        # ── 7. 当前轮消息 ──
        chunks.cur = [{"role": "user", "content": user_message}]

        # ── 8. 末尾 system_reminder（第二次注入）──
        reminder_text = self.fmt_system_prompt(SYSTEM_REMINDER)
        chunks.reminder = [{"role": "system", "content": reminder_text}]

        return chunks


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
