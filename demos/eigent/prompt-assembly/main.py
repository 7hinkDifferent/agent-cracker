"""
Eigent — Prompt 组装 Demo

复现 eigent 的角色化 System Prompt 组装机制：
- 8 种 Agent 各有独立的 system prompt 模板
- XML 标签结构化（role/team_structure/capabilities 等）
- 动态变量注入（working_directory/now_str/platform 等）
- 对话历史上下文拼接

原实现: backend/app/agent/prompt.py (8 种 prompt 模板)
       backend/app/service/chat_service.py (build_conversation_context)
"""

from __future__ import annotations

import datetime
import platform
from dataclasses import dataclass
from enum import Enum
from typing import Any


# ─── Agent 类型 ───────────────────────────────────────────────

class AgentType(str, Enum):
    developer = "developer_agent"
    browser = "browser_agent"
    document = "document_agent"
    multi_modal = "multi_modal_agent"
    social_media = "social_media_agent"
    question_confirm = "question_confirm_agent"


# ─── Prompt 模板 ─────────────────────────────────────────────
# 原实现中每种 Agent 的 prompt 长达 100-200 行，这里保留骨架结构

PROMPT_TEMPLATES: dict[AgentType, str] = {
    AgentType.developer: """\
<role>
You are a Lead Software Engineer, a master-level coding assistant with a
powerful and unrestricted terminal. Your primary role is to solve any
technical task by writing and executing code, installing necessary libraries,
interacting with the operating system, and deploying applications.
</role>

<team_structure>
You collaborate with the following agents who can work in parallel:
- **Senior Research Analyst**: Gathers information from the web.
- **Documentation Specialist**: Creates and manages documents.
- **Creative Content Specialist**: Handles image, audio, and video.
</team_structure>

<operating_environment>
- **System**: {platform_system} ({platform_machine})
- **Working Directory**: `{working_directory}`. All file operations must use absolute paths.
The current date is {now_str}. For any date-related tasks, use this as the current date.
</operating_environment>

<mandatory_instructions>
- You MUST use `list_note()` to discover available notes from other agents.
- After creating any file, you MUST register it: `append_note("shared_files", "- <path>: <desc>")`
- When you complete your task, provide a comprehensive summary.
</mandatory_instructions>

<capabilities>
- **Skills System (Highest Priority Workflow)**: If a task references a skill
  with double curly braces (e.g., {{{{pdf}}}}), use the skill workflow first.
- **Unrestricted Code Execution**: Write and execute code in any language.
- **Full Terminal Control**: Root-level access to the terminal.
- **Desktop Automation**: Control desktop applications programmatically.
</capabilities>

<philosophy>
- **Bias for Action**: Don't just suggest—implement.
- **Complete the Full Task**: Finish what you start.
- **Resourcefulness**: If a tool is missing, install it.
</philosophy>""",

    AgentType.browser: """\
<role>
You are a Senior Research Analyst, responsible for conducting expert-level
web research to gather, analyze, and document information.
You must use search/browser tools to get the information you need.
</role>

<team_structure>
You collaborate with:
- **Developer Agent**: Writes and executes code.
- **Document Agent**: Creates documents and presentations.
- **Multi-Modal Agent**: Processes images and audio.
</team_structure>

<operating_environment>
- **System**: {platform_system} ({platform_machine})
- **Working Directory**: `{working_directory}`.
The current date is {now_str}.
</operating_environment>

<mandatory_instructions>
- You MUST use note-taking tools to record your findings.
- **CRITICAL URL POLICY**: You are STRICTLY FORBIDDEN from inventing URLs.
  Only use URLs from search results or user-provided.
- You MUST NOT answer from your own knowledge.
</mandatory_instructions>

<capabilities>
- Search and get information from the web using search tools.
- Use browser toolset to investigate websites.
- Use terminal tools for local operations.
</capabilities>""",

    AgentType.document: """\
<role>
You are a Documentation Specialist, responsible for creating, modifying, and
managing documents. Your expertise includes text files, office documents,
presentations, and spreadsheets.
</role>

<operating_environment>
- **System**: {platform_system} ({platform_machine})
- **Working Directory**: `{working_directory}`.
The current date is {now_str}.
</operating_environment>

<mandatory_instructions>
- Before creating any document, use `list_note()` to discover available notes.
- After creating any document, register it with `append_note("shared_files", ...)`.
- If no format specified, use HTML format.
</mandatory_instructions>

<capabilities>
- Document Reading: PDF, Word, Excel, PowerPoint, EPUB, HTML, CSV, JSON.
- Document Creation: Markdown, Word, PDF, CSV, JSON, YAML, HTML.
- PowerPoint presentations with slides, tables, and bullet points.
- Excel spreadsheet management.
</capabilities>""",

    AgentType.multi_modal: """\
<role>
You are a Creative Content Specialist, specializing in analyzing and
generating various types of media content including video, audio, and images.
</role>

<operating_environment>
- **System**: {platform_system} ({platform_machine})
- **Working Directory**: `{working_directory}`.
The current date is {now_str}.
</operating_environment>

<capabilities>
- Video & Audio Analysis: Download, transcribe, and analyze media.
- Image Analysis & Generation: Read images, take screenshots, generate with DALL-E.
</capabilities>""",

    AgentType.social_media: """\
You are a Social Media Management Assistant with comprehensive capabilities
across multiple platforms. You MUST use the `send_message_to_user` tool to
inform the user of every decision and action you take.

- **Working Directory**: `{working_directory}`.
The current date is {now_str}.

Your integrated toolkits enable you to:
1. WhatsApp Business Management
2. Twitter Account Management
3. LinkedIn Professional Networking
4. Reddit Content Analysis
5. Notion Workspace Management
6. Slack Workspace Interaction""",

    AgentType.question_confirm: """\
You are a highly capable agent. Your primary function is to analyze a user's \
request and determine the appropriate course of action. The current date is \
{now_str}. For any date-related tasks, you MUST use this as the current date.""",
}


# ─── 动态变量注入 ─────────────────────────────────────────────

@dataclass
class PromptContext:
    """Prompt 动态变量集合。

    原实现中这些变量分散在各 factory 函数和 chat_service.py 中。
    """
    working_directory: str = "/tmp/eigent/project_001"
    platform_system: str = ""
    platform_machine: str = ""
    now_str: str = ""

    def __post_init__(self):
        if not self.platform_system:
            self.platform_system = platform.system()
        if not self.platform_machine:
            self.platform_machine = platform.machine()
        if not self.now_str:
            self.now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def assemble_prompt(agent_type: AgentType, context: PromptContext) -> str:
    """组装完整的 system prompt — 模板 + 动态变量。

    原实现: 在各 factory 函数中调用 PROMPT.format(...)
    """
    template = PROMPT_TEMPLATES.get(agent_type, "You are a helpful assistant.")
    return template.format(
        working_directory=context.working_directory,
        platform_system=context.platform_system,
        platform_machine=context.platform_machine,
        now_str=context.now_str,
    )


# ─── 对话历史上下文构建 ──────────────────────────────────────

def build_conversation_context(
    conversation_history: list[dict[str, Any]],
    header: str = "=== CONVERSATION HISTORY ===",
) -> str:
    """构建对话历史上下文 — 注入到新任务中。

    原实现: chat_service.py build_conversation_context()

    设计要点:
    1. 区分 task_result 和 assistant 角色
    2. 文件列表只在最后统一列出（去重）
    3. 总长度超过 200k 字符时提示创建新项目
    """
    if not conversation_history:
        return ""

    context = f"{header}\n"
    for entry in conversation_history:
        role = entry["role"]
        content = entry["content"]

        if role == "task_result":
            context += f"Previous Task Result: {content}\n\n"
        elif role == "assistant":
            context += f"Assistant: {content}\n\n"
        elif role == "user":
            context += f"User: {content}\n\n"

    context += f"{'=' * 40}\n"
    return context


def collect_previous_task_context(
    working_directory: str,
    previous_task_content: str,
    previous_task_result: str,
) -> str:
    """收集前序任务上下文 — 注入到新任务的 prompt 中。

    原实现: chat_service.py collect_previous_task_context()
    """
    parts = ["=== CONTEXT FROM PREVIOUS TASK ===\n"]

    if previous_task_content:
        parts.append(f"Previous Task:\n{previous_task_content}\n")
    if previous_task_result:
        parts.append(f"Previous Task Result:\n{previous_task_result}\n")

    parts.append("=== END OF PREVIOUS TASK CONTEXT ===\n")
    return "\n".join(parts)


# ─── Demo ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Eigent Prompt 组装 Demo")
    print("=" * 60)

    context = PromptContext(working_directory="/home/user/project_web_scraper")

    # 1. 展示各 Agent 的 prompt 组装
    for agent_type in [AgentType.developer, AgentType.browser,
                        AgentType.document, AgentType.question_confirm]:
        prompt = assemble_prompt(agent_type, context)
        print(f"\n{'─' * 50}")
        print(f"📝 {agent_type.value} — System Prompt")
        print(f"{'─' * 50}")
        # 只显示前 300 字符
        preview = prompt[:300] + "..." if len(prompt) > 300 else prompt
        print(preview)
        print(f"\n  📏 总长度: {len(prompt)} 字符")

    # 2. 对话历史上下文构建
    print(f"\n{'=' * 60}")
    print("📚 对话历史上下文构建")
    print("=" * 60)

    history = [
        {"role": "user", "content": "Research Python web scraping libraries"},
        {"role": "task_result", "content": "Found: BeautifulSoup4, Scrapy, Playwright, Selenium"},
        {"role": "assistant", "content": "Based on the research, I recommend BeautifulSoup4 for simple scraping."},
        {"role": "user", "content": "Now write a scraper using BeautifulSoup4"},
    ]

    conv_context = build_conversation_context(history)
    print(conv_context)

    # 3. 前序任务上下文
    print(f"{'─' * 50}")
    print("📋 前序任务上下文")
    print("─" * 50)

    prev_context = collect_previous_task_context(
        working_directory="/home/user/project_web_scraper",
        previous_task_content="Research Python web scraping libraries",
        previous_task_result="Found: BeautifulSoup4, Scrapy, Playwright",
    )
    print(prev_context)

    # 4. 完整 prompt 组装（system + context）
    print(f"{'=' * 60}")
    print("🔗 完整 Prompt 组装（Developer Agent + 对话历史）")
    print("=" * 60)

    system_prompt = assemble_prompt(AgentType.developer, context)
    full_context = conv_context + "\nUser Query: Write a web scraper\n"
    total = len(system_prompt) + len(full_context)
    print(f"  System Prompt: {len(system_prompt)} 字符")
    print(f"  对话上下文:    {len(full_context)} 字符")
    print(f"  总计:         {total} 字符")

    # 检查长度限制（原实现 max_length=200000）
    max_length = 200000
    print(f"  上限:         {max_length} 字符")
    if total > max_length:
        print("  ⚠️  超出上限！需要创建新项目。")
    else:
        print(f"  ✅ 在限额内 ({total/max_length*100:.1f}%)")

    print("\n✅ Demo 完成")


if __name__ == "__main__":
    main()
