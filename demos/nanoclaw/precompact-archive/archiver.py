"""PreCompact 对话归档 — NanoClaw transcript 解析与 Markdown 导出

基于 container/agent-runner/src/index.ts 的 createPreCompactHook、
parseTranscript、formatTranscriptMarkdown 实现。

核心: JSONL 解析 → 消息提取(user/assistant) → 截断(2000 chars) → Markdown 归档
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime

# 每条消息的最大字符数（与原实现一致）
MAX_MESSAGE_CHARS = 2000


@dataclass
class ParsedMessage:
    """解析后的单条消息，扩展了 tool_uses 以保留 tool_use block 信息。"""
    role: str  # 'user' | 'assistant'
    content: str
    tool_uses: list[dict] = field(default_factory=list)


def parse_transcript(jsonl_content: str) -> list[ParsedMessage]:
    """将 JSONL transcript 解析为消息列表。跳过无效 JSON 行。"""
    messages: list[ParsedMessage] = []

    for line in jsonl_content.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        entry_type = entry.get("type")
        msg = entry.get("message")
        if not msg:
            continue

        if entry_type == "user":
            content = msg.get("content")
            if content is None:
                continue
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "".join(b.get("text", "") for b in content if isinstance(b, dict))
            else:
                continue
            if text:
                messages.append(ParsedMessage(role="user", content=text))

        elif entry_type == "assistant":
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            text_parts: list[str] = []
            tool_uses: list[dict] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_uses.append({
                        "name": block.get("name", "unknown"),
                        "input": block.get("input", {}),
                    })
            text = "".join(text_parts)
            if text or tool_uses:
                messages.append(ParsedMessage(role="assistant", content=text, tool_uses=tool_uses))

    return messages


def generate_summary(messages: list[ParsedMessage]) -> str:
    """取首条用户消息前 30 字符作为标题，无则返回 'conversation'。"""
    for msg in messages:
        if msg.role == "user" and msg.content.strip():
            return msg.content.strip()[:30].replace("\n", " ")
    return "conversation"


def _truncate(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    """截断过长文本，超出 limit 加 '...' 后缀。"""
    return text if len(text) <= limit else text[:limit] + "..."


def _format_tool_use(tool: dict) -> str:
    """将 tool_use 格式化为 blockquote: > Tool: name(args)"""
    name = tool.get("name", "unknown")
    inputs = tool.get("input", {})
    if isinstance(inputs, dict) and inputs:
        parts = []
        for k, v in list(inputs.items())[:5]:
            vs = str(v)
            parts.append(f"{k}={vs[:60] + '...' if len(vs) > 60 else vs}")
        return f"> Tool: {name}({', '.join(parts)})"
    return f"> Tool: {name}()"


def _sanitize_filename(title: str) -> str:
    """将标题转为安全的文件名片段（小写字母数字 + 连字符）。"""
    name = "".join(ch if ch.isalnum() else "-" for ch in title.lower())
    while "--" in name:
        name = name.replace("--", "-")
    return name.strip("-")[:50] or "conversation"


def archive_to_markdown(
    messages: list[ParsedMessage],
    title: str | None = None,
    output_dir: str = "conversations",
    *,
    assistant_name: str = "Assistant",
    timestamp: datetime | None = None,
) -> str:
    """将消息列表写入 Markdown 归档文件，返回文件路径。

    生成格式:
      # {title}
      Archived: {datetime}
      ---
      **User**: {content}
      **Assistant**: {content}
      > Tool: name(args)
    """
    now = timestamp or datetime.now()
    if title is None:
        title = generate_summary(messages)

    lines: list[str] = [
        f"# {title}", "",
        f"Archived: {now.strftime('%b %d, %I:%M %p')}", "",
        "---", "",
    ]

    for msg in messages:
        sender = "User" if msg.role == "user" else assistant_name
        lines.append(f"**{sender}**: {_truncate(msg.content)}")
        lines.append("")
        for tool in msg.tool_uses:
            lines.append(_format_tool_use(tool))
            lines.append("")

    # 写入文件
    safe_name = _sanitize_filename(title)
    filename = f"{now.strftime('%Y-%m-%d')}-{safe_name}.md"
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
