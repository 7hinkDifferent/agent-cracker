# Demo: Pi-Agent — Multi-Provider LLM

## 目标

用最简代码复现 Pi-Agent 的多 Provider LLM 调用层。

## MVP 角色

多 Provider 支持是 agent 的"通信层"——决定如何与不同 LLM 厂商交互。Pi-Agent 的特色是**统一接口 + 自动路由**：同一 `LlmClient.complete()` 调用可以透明地路由到 OpenAI、Anthropic、Google 等 provider，自动处理消息格式、工具 schema、响应解析的差异。

## 原理

Pi-Agent 的 LLM 调用层有 4 个核心环节���

1. **Provider 检测** — 从 model ID（如 `gpt-4o`、`claude-sonnet-4-20250514`）自动推断使用哪个 provider
2. **消息格式转换** — 统一的 `LlmMessage` 转为 provider 特定格式（OpenAI 的 `tool_calls` vs Anthropic 的 `content blocks`）
3. **Tool Schema 转换** — OpenAI 标准的 `function calling` 格式转为 provider 格式（如 Anthropic 的 `input_schema`）
4. **响应解析** — 各 provider 不同的响应格式解析为统一的 `LlmResponse`

关键差异点：

| 方面 | OpenAI | Anthropic |
|------|--------|-----------|
| System 消息 | 在 messages 中 | 单独 `system` 参数 |
| Tool calls | `message.tool_calls[].function.arguments`（JSON string） | `content[].type="tool_use"`，`input` 是 object |
| Tool results | `role: "tool"` + `tool_call_id` | `role: "user"` + `content[].type="tool_result"` |
| Usage | `prompt_tokens` / `completion_tokens` | `input_tokens` / `output_tokens` |

## 运行

```bash
cd demos/pi-agent/llm-multi-provider
uv run python main.py
```

无需 API key，使用 mock 模式演示格式转换逻辑。

## 文件结构

```
demos/pi-agent/llm-multi-provider/
├── README.md       # 本文件
├── providers.py    # 可复用模块: LlmClient + Provider 适配器
└── main.py         # Demo 入口（从 providers.py import）
```

## 关键代码解读

### Provider 自动检测

```python
PROVIDER_PATTERNS = {
    "openai": ["gpt-", "o1-", "o3-", "chatgpt-"],
    "anthropic": ["claude-"],
    "google": ["gemini-"],
    ...
}

def detect_provider(model_id: str) -> str:
    # 1. 显式前缀: "anthropic/claude-xxx" → "anthropic"
    # 2. 模式匹配: "gpt-4o" → "openai"
    # 3. 默认: "openai"
```

### Anthropic 消息格式差异

```python
class AnthropicProvider(LlmProvider):
    def normalize_messages(self, messages):
        # system → 跳过（走单独参数）
        # assistant + tool_calls → content blocks 数组
        # tool result → role="user" + type="tool_result"
```

### 统一响应解析

```python
@dataclass
class LlmResponse:
    content: str = ""               # 文本内容
    tool_calls: list[dict] = ...    # [{id, name, arguments}]
    usage: dict = ...               # {input, output}
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 语言 | TypeScript | Python |
| Provider 数量 | 6（OpenAI/Anthropic/Google/Mistral/xAI/OpenRouter） | 2（OpenAI/Anthropic） |
| 流式响应 | SSE streaming + delta 拼接 | 非流式（简化） |
| 错误处理 | 10+ 错误模式匹配 + overflow 检测 | 省略 |
| Token 计算 | 精确 tokenizer + 溢出预防 | usage 透传 |
| HTTP 客户端 | 原生 fetch + SSE parser | litellm（简化） |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 基于 commit: `316c2af`
- 核心源码: `packages/ai/src/providers/`
