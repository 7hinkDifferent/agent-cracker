"""
Pi-Agent Multi-Provider LLM Demo

复现 Pi-Agent 的多 Provider LLM 调用层：
- Provider 自动检测（从 model ID 推断 provider）
- 消息格式标准化（OpenAI vs Anthropic content blocks）
- Tool schema 格式转换（function calling vs tool_use）
- 响应解析统一化

Run: uv run python main.py
"""

import json
from providers import (
    LlmClient, LlmMessage, LlmResponse,
    detect_provider, PROVIDERS,
    OpenAIProvider, AnthropicProvider,
)


def demo_provider_detection():
    """演示 model ID → provider 自动路由。"""
    print("=" * 60)
    print("Demo 1: Provider Detection (model ID → provider 路由)")
    print("=" * 60)

    models = [
        "gpt-4o",
        "claude-sonnet-4-20250514",
        "gemini-1.5-pro",
        "mistral-large-latest",
        "grok-2",
        "o3-mini",
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4-turbo",
        "some-unknown-model",
    ]

    for model in models:
        provider = detect_provider(model)
        print(f"  {model:40s} → {provider}")


def demo_message_normalization():
    """演示同一消息在不同 provider 格式下的差异。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Message Normalization (消息格式转换)")
    print("=" * 60)

    # 构造包含 tool call 的对话
    messages = [
        LlmMessage(role="system", content="You are a helpful assistant."),
        LlmMessage(role="user", content="What files are in the current directory?"),
        LlmMessage(
            role="assistant",
            content="Let me check.",
            tool_calls=[{
                "id": "call_123",
                "name": "bash",
                "arguments": {"command": "ls -la"},
            }],
        ),
        LlmMessage(
            role="tool",
            content="total 16\ndrwxr-xr-x  4 user  staff  128 Jan  1 00:00 .\n-rw-r--r--  1 user  staff  256 Jan  1 00:00 main.py",
            tool_call_id="call_123",
        ),
    ]

    for name, provider in PROVIDERS.items():
        normalized = provider.normalize_messages(messages)
        print(f"\n  ── {name} format ──")
        for i, msg in enumerate(normalized):
            role = msg.get("role", "?")
            content = msg.get("content", "")

            # 截断显示
            if isinstance(content, str):
                content_preview = content[:80]
                if len(content) > 80:
                    content_preview += "..."
            elif isinstance(content, list):
                # Anthropic content blocks
                content_preview = f"[{len(content)} blocks: {', '.join(b['type'] for b in content)}]"
            else:
                content_preview = str(content)[:80]

            extra = ""
            if "tool_calls" in msg:
                extra = f" + {len(msg['tool_calls'])} tool_calls"
            if "tool_call_id" in msg:
                extra = f" (tool_call_id={msg['tool_call_id']})"

            print(f"    [{i}] role={role:10s} content={content_preview}{extra}")


def demo_tool_schema_conversion():
    """演示 OpenAI function calling schema → Anthropic tool schema 的转换。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Tool Schema Conversion (工具 schema 格式)")
    print("=" * 60)

    # OpenAI 标准格式
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "read",
                "description": "Read the contents of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "offset": {"type": "integer", "description": "Start line"},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Execute a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to run"},
                    },
                    "required": ["command"],
                },
            },
        },
    ]

    for name, provider in PROVIDERS.items():
        converted = provider.normalize_tools(openai_tools)
        print(f"\n  ── {name} format ──")
        print(f"    {json.dumps(converted, indent=4)[:400]}")
        if len(json.dumps(converted)) > 400:
            print(f"    ...")


def demo_response_parsing():
    """演示不同 provider 的响应解析为统一格式。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Response Parsing (响应解析统一化)")
    print("=" * 60)

    # OpenAI 原始响应
    openai_raw = {
        "choices": [{
            "message": {
                "content": "Let me read that file for you.",
                "tool_calls": [{
                    "id": "call_abc",
                    "type": "function",
                    "function": {
                        "name": "read",
                        "arguments": '{"path": "main.py"}',
                    },
                }],
            },
        }],
        "usage": {"prompt_tokens": 150, "completion_tokens": 30},
    }

    # Anthropic 原始响应
    anthropic_raw = {
        "content": [
            {"type": "text", "text": "Let me read that file for you."},
            {
                "type": "tool_use",
                "id": "toolu_xyz",
                "name": "read",
                "input": {"path": "main.py"},
            },
        ],
        "usage": {"input_tokens": 150, "output_tokens": 30},
    }

    cases = [
        ("openai", openai_raw),
        ("anthropic", anthropic_raw),
    ]

    for provider_name, raw in cases:
        provider = PROVIDERS[provider_name]
        response = provider.parse_response(raw)
        print(f"\n  ── {provider_name} → LlmResponse ──")
        print(f"    content:    \"{response.content}\"")
        print(f"    tool_calls: {len(response.tool_calls)}")
        if response.tool_calls:
            tc = response.tool_calls[0]
            print(f"      [0] id={tc['id']}, name={tc['name']}, args={tc['arguments']}")
        print(f"    usage:      input={response.usage['input']}, output={response.usage['output']}")

    # 验证统一性
    print(f"\n  ── Unified format check ──")
    openai_resp = PROVIDERS["openai"].parse_response(openai_raw)
    anthro_resp = PROVIDERS["anthropic"].parse_response(anthropic_raw)
    print(f"    Both have .content:    {type(openai_resp.content).__name__} == {type(anthro_resp.content).__name__}")
    print(f"    Both have .tool_calls: {type(openai_resp.tool_calls).__name__} == {type(anthro_resp.tool_calls).__name__}")
    print(f"    Both have .usage:      {type(openai_resp.usage).__name__} == {type(anthro_resp.usage).__name__}")
    print(f"    Same tool name:        {openai_resp.tool_calls[0]['name']} == {anthro_resp.tool_calls[0]['name']}")


def demo_mock_client():
    """演示 LlmClient mock 模式（无需 API key）。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Mock Client (无需 API key 的端到端演示)")
    print("=" * 60)

    client = LlmClient()

    models = ["gpt-4o", "claude-sonnet-4-20250514"]
    messages = [
        LlmMessage(role="user", content="Hello, world!"),
    ]
    tools = [{
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a command",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    }]

    for model in models:
        provider_name = detect_provider(model)
        response = client.complete_mock(model, messages, tools)
        print(f"\n  {model} (→ {provider_name}):")
        print(f"    content: \"{response.content}\"")
        print(f"    usage:   {response.usage}")


def main():
    print("Pi-Agent Multi-Provider LLM Demo")
    print("Reproduces the unified LLM calling layer with provider auto-routing\n")

    demo_provider_detection()
    demo_message_normalization()
    demo_tool_schema_conversion()
    demo_response_parsing()
    demo_mock_client()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("\n  Multi-provider LLM layer:")
    print("    1. detect_provider() — model ID → provider routing")
    print("    2. normalize_messages() — unified → provider-specific format")
    print("    3. normalize_tools() — OpenAI schema → provider schema")
    print("    4. parse_response() — provider response → unified LlmResponse")
    print("\n  Key differences between providers:")
    print("    - OpenAI: tool_calls in message, function.arguments as JSON string")
    print("    - Anthropic: content blocks array, tool_use/tool_result types")
    print("    - Usage keys: prompt_tokens/completion_tokens vs input_tokens/output_tokens")
    print("\n✓ Demo complete!")


if __name__ == "__main__":
    main()
