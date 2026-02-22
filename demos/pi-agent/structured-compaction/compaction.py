"""
Structured Compaction — 结构化上下文压缩

复现 pi-agent 的 Compaction 策略：
  chars/4 token 估算 → 阈值触发 → 向后累积找切割点 → LLM 结构化摘要 → 增量 UPDATE

核心设计：
  - Token 估算: chars / 4（保守高估，不依赖特定 tokenizer）
  - 切割点选择: 从末尾向前累积 token，在 user/assistant 边界切（不在 tool_result 处切）
  - 结构化摘要: Goal / Progress / Key Decisions / Next Steps / Critical Context
  - 增量 UPDATE: 后续压缩不重写，而是更新已有摘要

原实现: packages/coding-agent/src/core/compaction/compaction.ts
"""

import os

try:
    import litellm
except ImportError:
    litellm = None


# ── Token 估算 ────────────────────────────────────────────────

def estimate_tokens(message: dict) -> int:
    """chars/4 启发式估算 token 数

    对应原实现: compaction.ts — estimateTokens()
    保守高估，适用于所有 provider（不依赖特定 tokenizer）
    """
    role = message.get("role", "")
    content = message.get("content", "")

    if isinstance(content, str):
        chars = len(content)
    elif isinstance(content, list):
        chars = sum(len(block.get("text", "")) for block in content)
    else:
        chars = 0

    # 加上 role 和元数据的开销
    chars += len(role) + 10

    return max(1, chars // 4)


def total_tokens(messages: list[dict]) -> int:
    return sum(estimate_tokens(m) for m in messages)


# ── 切割点查找 ────────────────────────────────────────────────

def find_cut_point(messages: list[dict], keep_recent_tokens: int) -> int:
    """从末尾向前累积 token，找到切割点

    对应原实现: compaction.ts — findCutPoint()

    规则：
    - 从最新消息向前累积
    - 超过 keep_recent_tokens 时在 user/assistant 边界切
    - 不在 tool_result 消息处切（必须与 tool_call 保持一起）
    """
    accumulated = 0

    # 找所有合法切割点（user 或 assistant 消息的位置）
    valid_cut_points = []
    for i, msg in enumerate(messages):
        if msg["role"] in ("user", "assistant"):
            valid_cut_points.append(i)

    if not valid_cut_points:
        return 0

    # 从末尾向前累积
    for i in range(len(messages) - 1, -1, -1):
        accumulated += estimate_tokens(messages[i])
        if accumulated >= keep_recent_tokens:
            # 找最近的合法切割点（>= i）
            for cp in valid_cut_points:
                if cp >= i:
                    return cp
            return valid_cut_points[-1]

    return 0  # 全部保留


# ── 压缩触发判断 ──────────────────────────────────────────────

def should_compact(
    messages: list[dict],
    context_window: int = 128000,
    reserve_tokens: int = 16384,
) -> bool:
    """判断是否需要压缩

    对应原实现: compaction.ts — shouldCompact()
    """
    return total_tokens(messages) > context_window - reserve_tokens


# ── 结构化摘要 Prompt ─────────────────────────────────────────

INITIAL_SUMMARY_PROMPT = """\
Summarize the following conversation into a structured format.
Be concise but preserve all critical information.

Format your response EXACTLY as:

## Goal
[What is the user trying to accomplish?]

## Constraints & Preferences
- [Any constraints or preferences mentioned]

## Progress
### Done
- [x] [Completed tasks]
### In Progress
- [ ] [Tasks currently being worked on]

## Key Decisions
- **[Decision]**: [Reasoning]

## Next Steps
1. [What should happen next]

## Critical Context
- [Any critical data, file paths, error messages, or technical details that must be preserved]

Keep the summary under 500 tokens. Focus on actionable information."""

UPDATE_SUMMARY_PROMPT = """\
UPDATE the existing summary below with new information from the recent conversation.

Rules:
- PRESERVE all existing information that is still relevant
- ADD new progress, decisions, and context from the recent conversation
- Move items from "In Progress" to "Done" when completed
- Update "Next Steps" based on current state
- Do NOT rewrite from scratch — incrementally update

Keep the same structured format. Keep it under 500 tokens."""


# ── 摘要生成 ──────────────────────────────────────────────────

def generate_summary(
    messages: list[dict],
    previous_summary: str | None = None,
    model: str | None = None,
) -> str:
    """调用 LLM 生成结构化摘要

    对应原实现: compaction.ts — generateSummary()
    """
    if litellm is None:
        return _mock_summary(messages, previous_summary)

    model = model or os.environ.get("DEMO_MODEL", "openai/gpt-4o-mini")

    # 构建 prompt
    conversation_text = _serialize_messages(messages)

    if previous_summary:
        user_content = (
            f"<previous-summary>\n{previous_summary}\n</previous-summary>\n\n"
            f"<recent-conversation>\n{conversation_text}\n</recent-conversation>\n\n"
            f"{UPDATE_SUMMARY_PROMPT}"
        )
    else:
        user_content = (
            f"<conversation>\n{conversation_text}\n</conversation>\n\n"
            f"{INITIAL_SUMMARY_PROMPT}"
        )

    try:
        response = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": "You are a precise summarization assistant."},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=800,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  ⚠ LLM 调用失败: {e}，使用 mock 摘要")
        return _mock_summary(messages, previous_summary)


def _serialize_messages(messages: list[dict]) -> str:
    """将消息列表序列化为文本"""
    lines = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg.get("content", "")
        if isinstance(content, str):
            lines.append(f"[{role}]: {content}")
        elif isinstance(content, list):
            text = " ".join(b.get("text", "") for b in content)
            lines.append(f"[{role}]: {text}")
    return "\n".join(lines)


def _mock_summary(messages: list[dict], previous_summary: str | None = None) -> str:
    """无 LLM 时的 mock 摘要"""
    # 提取用户消息
    user_msgs = [m["content"] for m in messages if m["role"] == "user" and isinstance(m["content"], str)]
    first_goal = user_msgs[0] if user_msgs else "未知目标"
    done_count = sum(1 for m in messages if m["role"] == "assistant")

    if previous_summary:
        return (
            previous_summary.rstrip()
            + f"\n\n### Updated Progress\n- [x] 处理了 {len(user_msgs)} 条新消息\n"
            + f"- [x] 完成了 {done_count} 轮对话\n"
        )

    return f"""## Goal
{first_goal}

## Constraints & Preferences
- 从对话中提取（{len(messages)} 条消息）

## Progress
### Done
- [x] 已完成 {done_count} 轮对话

## Key Decisions
- **摘要模式**: mock（无 LLM API key）

## Next Steps
1. 继续当前任务

## Critical Context
- 总消息数: {len(messages)}
- 总 token 估算: {total_tokens(messages)}"""


# ── 主压缩流程 ────────────────────────────────────────────────

def compact(
    messages: list[dict],
    context_window: int = 128000,
    reserve_tokens: int = 16384,
    keep_recent_tokens: int = 20000,
    previous_summary: str | None = None,
    model: str | None = None,
) -> dict:
    """执行一次压缩

    对应原实现: compaction.ts — compact()

    Returns:
        {
            "summary": str,          # 结构化摘要
            "kept_messages": list,    # 保留的近期消息
            "discarded_count": int,   # 被压缩的消息数
            "tokens_before": int,     # 压缩前 token 数
            "tokens_after": int,      # 压缩后 token 数
        }
    """
    tokens_before = total_tokens(messages)

    # 1. 找切割点
    cut_index = find_cut_point(messages, keep_recent_tokens)

    if cut_index == 0:
        return {
            "summary": previous_summary or "",
            "kept_messages": messages,
            "discarded_count": 0,
            "tokens_before": tokens_before,
            "tokens_after": tokens_before,
        }

    # 2. 分割消息
    messages_to_summarize = messages[:cut_index]
    kept_messages = messages[cut_index:]

    # 3. 生成摘要（初始 or UPDATE）
    summary = generate_summary(messages_to_summarize, previous_summary, model)

    # 4. 构建压缩后的消息列表
    compacted = [{"role": "user", "content": f"[Compacted Summary]\n\n{summary}"}]
    compacted.extend(kept_messages)

    tokens_after = total_tokens(compacted)

    return {
        "summary": summary,
        "kept_messages": compacted,
        "discarded_count": len(messages_to_summarize),
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
    }
