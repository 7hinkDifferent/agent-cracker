"""
Aider Multi-Coder Demo

复现 Aider 的多 Coder 多态架构：
- 工厂模式创建（Coder.create() 按 edit_format 选择子类）
- 12+ 编辑格式（EditBlock/WholeFIle/Patch/Architect/Ask/Context...）
- 运行时切换（SwitchCoder 异常触发 Coder 切换）
- 多态继承（BaseCoder → 子类覆盖 get_edits/apply_edits）

Run: uv run python main.py
"""

from dataclasses import dataclass, field
from enum import Enum


# ── 编辑格式枚举 ─────────────────────────────────────────────────

class EditFormat(Enum):
    """aider 支持的编辑格式。对应 coders/__init__.py 的 13 种导出。"""
    EDITBLOCK = "editblock"           # SEARCH/REPLACE 块（默认）
    WHOLE = "whole"                   # 整文件替换
    PATCH = "patch"                   # V4A diff 格式
    ARCHITECT = "architect"           # 双模型规划 + 实现
    ASK = "ask"                       # 纯问答，无编辑
    CONTEXT = "context"               # 智能文件选择
    WHOLEFILE_FUNC = "wholefile-func" # OpenAI function calling
    UDIFF = "udiff"                   # Unified diff 格式
    DIFF = "diff"                     # Simple diff
    DIFF_FENCED = "diff-fenced"       # Fenced diff 块
    EDITBLOCK_FENCED = "editblock-fenced"  # Fenced SEARCH/REPLACE
    HELP = "help"                     # 帮助模式


# ── SwitchCoder 异常 ─────────────────────────────────────────────

class SwitchCoder(Exception):
    """运行时切换 Coder 的信号异常。
    对应 aider 的 SwitchCoder exception。
    """
    def __init__(self, edit_format: EditFormat, model: str = "", **kwargs):
        self.edit_format = edit_format
        self.model = model
        self.kwargs = kwargs
        super().__init__(f"Switch to {edit_format.value}")


# ── BaseCoder（多态基类）─────────────────────────────────────────

@dataclass
class EditResult:
    """编辑结果。"""
    file_path: str
    original: str
    modified: str
    success: bool = True
    error: str = ""


class BaseCoder:
    """
    Coder 基类。对应 aider/coders/base_coder.py。
    子类必须实现 get_edits() 和 apply_edits()。
    """

    edit_format: EditFormat = EditFormat.EDITBLOCK
    description: str = "Base coder"

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.chat_files: list[str] = []
        self.num_reflections = 0
        self.max_reflections = 3

    def get_edits(self, llm_response: str) -> list[dict]:
        """从 LLM 响应中提取编辑指令。子类必须覆盖。"""
        raise NotImplementedError

    def apply_edits(self, edits: list[dict], file_contents: dict[str, str]) -> list[EditResult]:
        """应用编辑到文件。子类必须覆盖。"""
        raise NotImplementedError

    def format_instructions(self) -> str:
        """返回给 LLM 的编辑格式说明。"""
        return f"Use {self.edit_format.value} format."

    def run_one(self, user_message: str, file_contents: dict[str, str]) -> list[EditResult]:
        """执行一轮：解析 LLM 响应 → 提取编辑 → 应用。"""
        # 模拟 LLM 响应
        mock_response = self._mock_llm(user_message, file_contents)
        edits = self.get_edits(mock_response)
        if edits:
            return self.apply_edits(edits, file_contents)
        return []

    def _mock_llm(self, user_msg: str, files: dict) -> str:
        """Mock LLM 响应（子类可覆盖提供特定格式）。"""
        return f"I'll help with: {user_msg}"

    @classmethod
    def create(cls, edit_format: EditFormat, model: str = "gpt-4o") -> "BaseCoder":
        """
        工厂方法。对应 Coder.create()。
        根据 edit_format 创建对应的 Coder 子类实例。
        """
        coder_map = {
            EditFormat.EDITBLOCK: EditBlockCoder,
            EditFormat.WHOLE: WholeFileCoder,
            EditFormat.PATCH: PatchCoder,
            EditFormat.ARCHITECT: ArchitectCoder,
            EditFormat.ASK: AskCoder,
            EditFormat.CONTEXT: ContextCoder,
            EditFormat.UDIFF: UdiffCoder,
        }
        coder_class = coder_map.get(edit_format, EditBlockCoder)
        return coder_class(model=model)


# ── 具体 Coder 实现 ──────────────────────────────────────────────

class EditBlockCoder(BaseCoder):
    """SEARCH/REPLACE 块编辑器。默认编辑格式。"""
    edit_format = EditFormat.EDITBLOCK
    description = "SEARCH/REPLACE blocks (default, precise line-level editing)"

    def get_edits(self, llm_response: str) -> list[dict]:
        edits = []
        lines = llm_response.split("\n")
        i = 0
        while i < len(lines):
            if "<<<<<<< SEARCH" in lines[i]:
                search_lines = []
                replace_lines = []
                i += 1
                in_replace = False
                while i < len(lines):
                    if "=======" in lines[i]:
                        in_replace = True
                    elif ">>>>>>> REPLACE" in lines[i]:
                        break
                    elif in_replace:
                        replace_lines.append(lines[i])
                    else:
                        search_lines.append(lines[i])
                    i += 1
                edits.append({
                    "search": "\n".join(search_lines),
                    "replace": "\n".join(replace_lines),
                })
            i += 1
        return edits

    def apply_edits(self, edits, file_contents):
        results = []
        for edit in edits:
            for path, content in file_contents.items():
                if edit["search"] in content:
                    new_content = content.replace(edit["search"], edit["replace"], 1)
                    file_contents[path] = new_content
                    results.append(EditResult(path, content, new_content))
                    break
        return results

    def _mock_llm(self, user_msg, files):
        # 生成 SEARCH/REPLACE 格式的 mock 响应
        for path, content in files.items():
            return f"""I'll fix that.

<<<<<<< SEARCH
{content.splitlines()[0]}
=======
{content.splitlines()[0].replace('Hello', 'Hi there')}
>>>>>>> REPLACE"""
        return ""


class WholeFileCoder(BaseCoder):
    """整文件替换编辑器。"""
    edit_format = EditFormat.WHOLE
    description = "Whole file replacement (for new files or major rewrites)"

    def get_edits(self, llm_response: str) -> list[dict]:
        # 提取 ``` 代码块中的整文件内容
        edits = []
        in_block = False
        block_lines = []
        filename = ""
        for line in llm_response.split("\n"):
            if line.startswith("```") and not in_block:
                in_block = True
                block_lines = []
            elif line.startswith("```") and in_block:
                in_block = False
                if block_lines:
                    edits.append({"file": filename or "unknown", "content": "\n".join(block_lines)})
            elif in_block:
                block_lines.append(line)
            elif line.strip().endswith(".py") or line.strip().endswith(".js"):
                filename = line.strip()
        return edits

    def apply_edits(self, edits, file_contents):
        results = []
        for edit in edits:
            path = edit.get("file", "")
            for fp in file_contents:
                if fp.endswith(path) or path == "unknown":
                    old = file_contents[fp]
                    file_contents[fp] = edit["content"]
                    results.append(EditResult(fp, old, edit["content"]))
                    break
        return results


class PatchCoder(BaseCoder):
    """V4A Diff 格式编辑器。"""
    edit_format = EditFormat.PATCH
    description = "V4A diff format (for complex multi-file changes)"

    def get_edits(self, llm_response: str) -> list[dict]:
        edits = []
        for line in llm_response.split("\n"):
            if line.startswith("--- ") or line.startswith("+++ "):
                edits.append({"type": "diff_header", "line": line})
            elif line.startswith("+") or line.startswith("-"):
                edits.append({"type": "diff_line", "line": line})
        return edits

    def apply_edits(self, edits, file_contents):
        return [EditResult("mock.py", "", "", True, "Patch applied (mock)")]


class ArchitectCoder(BaseCoder):
    """双模型协作编辑器。"""
    edit_format = EditFormat.ARCHITECT
    description = "Two-model collaboration (architect plans, editor implements)"

    def get_edits(self, llm_response: str) -> list[dict]:
        return [{"type": "plan", "content": llm_response}]

    def apply_edits(self, edits, file_contents):
        # 架构师只输出计划，不直接编辑
        return [EditResult("(plan)", "", edits[0]["content"], True)]


class AskCoder(BaseCoder):
    """纯问答模式，无编辑。"""
    edit_format = EditFormat.ASK
    description = "Q&A only, no file edits"

    def get_edits(self, llm_response: str) -> list[dict]:
        return []  # 不产生编辑

    def apply_edits(self, edits, file_contents):
        return []


class ContextCoder(BaseCoder):
    """智能文件选择器。"""
    edit_format = EditFormat.CONTEXT
    description = "Smart file selection (suggests files to add to chat)"

    def get_edits(self, llm_response: str) -> list[dict]:
        # 提取文件路径列表
        files = []
        for line in llm_response.split("\n"):
            stripped = line.strip()
            if stripped.endswith((".py", ".js", ".ts", ".md")):
                files.append({"type": "suggest_file", "path": stripped})
        return files

    def apply_edits(self, edits, file_contents):
        return [EditResult(e["path"], "", "", True) for e in edits]


class UdiffCoder(BaseCoder):
    """Unified diff 格式编辑器。"""
    edit_format = EditFormat.UDIFF
    description = "Unified diff format"

    def get_edits(self, llm_response: str) -> list[dict]:
        return [{"type": "udiff", "content": llm_response}]

    def apply_edits(self, edits, file_contents):
        return [EditResult("mock.py", "", "", True, "Udiff applied (mock)")]


# ── Demo ─────────────────────────────────────────────────────────

def demo_factory_pattern():
    """演示工厂模式创建 Coder。"""
    print("=" * 60)
    print("Demo 1: Factory Pattern (Coder.create)")
    print("=" * 60)

    print(f"\n  Available edit formats ({len(EditFormat)} total):\n")
    for fmt in EditFormat:
        coder = BaseCoder.create(fmt)
        print(f"    {fmt.value:25s} → {type(coder).__name__:25s} {coder.description}")


def demo_edit_formats():
    """演示不同编辑格式的行为差异。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Edit Format Behavior Differences")
    print("=" * 60)

    files = {"main.py": 'def greet():\n    return "Hello"\n'}
    user_msg = "Change Hello to Hi there"

    formats = [EditFormat.EDITBLOCK, EditFormat.ASK, EditFormat.ARCHITECT]

    for fmt in formats:
        coder = BaseCoder.create(fmt)
        print(f"\n  [{fmt.value}] {coder.description}")

        results = coder.run_one(user_msg, dict(files))  # copy
        if results:
            for r in results:
                if r.modified:
                    preview = r.modified[:60].replace("\n", "\\n")
                    print(f"    Result: {r.file_path} → \"{preview}\"")
                else:
                    print(f"    Result: {r.file_path} (no content change)")
        else:
            print(f"    Result: (no edits produced)")


def demo_editblock_parsing():
    """演示 SEARCH/REPLACE 块解析。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: EditBlock SEARCH/REPLACE Parsing")
    print("=" * 60)

    coder = EditBlockCoder()

    response = """Sure, I'll update the function.

<<<<<<< SEARCH
def greet():
    return "Hello"
=======
def greet():
    return "Hello, World!"
>>>>>>> REPLACE

<<<<<<< SEARCH
print(greet())
=======
result = greet()
print(f"Greeting: {result}")
>>>>>>> REPLACE
"""

    edits = coder.get_edits(response)
    print(f"\n  Parsed {len(edits)} edit blocks:")
    for i, edit in enumerate(edits):
        print(f"\n    Block {i+1}:")
        print(f"      SEARCH:  \"{edit['search'][:50]}\"")
        print(f"      REPLACE: \"{edit['replace'][:50]}\"")

    # Apply
    files = {"main.py": 'def greet():\n    return "Hello"\n\nprint(greet())\n'}
    results = coder.apply_edits(edits, files)
    print(f"\n  Applied {len(results)} edits:")
    for r in results:
        print(f"    {r.file_path}: success={r.success}")
    print(f"\n  Final content:")
    for line in files["main.py"].splitlines():
        print(f"    {line}")


def demo_runtime_switch():
    """演示运行时 Coder 切换（SwitchCoder 异常）。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Runtime Coder Switching (SwitchCoder)")
    print("=" * 60)

    # 模拟 aider 的三层循环中的 Coder 切换
    coder = BaseCoder.create(EditFormat.EDITBLOCK)
    switch_log = []

    commands = [
        ("Fix the bug in main.py", None),
        ("/architect", EditFormat.ARCHITECT),   # 用户命令触发切换
        ("Plan the refactoring", None),
        ("/code", EditFormat.EDITBLOCK),        # 切回代码模式
        ("Apply the changes", None),
        ("/ask", EditFormat.ASK),               # 切到问答模式
        ("Explain the algorithm", None),
    ]

    print(f"\n  Simulating session with coder switches:\n")

    for msg, switch_to in commands:
        if switch_to:
            # 模拟 SwitchCoder 异常
            try:
                raise SwitchCoder(switch_to)
            except SwitchCoder as e:
                old_type = type(coder).__name__
                coder = BaseCoder.create(e.edit_format)
                new_type = type(coder).__name__
                switch_log.append((old_type, new_type, e.edit_format.value))
                print(f"  ⟳ SWITCH: {old_type} → {new_type} (/{e.edit_format.value})")
        else:
            print(f"  ▸ [{type(coder).__name__:20s}] \"{msg}\"")

    print(f"\n  Total switches: {len(switch_log)}")
    for old, new, fmt in switch_log:
        print(f"    {old} → {new} (format: {fmt})")


def demo_polymorphism():
    """演示多态继承结构。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Polymorphic Inheritance")
    print("=" * 60)

    coders = [
        BaseCoder.create(fmt)
        for fmt in [EditFormat.EDITBLOCK, EditFormat.WHOLE, EditFormat.PATCH,
                     EditFormat.ARCHITECT, EditFormat.ASK, EditFormat.CONTEXT, EditFormat.UDIFF]
    ]

    print(f"\n  {'Class':25s} {'Format':20s} {'Produces Edits':>15s}  Description")
    print(f"  {'─' * 25} {'─' * 20} {'─' * 15}  {'─' * 30}")
    for c in coders:
        # 测试是否产生编辑
        files = {"test.py": "x = 1\n"}
        edits = c.get_edits("some response\ntest.py\n```\nx = 2\n```")
        produces = "yes" if edits else "no"
        print(f"  {type(c).__name__:25s} {c.edit_format.value:20s} {produces:>15s}  {c.description}")

    print(f"\n  All coders inherit from BaseCoder:")
    print(f"    - get_edits(response) → list[dict]  (polymorphic)")
    print(f"    - apply_edits(edits, files) → list[EditResult]  (polymorphic)")
    print(f"    - format_instructions() → str  (shared)")
    print(f"    - run_one(msg, files) → list[EditResult]  (template method)")


def main():
    print("Aider Multi-Coder Demo")
    print("Reproduces factory pattern + 12 edit format polymorphism\n")

    demo_factory_pattern()
    demo_edit_formats()
    demo_editblock_parsing()
    demo_runtime_switch()
    demo_polymorphism()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("""
  Multi-Coder architecture:
    1. Factory: Coder.create(edit_format) → specific subclass
    2. Polymorphism: get_edits() + apply_edits() overridden per format
    3. Runtime switch: SwitchCoder exception → outer loop catches → new Coder
    4. Template method: run_one() calls get_edits() → apply_edits()

  Three-layer loop integration:
    while True:                    # outer: model/format switching
      try:
        coder.run()                # middle: REPL (user → LLM → edit)
      except SwitchCoder:
        coder = Coder.create(...)  # create new coder
""")
    print("✓ Demo complete!")


if __name__ == "__main__":
    main()
