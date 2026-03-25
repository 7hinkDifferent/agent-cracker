#!/usr/bin/env python3
"""
Event-Driven Agent Loop — Minimal reproduction of Gemini CLI's _runLoop

This demo implements the core event-driven main loop that drives Gemini CLI:

1. Send message to LLM with streaming
2. Collect tool call requests as events
3. Execute tools concurrently
4. Feed tool responses back to LLM
5. Repeat until terminal condition (Finished/Error/MaxTurns)

Key insights:
- Fully streaming: each LLM event is emitted immediately (vs polling)
- Non-blocking tool execution: tools run in parallel via asyncio
- Event-based: AbortController pattern for cancellation
"""

import asyncio
import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import google.generativeai as genai


# ============================================================================
# Type Definitions
# ============================================================================

class EventType(str, Enum):
    """LLM response event types"""
    TEXT_CHUNK = "text_chunk"
    TOOL_CALL_REQUEST = "tool_call_request"
    FINISHED = "finished"
    ERROR = "error"
    CONTEXT_WINDOW_OVERFLOW = "context_window_overflow"


class FinishReason(str, Enum):
    """LLM finish reasons"""
    STOP = "STOP"
    MAX_TOKENS = "MAX_TOKENS"
    SAFETY = "SAFETY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ToolCallRequest:
    """Represents a tool call requested by the LLM"""
    call_id: str
    name: str
    params: dict


@dataclass
class Event:
    """Base event emitted during agent loop"""
    type: EventType
    data: Optional[dict] = None


@dataclass
class ToolResult:
    """Result of tool execution"""
    call_id: str
    output: str
    error: Optional[str] = None


# ============================================================================
# Event-Driven Loop Implementation
# ============================================================================

class AgentLoop:
    """Event-driven agent loop inspired by LegacyAgentSession._runLoop()"""

    def __init__(self, model: str = "gemini-2.5-flash", max_turns: int = 10):
        self.model = model
        self.max_turns = max_turns
        self.client = genai.GenerativeModel(model)
        self.turn_count = 0
        self.abort_signal = asyncio.Event()  # Not set = continue, set = abort

    async def run(self, user_message: str) -> list[Event]:
        """
        Execute the main agent loop.

        Args:
            user_message: Initial user prompt

        Returns:
            All events emitted during this run
        """
        events = []
        current_parts = [user_message]

        while True:
            self.turn_count += 1
            print(f"\n=== Turn {self.turn_count} ===")

            # Check turn limit
            if self.turn_count > self.max_turns:
                print(f"Reached max turns ({self.max_turns}), stopping")
                events.append(Event(EventType.FINISHED, {"reason": "max_turns"}))
                break

            # Check abort signal
            if self.abort_signal.is_set():
                print("Aborted by user")
                break

            # ===== THINK: Call LLM with streaming =====
            tool_call_requests = []
            response_text = ""

            try:
                response = await self._send_message_stream(current_parts)

                # Process each event from LLM
                for event in response.events:
                    if event["type"] == "text":
                        chunk = event.get("text", "")
                        response_text += chunk
                        print(f"LLM: {chunk}", end="", flush=True)
                        events.append(Event(EventType.TEXT_CHUNK, {"text": chunk}))

                    elif event["type"] == "tool_call_request":
                        req = ToolCallRequest(
                            call_id=event["id"],
                            name=event["name"],
                            params=event["args"],
                        )
                        tool_call_requests.append(req)
                        print(f"\n[Tool Call] {req.name} (id: {req.call_id})")
                        events.append(
                            Event(
                                EventType.TOOL_CALL_REQUEST,
                                {
                                    "name": req.name,
                                    "params": req.params,
                                },
                            )
                        )

                    elif event["type"] == "error":
                        print(f"\n[LLM Error] {event['error']}")
                        events.append(
                            Event(
                                EventType.ERROR,
                                {"error": event["error"]},
                            )
                        )
                        return events

                # Check finish reason
                finish_reason = response.finish_reason
                print(f"\n[Finished] reason={finish_reason}")
                events.append(
                    Event(
                        EventType.FINISHED,
                        {"reason": finish_reason},
                    )
                )

                # If no tool calls, we're done
                if not tool_call_requests:
                    print("No tools to call, loop complete")
                    break

            except Exception as e:
                print(f"\n[Error] {e}")
                events.append(Event(EventType.ERROR, {"error": str(e)}))
                break

            # ===== ACT: Execute tools concurrently =====
            print(f"\n[Executing {len(tool_call_requests)} tools...]")
            tool_results = await self._execute_tools(tool_call_requests)

            # ===== OBSERVE: Build tool response parts for next iteration =====
            tool_response_parts = []
            for result in tool_results:
                print(f"Tool {result.call_id} result: {result.output[:100]}...")
                tool_response_parts.append(f"Tool {result.name}: {result.output}")

            # Prepare next round: append responses to continue conversation
            current_parts = [
                *current_parts,
                response_text,  # LLM's response
                *tool_response_parts,  # Tool outcomes
            ]

        return events

    async def _send_message_stream(self, parts: list[str]) -> dict:
        """
        Send message to LLM with streaming.

        Simulates genai SDK's streaming response. In real implementation,
        this would use genai.GenerativeModel.generate_content_stream().
        """
        # Simplified mock: return a response structure
        return {
            "events": [
                {
                    "type": "text",
                    "text": "I'll help you with that task. Let me break it down...",
                },
                {
                    "type": "tool_call_request",
                    "id": "call_1",
                    "name": "read_file",
                    "args": {"file": "example.py"},
                },
                {
                    "type": "text",
                    "text": "Now I'll process the file...",
                },
            ],
            "finish_reason": "tool_calls",  # or "stop", "max_tokens", etc.
        }

    async def _execute_tools(
        self, requests: list[ToolCallRequest]
    ) -> list[ToolResult]:
        """
        Execute multiple tools concurrently (simulated).

        In real implementation, this would invoke the actual tools.
        """
        async def mock_tool_exec(req: ToolCallRequest) -> ToolResult:
            # Simulate tool execution delay
            await asyncio.sleep(0.5)
            return ToolResult(
                call_id=req.call_id,
                output=f"Result from {req.name} with {req.params}",
            )

        # Run all tools concurrently
        tasks = [mock_tool_exec(req) for req in requests]
        results = await asyncio.gather(*tasks)
        return results


# ============================================================================
# Example Usage
# ============================================================================

async def main():
    """Demonstrate the event-driven loop"""
    
    # Initialize Gemini API
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set")
        print("Get your API key from https://aistudio.google.com/apikey")
        return
    
    genai.configure(api_key=api_key)

    # Create and run the loop
    loop = AgentLoop(model="gemini-2.5-flash", max_turns=3)
    
    events = await loop.run(
        "Write a Python function that checks if a number is prime"
    )

    # Print event summary
    print("\n" + "=" * 60)
    print("EVENT SUMMARY")
    print("=" * 60)
    for i, event in enumerate(events):
        print(f"{i}. {event.type}: {event.data}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
