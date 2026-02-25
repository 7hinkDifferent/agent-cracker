"""NanoClaw PreCompact 对话归档 — Demo

演示 PreCompact hook 的核心机制：
  1. 基本归档 — 简单 user/assistant JSONL 转 Markdown
  2. Tool use 提取 — tool_use blocks 格式化为引用块
  3. 长消息截断 — 超过 2000 字符的消息被截断
  4. 混合内容 — 数组格式 user content + 无效 JSON 行容错
  5. 多次归档 — 模拟多次 PreCompact 事件生成多个文件

运行: uv run python main.py
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime

from archiver import (
    ParsedMessage,
    archive_to_markdown,
    generate_summary,
    parse_transcript,
    MAX_MESSAGE_CHARS,
)

DEMO_OUTPUT_DIR = "_demo_conversations"


def _jsonl(*entries: dict) -> str:
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Demo 1: 基本归档
# ---------------------------------------------------------------------------

def demo_basic_archive():
    print("=" * 60)
    print("Demo 1: 基本归档 — JSONL transcript → Markdown")
    print("=" * 60)

    jsonl = _jsonl(
        {"type": "user", "message": {"role": "user", "content": "帮我查一下北京明天的天气"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "北京明天天气: 晴，25°C，微风。适合户外活动。"}]}},
        {"type": "user", "message": {"role": "user", "content": "谢谢！"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "不客气！有其他问题随时问我。"}]}},
    )

    messages = parse_transcript(jsonl)
    print(f"\n  解析出 {len(messages)} 条消息:")
    for msg in messages:
        print(f"    [{msg.role}] {msg.content[:50]}")

    summary = generate_summary(messages)
    print(f"\n  自动摘要: {summary!r}")

    filepath = archive_to_markdown(messages, output_dir=DEMO_OUTPUT_DIR, timestamp=datetime(2026, 2, 25, 14, 30))
    print(f"  归档文件: {filepath}\n  文件内容:")
    for line in _read(filepath).splitlines():
        print(f"    {line}")
    print()


# ---------------------------------------------------------------------------
# Demo 2: Tool use 提取
# ---------------------------------------------------------------------------

def demo_tool_use():
    print("=" * 60)
    print("Demo 2: Tool use 提取 — tool_use blocks → 引用块")
    print("=" * 60)

    jsonl = _jsonl(
        {"type": "user", "message": {"role": "user", "content": "帮我创建一个 hello.py 文件"}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "好的，我来创建这个文件。"},
            {"type": "tool_use", "name": "Write", "input": {"file_path": "/workspace/group/hello.py", "content": "print('Hello, World!')"}},
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "文件已创建。让我运行一下验证。"},
            {"type": "tool_use", "name": "Bash", "input": {"command": "python3 /workspace/group/hello.py"}},
        ]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "运行成功！输出是 'Hello, World!'。"}]}},
    )

    messages = parse_transcript(jsonl)
    print(f"\n  解析出 {len(messages)} 条消息:")
    for msg in messages:
        tools = f" (+{len(msg.tool_uses)} tools)" if msg.tool_uses else ""
        print(f"    [{msg.role}] {msg.content[:50]}{tools}")

    filepath = archive_to_markdown(messages, title="创建 hello.py 文件", output_dir=DEMO_OUTPUT_DIR, timestamp=datetime(2026, 2, 25, 15, 0))
    print(f"\n  归档文件: {filepath}\n  文件内容:")
    for line in _read(filepath).splitlines():
        print(f"    {line}")
    print()


# ---------------------------------------------------------------------------
# Demo 3: 长消息截断
# ---------------------------------------------------------------------------

def demo_truncation():
    print("=" * 60)
    print("Demo 3: 长消息截断 — 5000 字符 → 2000 + '...'")
    print("=" * 60)

    long_content = "这是一段很长的回复。" * 500  # 5000 chars
    print(f"\n  原始消息长度: {len(long_content)} 字符")

    jsonl = _jsonl(
        {"type": "user", "message": {"role": "user", "content": "给我写一篇很长的文章"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": long_content}]}},
    )

    messages = parse_transcript(jsonl)
    filepath = archive_to_markdown(messages, output_dir=DEMO_OUTPUT_DIR, timestamp=datetime(2026, 2, 25, 15, 30))

    for line in _read(filepath).splitlines():
        if line.startswith("**Assistant**:"):
            msg_text = line[len("**Assistant**: "):]
            print(f"  归档中消息长度: {len(msg_text)} 字符")
            print(f"  以 '...' 结尾: {msg_text.endswith('...')}")
            assert len(msg_text) == MAX_MESSAGE_CHARS + 3
            print(f"  截断验证通过 ({MAX_MESSAGE_CHARS} + 3 = {MAX_MESSAGE_CHARS + 3})")
            break
    print()


# ---------------------------------------------------------------------------
# Demo 4: 混合内容 — 数组 user content + 无效 JSON 行
# ---------------------------------------------------------------------------

def demo_mixed_content():
    print("=" * 60)
    print("Demo 4: 混合内容 — 数组 user content + 无效 JSON 容错")
    print("=" * 60)

    lines = [
        json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "text", "text": "第一段话。"}, {"type": "text", "text": "第二段话。"},
        ]}}),
        "[2026-02-25 14:00:00] DEBUG: context compaction triggered",  # 非 JSON
        "",  # 空行
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "收到你的两段话。"}]}}),
        json.dumps({"type": "system", "subtype": "init", "session_id": "sess-001"}),  # 非 user/assistant
        json.dumps({"type": "user"}),  # 缺 message
        json.dumps({"type": "user", "message": {"role": "user", "content": "最后一条消息"}}),
    ]

    messages = parse_transcript("\n".join(lines))
    print(f"\n  输入 {len(lines)} 行 (含无效行)，解析出 {len(messages)} 条消息:")
    for msg in messages:
        print(f"    [{msg.role}] {msg.content}")

    assert messages[0].content == "第一段话。第二段话。"
    print(f"\n  数组 content 拼接验证通过: {messages[0].content!r}")

    filepath = archive_to_markdown(messages, output_dir=DEMO_OUTPUT_DIR, timestamp=datetime(2026, 2, 25, 16, 0))
    print(f"  归档文件: {filepath}")
    print()


# ---------------------------------------------------------------------------
# Demo 5: 多次归档 — 模拟多次 PreCompact 事件
# ---------------------------------------------------------------------------

def demo_multiple_archives():
    print("=" * 60)
    print("Demo 5: 多次归档 — 模拟多次 PreCompact 事件")
    print("=" * 60)

    sessions = [
        (datetime(2026, 2, 25, 9, 0), _jsonl(
            {"type": "user", "message": {"role": "user", "content": "早上好，帮我看看今天的日程"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "早上好！你今天有 3 个会议。"}]}},
        )),
        (datetime(2026, 2, 25, 14, 30), _jsonl(
            {"type": "user", "message": {"role": "user", "content": "帮我写一封邮件给 Bob"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "好的，我已经起草了邮件。"}]}},
        )),
        (datetime(2026, 2, 25, 18, 0), _jsonl(
            {"type": "user", "message": {"role": "user", "content": "总结一下今天的工作"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "今天你完成了 3 个会议和 2 封邮件。"}]}},
        )),
    ]

    print(f"\n  模拟 {len(sessions)} 次 PreCompact 事件:")
    for i, (ts, transcript) in enumerate(sessions):
        messages = parse_transcript(transcript)
        filepath = archive_to_markdown(messages, output_dir=DEMO_OUTPUT_DIR, timestamp=ts)
        print(f"    [{i+1}] {ts.strftime('%H:%M')} → {os.path.basename(filepath)}")

    print(f"\n  conversations/ 目录:")
    for f in sorted(os.listdir(DEMO_OUTPUT_DIR)):
        print(f"    {f} ({os.path.getsize(os.path.join(DEMO_OUTPUT_DIR, f))} bytes)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("NanoClaw PreCompact 对话归档 — 机制 Demo\n")
    if os.path.exists(DEMO_OUTPUT_DIR):
        shutil.rmtree(DEMO_OUTPUT_DIR)
    try:
        demo_basic_archive()
        demo_tool_use()
        demo_truncation()
        demo_mixed_content()
        demo_multiple_archives()
        print("All 5 demos passed.")
    finally:
        shutil.rmtree(DEMO_OUTPUT_DIR, ignore_errors=True)
