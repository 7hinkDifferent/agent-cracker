"""
Pi-Agent Prompt 构建器。

提供分层 prompt 组装能力，可被其他 demo（如 mini-pi）导入复用。

核心接口:
  - ToolDef: 工具定义（名称 + 描述 + 参数 schema）
  - PromptBuilder: 分层组装 system prompt
"""

from dataclasses import dataclass, field


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class ToolParam:
    name: str
    type: str
    description: str
    required: bool = True


@dataclass
class ToolDef:
    """工具定义，对应 pi-agent 的 AgentTool schema。"""
    name: str
    description: str
    parameters: list[ToolParam] = field(default_factory=list)

    def to_schema_text(self) -> str:
        """生成工具的文本描述（注入 system prompt）。"""
        lines = [f"### {self.name}", f"{self.description}", "", "Parameters:"]
        for p in self.parameters:
            req = " (required)" if p.required else " (optional)"
            lines.append(f"  - {p.name}: {p.type}{req} — {p.description}")
        return "\n".join(lines)

    def to_function_schema(self) -> dict:
        """生成 OpenAI function calling 格式的 schema。"""
        properties = {}
        required = []
        for p in self.parameters:
            properties[p.name] = {"type": p.type, "description": p.description}
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# ── 自适应指南生成 ───────────────────────────────────────────────

def generate_adaptive_guidelines(tools: list[ToolDef]) -> list[str]:
    """
    根据可用工具组合生成自适应指南。
    对应 pi-agent 的 system-prompt.ts 中的条件指南逻辑。
    """
    tool_names = {t.name for t in tools}
    guidelines = []

    has_bash = "bash" in tool_names
    has_grep = "grep" in tool_names
    has_find = "find" in tool_names
    has_read = "read" in tool_names
    has_edit = "edit" in tool_names
    has_ls = "ls" in tool_names

    # 文件搜索策略
    if has_bash and not has_grep and not has_find:
        guidelines.append("Use bash for file operations like searching, listing, and finding files.")
    elif has_bash and (has_grep or has_find or has_ls):
        guidelines.append(
            "Prefer specialized tools (grep, find, ls) over bash for file exploration. "
            "Use bash only for operations not covered by available tools."
        )

    # 编辑前先读
    if has_read and has_edit:
        guidelines.append(
            "Always use read to examine file contents before making edits. "
            "This ensures accurate SEARCH text matching."
        )

    # 编辑策略
    if has_edit:
        guidelines.append(
            "Make precise, minimal edits. Include enough context in search text "
            "to uniquely identify the location."
        )

    # Bash 安全
    if has_bash:
        guidelines.append(
            "When using bash, prefer non-destructive commands. "
            "Avoid commands that could cause irreversible damage without confirmation."
        )

    return guidelines


# ── Prompt 构建器 ────────────────────────────────────────────────

BASE_ROLE = """\
You are an expert coding assistant operating inside pi, a coding agent harness.
You help users with software engineering tasks by reading, analyzing, and modifying code.
You have access to tools that let you interact with the user's codebase and environment."""


@dataclass
class PromptBuilder:
    """
    Pi-Agent 的分层 prompt 构建器。
    对应 packages/coding-agent/src/core/system-prompt.ts。

    构建顺序：
    1. 角色定义（固定基础）
    2. 工具描述（动态，根据激活的工具）
    3. 自适应指南（动态，根据工具组合）
    4. 项目上下文（.pi/context/*.md）
    5. 元信息（时间戳、工作目录）
    """
    tools: list[ToolDef] = field(default_factory=list)
    cwd: str = "."
    project_context: str = ""
    custom_context: str = ""

    def build(self) -> str:
        """组装完整 system prompt。"""
        sections = []

        # 1. 角色定义
        sections.append(BASE_ROLE)

        # 2. 工具描述
        if self.tools:
            tool_section = ["", "## Available Tools", ""]
            for tool in self.tools:
                tool_section.append(tool.to_schema_text())
                tool_section.append("")
            sections.append("\n".join(tool_section))

        # 3. 自适应指南
        guidelines = generate_adaptive_guidelines(self.tools)
        if guidelines:
            guide_section = ["", "## Guidelines", ""]
            for i, g in enumerate(guidelines, 1):
                guide_section.append(f"{i}. {g}")
            sections.append("\n".join(guide_section))

        # 4. 项目上下文
        if self.project_context:
            sections.append(f"\n## Project Context\n\n{self.project_context}")

        # 5. 自定义上下文
        if self.custom_context:
            sections.append(f"\n## Additional Context\n\n{self.custom_context}")

        # 6. 元信息
        from datetime import datetime
        meta = (
            f"\n## Environment\n\n"
            f"- Working directory: {self.cwd}\n"
            f"- Current time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        sections.append(meta)

        return "\n".join(sections)

    def build_messages(self) -> list[dict]:
        """构建包含 system prompt 的初始消息列表。"""
        return [{"role": "system", "content": self.build()}]

    def get_tool_schemas(self) -> list[dict]:
        """获取所有工具的 function calling schema。"""
        return [t.to_function_schema() for t in self.tools]


# ── 预定义工具集 ─────────────────────────────────────────────────

TOOL_READ = ToolDef(
    name="read",
    description="Read the contents of a file",
    parameters=[
        ToolParam("path", "string", "Absolute or relative file path"),
        ToolParam("offset", "integer", "Starting line number (1-based)", required=False),
        ToolParam("limit", "integer", "Number of lines to read", required=False),
    ],
)

TOOL_EDIT = ToolDef(
    name="edit",
    description="Edit a file by replacing a search string with a replacement string",
    parameters=[
        ToolParam("path", "string", "File path to edit"),
        ToolParam("search", "string", "Exact text to find in the file"),
        ToolParam("replace", "string", "Text to replace the search string with"),
    ],
)

TOOL_BASH = ToolDef(
    name="bash",
    description="Execute a shell command and return its output",
    parameters=[
        ToolParam("command", "string", "Shell command to execute"),
        ToolParam("timeout", "integer", "Timeout in seconds", required=False),
    ],
)

TOOL_GREP = ToolDef(
    name="grep",
    description="Search for a pattern in files using regex",
    parameters=[
        ToolParam("pattern", "string", "Regex pattern to search for"),
        ToolParam("path", "string", "File or directory to search in", required=False),
        ToolParam("include", "string", "Glob pattern for files to include", required=False),
    ],
)

TOOL_FIND = ToolDef(
    name="find",
    description="Find files by name pattern",
    parameters=[
        ToolParam("pattern", "string", "Glob pattern to match file names"),
        ToolParam("path", "string", "Directory to search in", required=False),
    ],
)

TOOL_LS = ToolDef(
    name="ls",
    description="List directory contents",
    parameters=[
        ToolParam("path", "string", "Directory path to list"),
    ],
)

# 完整工具集
ALL_TOOLS = [TOOL_READ, TOOL_EDIT, TOOL_BASH, TOOL_GREP, TOOL_FIND, TOOL_LS]
BASIC_TOOLS = [TOOL_READ, TOOL_EDIT, TOOL_BASH]
