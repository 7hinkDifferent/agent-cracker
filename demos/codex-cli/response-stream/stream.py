"""
Codex CLI Response Stream 核心模块。

提供 SSE 流式响应解析 + function call 增量拼接，可被 mini-codex 导入复用。

核心接口:
  - StreamParser: SSE 流解析器
  - FunctionCallAccumulator: function call 增量拼接
  - ResponseAssembler: 完整响应组装
"""

import json
from dataclasses import dataclass, field


# ── Token 估算 ────────────────────────────────────────────────────

APPROX_BYTES_PER_TOKEN = 4

def approx_token_count(text: str) -> int:
    """
    bytes/4 token 近似估算。
    对应 codex-cli 的 truncate.rs APPROX_BYTES_PER_TOKEN。
    """
    return (len(text.encode("utf-8")) + 3) // 4


# ── SSE 事件 ──────────────────────────────────────────────────────

@dataclass
class SSEEvent:
    """Server-Sent Event。"""
    event: str = ""   # 事件类型
    data: str = ""    # JSON data


def parse_sse_stream(raw_text: str) -> list[SSEEvent]:
    """
    解析 SSE 文本流为事件列表。
    格式: event: xxx\ndata: {...}\n\n
    """
    events = []
    current_event = ""
    current_data = ""

    for line in raw_text.split("\n"):
        line = line.strip()
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            current_data = line[6:]
        elif line == "" and (current_event or current_data):
            events.append(SSEEvent(event=current_event, data=current_data))
            current_event = ""
            current_data = ""

    # 处理末尾没有空行的情况
    if current_event or current_data:
        events.append(SSEEvent(event=current_event, data=current_data))

    return events


# ── Function Call 增量拼接 ────────────────────────────────────────

@dataclass
class PartialFunctionCall:
    """正在拼接中的 function call。"""
    call_id: str = ""
    name: str = ""
    arguments_chunks: list[str] = field(default_factory=list)

    @property
    def arguments_str(self) -> str:
        return "".join(self.arguments_chunks)

    def is_complete(self) -> bool:
        """检查 JSON 是否完整（简单的括号匹配）。"""
        s = self.arguments_str.strip()
        if not s:
            return False
        try:
            json.loads(s)
            return True
        except json.JSONDecodeError:
            return False

    def to_dict(self) -> dict:
        return {
            "id": self.call_id,
            "name": self.name,
            "arguments": json.loads(self.arguments_str) if self.is_complete() else {},
        }


class FunctionCallAccumulator:
    """
    增量拼接 function call 参数。
    LLM 流式返回 tool call 时，arguments 分多个 chunk 到达。
    """

    def __init__(self):
        self._calls: dict[int, PartialFunctionCall] = {}

    def feed_delta(self, index: int, delta: dict):
        """
        喂入一个 delta chunk。
        delta 格式: {id?, function?: {name?, arguments?}}
        """
        if index not in self._calls:
            self._calls[index] = PartialFunctionCall()

        pc = self._calls[index]

        if "id" in delta:
            pc.call_id = delta["id"]

        fn = delta.get("function", {})
        if "name" in fn:
            pc.name = fn["name"]
        if "arguments" in fn:
            pc.arguments_chunks.append(fn["arguments"])

    def get_completed(self) -> list[dict]:
        """获取所有已完成的 function calls。"""
        result = []
        for pc in self._calls.values():
            if pc.is_complete():
                result.append(pc.to_dict())
        return result

    def get_all(self) -> list[PartialFunctionCall]:
        return list(self._calls.values())


# ── 响应组装器 ────────────────────────────────────────────────────

@dataclass
class StreamedResponse:
    """组装完成的响应。"""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict = field(default_factory=dict)


class ResponseAssembler:
    """
    从 SSE 事件流组装完整响应。
    对应 codex-cli 的 stream.rs 流式解析逻辑。
    """

    def __init__(self):
        self._content_chunks: list[str] = []
        self._fc_accumulator = FunctionCallAccumulator()
        self._finish_reason = ""
        self._usage = {}

    def feed_event(self, event: SSEEvent) -> str | None:
        """
        处理一个 SSE 事件，返回事件类型提示。
        """
        if event.data == "[DONE]":
            return "done"

        try:
            data = json.loads(event.data)
        except json.JSONDecodeError:
            return None

        # 使用量信息
        if "usage" in data:
            self._usage = data["usage"]

        choices = data.get("choices", [])
        if not choices:
            return None

        choice = choices[0]
        delta = choice.get("delta", {})
        self._finish_reason = choice.get("finish_reason", "") or self._finish_reason

        # 文本内容 delta
        if "content" in delta and delta["content"]:
            self._content_chunks.append(delta["content"])
            return "content_delta"

        # Tool call delta
        if "tool_calls" in delta:
            for tc_delta in delta["tool_calls"]:
                index = tc_delta.get("index", 0)
                self._fc_accumulator.feed_delta(index, tc_delta)
            return "tool_call_delta"

        return "other"

    def build(self) -> StreamedResponse:
        """构建完整响应。"""
        return StreamedResponse(
            content="".join(self._content_chunks),
            tool_calls=self._fc_accumulator.get_completed(),
            finish_reason=self._finish_reason,
            usage=self._usage,
        )

    @property
    def partial_content(self) -> str:
        return "".join(self._content_chunks)

    @property
    def partial_calls(self) -> list[PartialFunctionCall]:
        return self._fc_accumulator.get_all()
