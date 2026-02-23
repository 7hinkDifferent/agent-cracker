"""
Codex CLI Response Stream Demo

复现 Codex CLI 的流式响应解析：
- SSE (Server-Sent Events) 流解析
- Function call 增量拼接（多 chunk 拼接 JSON）
- Token 估算（bytes/4 近似）
- 完整响应组装

Run: uv run python main.py
"""

from stream import (
    parse_sse_stream, SSEEvent,
    FunctionCallAccumulator, PartialFunctionCall,
    ResponseAssembler, StreamedResponse,
    approx_token_count,
)


def demo_sse_parsing():
    """演示 SSE 流解析。"""
    print("=" * 60)
    print("Demo 1: SSE Stream Parsing")
    print("=" * 60)

    raw = """event: message
data: {"choices":[{"delta":{"content":"Hello"}}]}

event: message
data: {"choices":[{"delta":{"content":" world"}}]}

event: message
data: {"choices":[{"delta":{"content":"!"}}]}

data: [DONE]
"""

    events = parse_sse_stream(raw)
    print(f"\n  Raw stream: {len(raw)} chars")
    print(f"  Parsed events: {len(events)}")
    for i, ev in enumerate(events):
        print(f"    [{i}] event={ev.event or '(none)'} data={ev.data[:50]}")


def demo_function_call_accumulation():
    """演示 function call 增量拼接。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Function Call Incremental Assembly")
    print("=" * 60)

    acc = FunctionCallAccumulator()

    # 模拟多个 chunk 到达
    deltas = [
        {"index": 0, "id": "call_abc", "function": {"name": "shell"}},
        {"index": 0, "function": {"arguments": '{"com'}},
        {"index": 0, "function": {"arguments": 'mand":'}},
        {"index": 0, "function": {"arguments": ' "ls -la"}'}},
    ]

    print(f"\n  Feeding {len(deltas)} deltas:")
    for i, delta in enumerate(deltas):
        acc.feed_delta(delta.get("index", 0), delta)
        partial = acc.get_all()[0]
        complete = "✓" if partial.is_complete() else "..."
        print(f"    [{i}] args so far: \"{partial.arguments_str}\" {complete}")

    completed = acc.get_completed()
    print(f"\n  Completed calls: {len(completed)}")
    if completed:
        print(f"    {completed[0]}")


def demo_multi_tool_calls():
    """演示多个 tool call 的并行拼接。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Multiple Tool Calls (并行拼接)")
    print("=" * 60)

    acc = FunctionCallAccumulator()

    # 两个 tool call 交错到达
    deltas = [
        {"index": 0, "id": "call_1", "function": {"name": "read"}},
        {"index": 1, "id": "call_2", "function": {"name": "shell"}},
        {"index": 0, "function": {"arguments": "{\"path\""}},
        {"index": 1, "function": {"arguments": "{\"command\""}},
        {"index": 0, "function": {"arguments": ": \"main.py\"}"}},
        {"index": 1, "function": {"arguments": ": \"pwd\"}"}},
    ]

    print(f"\n  Feeding {len(deltas)} interleaved deltas:")
    for i, delta in enumerate(deltas):
        idx = delta.get("index", 0)
        acc.feed_delta(idx, delta)
        print(f"    [{i}] index={idx}")

    completed = acc.get_completed()
    print(f"\n  Completed calls: {len(completed)}")
    for tc in completed:
        print(f"    id={tc['id']} name={tc['name']} args={tc['arguments']}")


def demo_full_response():
    """演示完整响应组装。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Full Response Assembly (完整响应)")
    print("=" * 60)

    # 模拟一个带 tool call 的 SSE 流
    sse_events = [
        SSEEvent("message", '{"choices":[{"delta":{"content":"Let me "}}]}'),
        SSEEvent("message", '{"choices":[{"delta":{"content":"check that."}}]}'),
        SSEEvent("message", '{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_x","function":{"name":"shell"}}]}}]}'),
        SSEEvent("message", '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"command\\""}}]}}]}'),
        SSEEvent("message", '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":": \\"ls -la\\"}"}}]}}]}'),
        SSEEvent("message", '{"choices":[{"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":150,"completion_tokens":30}}'),
        SSEEvent("", "[DONE]"),
    ]

    assembler = ResponseAssembler()
    print(f"\n  Processing {len(sse_events)} SSE events:")

    for i, ev in enumerate(sse_events):
        event_type = assembler.feed_event(ev)
        content_so_far = assembler.partial_content
        calls_so_far = len(assembler.partial_calls)
        print(f"    [{i}] {event_type or 'skip':20s} content=\"{content_so_far}\" calls={calls_so_far}")

    response = assembler.build()
    print(f"\n  ── Assembled Response ──")
    print(f"    content:       \"{response.content}\"")
    print(f"    tool_calls:    {response.tool_calls}")
    print(f"    finish_reason: {response.finish_reason}")
    print(f"    usage:         {response.usage}")


def demo_token_estimation():
    """演示 bytes/4 token 估算。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Token Estimation (bytes/4)")
    print("=" * 60)

    texts = [
        "Hello, world!",
        "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
        "这是一段中文文本，用于测试 UTF-8 多字节字符的 token 估算。",
        "A" * 1000,
    ]

    for text in texts:
        tokens = approx_token_count(text)
        byte_len = len(text.encode("utf-8"))
        char_len = len(text)
        preview = text[:40].replace("\n", "\\n")
        if len(text) > 40:
            preview += "..."
        print(f"\n  \"{preview}\"")
        print(f"    chars={char_len} bytes={byte_len} tokens≈{tokens} (bytes/4)")


def main():
    print("Codex CLI Response Stream Demo")
    print("Reproduces SSE parsing + function call incremental assembly\n")

    demo_sse_parsing()
    demo_function_call_accumulation()
    demo_multi_tool_calls()
    demo_full_response()
    demo_token_estimation()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("\n  Response stream pipeline:")
    print("    1. SSE parsing (event: + data: format)")
    print("    2. Function call accumulation (multi-chunk JSON)")
    print("    3. Content delta concatenation")
    print("    4. Full response assembly (content + tools + usage)")
    print("\n  Token estimation: bytes/4 (conservative, no tokenizer needed)")
    print("\n✓ Demo complete!")


if __name__ == "__main__":
    main()
