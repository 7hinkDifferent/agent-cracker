from __future__ import annotations

"""Hermes agent-session-loop demo core.

复现 Hermes `AIAgent.run_conversation()` 的最小主循环：
- provider fallback
- tool loop
- interrupt
- context compression
- final response persistence
"""

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class AssistantTurn:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class Message:
    role: str
    content: str
    tool_call_id: Optional[str] = None


class ProviderError(RuntimeError):
    """Raised when a provider fails before returning a usable turn."""


class MockProvider:
    """Scripted provider used to simulate fallback and tool calling."""

    def __init__(
        self,
        name: str,
        script: Iterable[AssistantTurn],
        fail_on_call: int | None = None,
        fail_on_calls: set[int] | None = None,
    ):
        self.name = name
        self._script = list(script)
        self.fail_on_call = fail_on_call
        self.fail_on_calls = fail_on_calls or set()
        self.call_count = 0

    def complete(self, messages: list[Message], system_prompt: str) -> AssistantTurn:
        self.call_count += 1
        should_fail = (
            (self.fail_on_call is not None and self.call_count == self.fail_on_call)
            or self.call_count in self.fail_on_calls
        )
        if should_fail:
            raise ProviderError(f"{self.name} unavailable during API call {self.call_count}")
        if self.call_count - 1 >= len(self._script):
            return AssistantTurn(content=f"[{self.name}] no more scripted turns")
        return self._script[self.call_count - 1]


class CompressionStrategy:
    """Replace the middle of the conversation with a summary block."""

    def __init__(self, threshold_chars: int = 260):
        self.threshold_chars = threshold_chars

    def should_compress(self, messages: list[Message]) -> bool:
        return sum(len(m.content) for m in messages) > self.threshold_chars

    def compress(self, messages: list[Message]) -> list[Message]:
        if len(messages) <= 4:
            return messages
        head = messages[:2]
        middle = messages[2:-1]
        tail = messages[-1:]
        summary = " | ".join(f"{m.role}:{m.content[:28]}" for m in middle)
        return head + [Message("system", f"[compressed-summary] {summary}")] + tail


class InterruptController:
    """Minimal interrupt flag used by gateway/CLI style stop signals."""

    def __init__(self):
        self.reason: str | None = None

    def trigger(self, reason: str):
        self.reason = reason

    def consume(self) -> str | None:
        reason = self.reason
        self.reason = None
        return reason


ToolHandler = Callable[[dict], str]


class HermesLoopAgent:
    """Minimal Hermes-style conversation loop.

    The loop keeps one stable system prompt, retries across providers, executes
    returned tool calls, optionally compresses the conversation, and stops when
    the model returns plain text.
    """

    def __init__(
        self,
        providers: list[MockProvider],
        tools: dict[str, ToolHandler],
        compression: CompressionStrategy | None = None,
        interrupt: InterruptController | None = None,
        max_iterations: int = 6,
    ):
        self.providers = providers
        self.tools = tools
        self.compression = compression or CompressionStrategy()
        self.interrupt = interrupt or InterruptController()
        self.max_iterations = max_iterations
        self.events: list[str] = []
        self.history: list[Message] = []
        self._cached_system_prompt: str | None = None

    def _log(self, text: str):
        self.events.append(text)

    def _call_with_fallback(self, messages: list[Message], system_prompt: str) -> AssistantTurn:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                self._log(f"API call via {provider.name}")
                return provider.complete(messages, system_prompt)
            except ProviderError as exc:
                last_error = exc
                self._log(f"fallback from {provider.name}: {exc}")
        raise ProviderError(str(last_error or "all providers failed"))

    def run(self, user_message: str, system_prompt: str) -> str:
        self._cached_system_prompt = self._cached_system_prompt or system_prompt
        messages = [Message("user", user_message)]
        self.history = [Message("system", self._cached_system_prompt)] + messages[:]

        for iteration in range(1, self.max_iterations + 1):
            reason = self.interrupt.consume()
            if reason:
                self._log(f"interrupt received: {reason}")
                messages.append(Message("system", f"[interrupt] {reason}"))

            if self.compression.should_compress(messages):
                messages = self.compression.compress(messages)
                self._log("context compressed into lineage summary")

            turn = self._call_with_fallback(messages, self._cached_system_prompt)
            self._log(f"assistant turn {iteration}: {turn.content or '[tool-calls]'}")
            messages.append(Message("assistant", turn.content or "[tool-calls]"))

            if not turn.tool_calls:
                self.history = [Message("system", self._cached_system_prompt)] + messages
                return turn.content

            for call in turn.tool_calls:
                handler = self.tools.get(call.name)
                if not handler:
                    result = f"Unknown tool: {call.name}"
                else:
                    result = handler(call.arguments)
                self._log(f"tool {call.name}({call.arguments}) -> {result}")
                messages.append(Message("tool", result, tool_call_id=call.id))

        self.history = [Message("system", self._cached_system_prompt)] + messages
        return "Stopped: iteration budget reached"
