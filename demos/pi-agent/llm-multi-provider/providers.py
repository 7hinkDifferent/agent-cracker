"""
Pi-Agent 多 Provider LLM 调用层。

提供统一接口适配多个 LLM Provider，可被其他 demo（如 mini-pi）导入复用。

核心接口:
  - LlmProvider: Provider 适配器基类
  - detect_provider(): 从 model ID 检测 provider
  - LlmClient: 统一客户端，路由到对应 provider
"""

import os
import json
from dataclasses import dataclass, field


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class LlmMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[dict] | None = None  # [{id, name, arguments}]
    tool_call_id: str | None = None       # for role="tool"


@dataclass
class LlmResponse:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)  # {input, output}


# ── Provider 检测 ────────────────────────────────────────────────

PROVIDER_PATTERNS = {
    "openai": ["gpt-", "o1-", "o3-", "chatgpt-"],
    "anthropic": ["claude-"],
    "google": ["gemini-"],
    "mistral": ["mistral-", "codestral-"],
    "xai": ["grok-"],
}


def detect_provider(model_id: str) -> str:
    """
    从 model ID 检测 provider。
    对应 pi-agent 的 packages/ai/src/providers/ 路由逻辑。
    """
    model_lower = model_id.lower()

    # 显式前缀 provider/model
    if "/" in model_lower:
        prefix = model_lower.split("/")[0]
        if prefix in PROVIDER_PATTERNS:
            return prefix
        # litellm 风格
        if prefix in ("openai", "anthropic", "google", "mistral", "xai"):
            return prefix

    # 模式匹配
    for provider, patterns in PROVIDER_PATTERNS.items():
        for pattern in patterns:
            if model_lower.startswith(pattern):
                return provider

    return "openai"  # 默认


# ── Provider 适配器 ──────────────────────────────────────────────

class LlmProvider:
    """Provider 适配器基类。"""
    name = "base"

    def get_api_key_env(self) -> str:
        raise NotImplementedError

    def normalize_messages(self, messages: list[LlmMessage]) -> list[dict]:
        """将统一消息格式转为 provider 特定格式。"""
        raise NotImplementedError

    def normalize_tools(self, tools: list[dict]) -> list[dict]:
        """将 OpenAI 格式 tool schema 转为 provider 特定格式。"""
        raise NotImplementedError

    def parse_response(self, raw: dict) -> LlmResponse:
        """解析 provider 响应为统一格式。"""
        raise NotImplementedError


class OpenAIProvider(LlmProvider):
    """OpenAI API 适配器（也兼容 OpenAI 兼容 API）。"""
    name = "openai"

    def get_api_key_env(self) -> str:
        return "OPENAI_API_KEY"

    def normalize_messages(self, messages: list[LlmMessage]) -> list[dict]:
        result = []
        for msg in messages:
            d = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                d["tool_call_id"] = msg.tool_call_id
            result.append(d)
        return result

    def normalize_tools(self, tools: list[dict]) -> list[dict]:
        # OpenAI 格式就是标准格式
        return tools

    def parse_response(self, raw: dict) -> LlmResponse:
        choice = raw["choices"][0]["message"]
        tool_calls = []
        if choice.get("tool_calls"):
            for tc in choice["tool_calls"]:
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": json.loads(tc["function"]["arguments"]),
                })
        usage = raw.get("usage", {})
        return LlmResponse(
            content=choice.get("content", "") or "",
            tool_calls=tool_calls,
            usage={
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
            },
        )


class AnthropicProvider(LlmProvider):
    """Anthropic API 适配器。"""
    name = "anthropic"

    def get_api_key_env(self) -> str:
        return "ANTHROPIC_API_KEY"

    def normalize_messages(self, messages: list[LlmMessage]) -> list[dict]:
        result = []
        for msg in messages:
            if msg.role == "system":
                continue  # Anthropic 的 system 走单独参数
            d = {"role": msg.role}
            if msg.role == "assistant" and msg.tool_calls:
                # Anthropic: content 是数组
                content_blocks = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["arguments"],
                    })
                d["content"] = content_blocks
            elif msg.role == "tool":
                # Anthropic: tool_result 在 user 消息中
                d = {
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                }
            else:
                d["content"] = msg.content
            result.append(d)
        return result

    def normalize_tools(self, tools: list[dict]) -> list[dict]:
        # Anthropic 用 name/description/input_schema 格式
        result = []
        for t in tools:
            fn = t["function"]
            result.append({
                "name": fn["name"],
                "description": fn["description"],
                "input_schema": fn["parameters"],
            })
        return result

    def parse_response(self, raw: dict) -> LlmResponse:
        content_text = ""
        tool_calls = []
        for block in raw.get("content", []):
            if block["type"] == "text":
                content_text += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "name": block["name"],
                    "arguments": block["input"],
                })
        usage = raw.get("usage", {})
        return LlmResponse(
            content=content_text,
            tool_calls=tool_calls,
            usage={
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
            },
        )


# ── Provider 注册表 ──────────────────────────────────────────────

PROVIDERS: dict[str, LlmProvider] = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
}


# ── 统一客户端 ───────────────────────────────────────────────────

class LlmClient:
    """
    统一 LLM 客户端，自动路由到对应 provider。
    对应 pi-agent 的 packages/ai/src/ 层。
    """

    def complete(
        self,
        model: str,
        messages: list[LlmMessage],
        tools: list[dict] | None = None,
    ) -> LlmResponse:
        """
        调用 LLM 并返回统一格式响应。
        实际项目中这里会发 HTTP 请求；demo 中使用 litellm 简化。
        """
        import litellm

        provider_name = detect_provider(model)
        provider = PROVIDERS.get(provider_name, PROVIDERS["openai"])

        # 转换消息和工具
        normalized_msgs = provider.normalize_messages(messages)
        normalized_tools = provider.normalize_tools(tools) if tools else None

        # 通过 litellm 统一调用（它处理了底层 HTTP 差异）
        kwargs = {"model": model, "messages": normalized_msgs, "temperature": 0}

        # 提取 system message
        system_msgs = [m for m in messages if m.role == "system"]
        if system_msgs and provider_name != "anthropic":
            # OpenAI 格式 system 已在 normalized_msgs 中
            pass

        if normalized_tools:
            kwargs["tools"] = normalized_tools

        raw = litellm.completion(**kwargs)
        raw_dict = raw.model_dump()

        # 用 OpenAI provider 解析（litellm 统一返回 OpenAI 格式）
        return PROVIDERS["openai"].parse_response(raw_dict)

    def complete_mock(
        self,
        model: str,
        messages: list[LlmMessage],
        tools: list[dict] | None = None,
        mock_response: dict | None = None,
    ) -> LlmResponse:
        """
        Mock 版本，用于无 API key 的演示。
        展示 provider 检测和消息格式转换。
        """
        provider_name = detect_provider(model)
        provider = PROVIDERS.get(provider_name, PROVIDERS["openai"])

        normalized_msgs = provider.normalize_messages(messages)
        normalized_tools = provider.normalize_tools(tools) if tools else None

        if mock_response:
            return provider.parse_response(mock_response)

        return LlmResponse(
            content=f"[Mock response from {provider_name}/{model}]",
            tool_calls=[],
            usage={"input": len(str(normalized_msgs)) // 4, "output": 20},
        )
