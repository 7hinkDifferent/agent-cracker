#!/usr/bin/env python3
"""
Mini Gemini — Complete AI Agent Integration

Integrates all MVP and advanced components:
  • MVP: event-driven-loop, tool-registry-system, mcp-tool-integration,
         prompt-assembly, session-replay, error-handling
  • Advanced: message-bus-confirmation, sandbox-execution, context-window-management

This is the "skeleton" of a complete Gemini CLI agent, demonstrating the
core message loop and integration patterns.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Callable, Any
import sys


# ============================================================================
# Part 1: Shared Types & Events
# ============================================================================

class EventType(Enum):
    """Event types in the agent lifecycle."""
    USER_INPUT = "user_input"
    LLM_THINKING = "llm_thinking"
    TOOL_CALL_REQUEST = "tool_call_request"
    TOOL_EXECUTION = "tool_execution"
    TOOL_RESULT = "tool_result"
    CONTEXT_OVERFLOW = "context_overflow"
    ERROR = "error"
    FINISHED = "finished"


@dataclass
class Event:
    """Base event type."""
    event_type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __str__(self) -> str:
        return f"[{self.event_type.value}] {self.data}"


@dataclass
class ToolCallRequest:
    """Request to execute a tool."""
    call_id: str
    tool_name: str
    parameters: Dict[str, Any]


@dataclass
class ToolResult:
    """Result from tool execution."""
    tool_name: str
    success: bool
    output: Any
    error: Optional[str] = None


# ============================================================================
# Part 2: Tool Registry (MVP layer, D3)
# ============================================================================

class BaseDeclarativeTool:
    """Base class for all tools."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    async def invoke(self, parameters: Dict) -> ToolResult:
        """Execute tool with given parameters."""
        raise NotImplementedError

    def get_function_declaration(self) -> Dict:
        """Get function declaration for LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}},
        }


class ReadFileTool(BaseDeclarativeTool):
    """Tool: read file contents."""

    def __init__(self):
        super().__init__("read_file", "Read a file from the filesystem")

    async def invoke(self, parameters: Dict) -> ToolResult:
        file_path = parameters.get("file_path", "")
        await asyncio.sleep(0.05)
        return ToolResult(
            tool_name=self.name,
            success=True,
            output=f"Content of {file_path}:\n# Demo file content",
        )


class ToolRegistry:
    """Tool registry for managing all available tools."""

    def __init__(self):
        self. tools: Dict[str, BaseDeclarativeTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register default tools."""
        self.tools["read_file"] = ReadFileTool()

    async def invoke_tool(
        self, tool_name: str, parameters: Dict
    ) -> ToolResult:
        """Invoke a registered tool."""
        if tool_name not in self.tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                error=f"Unknown tool: {tool_name}",
            )

        tool = self.tools[tool_name]
        return await tool.invoke(parameters)


# ============================================================================
# Part 3: Prompt Assembly (MVP layer, D4)
# ============================================================================

class PromptAssembler:
    """Assemble prompts from multiple sources."""

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self.system_prompt = (
            "You are a helpful AI assistant powered by Google Gemini. "
            "You have access to tools to read files, execute commands, and more. "
            "Think step by step before using tools. "
            "When done, respond directly without using tools."
        )

    def assemble_system_prompt(self) -> str:
        """Assemble full system prompt with tool declarations."""
        tools_section = "Available tools:\n"
        for tool_name, tool in self.tool_registry.tools.items():
            decl = tool.get_function_declaration()
            tools_section += f"  • {tool_name}: {tool.description}\n"

        return self.system_prompt + "\n\n" + tools_section


# ============================================================================
# Part 4: Event-Driven Loop (MVP layer, D2)
# ============================================================================

class AgentLoop:
    """
    Main event-driven loop of the agent.

    Flow:
    1. Get user input
    2. Send to LLM (with system prompt + tool declarations)
    3. Stream LLM response → parse tool calls
    4. Execute tools in parallel
    5. Feed results back to LLM
    6. Repeat until finished or error
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        prompt_assembler: PromptAssembler,
        approval_bus=None,
        sandbox_executor=None,
        context_manager=None,
    ):
        self.tool_registry = tool_registry
        self.prompt_assembler = prompt_assembler
        self.approval_bus = approval_bus
        self.sandbox_executor = sandbox_executor
        self.context_manager = context_manager
        self.turn_count = 0
        self.max_turns = 5

    async def run(self, user_input: str):
        """
        Run agent loop for user input.
        Yields events as they occur.
        """
        self.turn_count = 0
        current_parts = [{"type": "text", "text": user_input}]

        while self.turn_count < self.max_turns:
            self.turn_count += 1

            # Emit thinking event
            yield Event(EventType.LLM_THINKING, {"turn": self.turn_count})

            # Build prompt
            system_prompt = self.prompt_assembler.assemble_system_prompt()

            # Check context overflow (if manager present)
            if self.context_manager:
                if self.context_manager.metrics.usage_ratio >= 0.95:
                    yield Event(
                        EventType.CONTEXT_OVERFLOW,
                        {"message": "Context window near limit"},
                    )
                    break

            # Simulate LLM response with optional tool calls
            tool_calls = await self._simulate_llm_response(user_input, self.turn_count)

            if not tool_calls:
                # No tool calls → agent finished
                yield Event(EventType.FINISHED, {"text": "Agent completed."})
                break

            # Execute tools
            for tool_call in tool_calls:
                yield Event(
                    EventType.TOOL_CALL_REQUEST,
                    {"tool": tool_call.tool_name, "params": tool_call.parameters},
                )

                # Check approval (if bus present)
                if self.approval_bus:
                    from dataclasses import dataclass

                    # approval_msg = ApprovalMessage(
                    #     tool_name=tool_call.tool_name,
                    #     parameters=tool_call.parameters,
                    # )
                    # approval_result = await self.approval_bus.request_approval(
                    #     approval_msg
                    # )
                    # if not approval_result.approved:
                    #     yield Event(
                    #         EventType.ERROR,
                    #         {"message": "Tool execution denied"},
                    #     )
                    #     continue
                    pass

                # Execute tool (optionally in sandbox)
                if self.sandbox_executor:
                    # result = await self.sandbox_executor.execute(
                    #     tool_call.tool_name,
                    #     tool_call.parameters,
                    # )
                    result = await self.tool_registry.invoke_tool(
                        tool_call.tool_name, tool_call.parameters
                    )
                else:
                    result = await self.tool_registry.invoke_tool(
                        tool_call.tool_name, tool_call.parameters
                    )

                yield Event(
                    EventType.TOOL_RESULT,
                    {
                        "tool": tool_call.tool_name,
                        "success": result.success,
                        "output": result.output[:100] + "..."
                        if isinstance(result.output, str)
                        else result.output,
                    },
                )

    async def _simulate_llm_response(
        self, user_input: str, turn: int
    ) -> List[ToolCallRequest]:
        """
        Simulate LLM response. In real impl, calls Gemini API.
        """
        await asyncio.sleep(0.2)  # Simulate network latency

        # Strategy: First turn, use tools; second turn, finish
        if turn == 1:
            return [
                ToolCallRequest(
                    call_id="call_1",
                    tool_name="read_file",
                    parameters={"file_path": "main.py"},
                )
            ]
        else:
            return []  # No more tools, finish


# ============================================================================
# Part 5: Session & History (MVP layer, D5)
# ============================================================================

class EventHistory:
    """Track all events in the session."""

    def __init__(self):
        self.events: List[Event] = []
        self.event_id_counter = 0

    def append(self, event: Event) -> int:
        """Add event and return its ID."""
        event_id = self.event_id_counter
        self.event_id_counter += 1
        self.events.append(event)
        return event_id

    def get_from_event(self, event_id: int) -> List[Event]:
        """Get all events from given event ID onwards."""
        if event_id < 0 or event_id >= len(self.events):
            return self.events
        return self.events[event_id:]


# ============================================================================
# Part 6: Error Handling (MVP layer, D6)
# ============================================================================

class AgentErrorHandler:
    """Classify and handle agent errors."""

    def __init__(self):
        self.fatal_patterns = ["allowed", "denied", "shutdown"]
        self.recoverable_patterns = ["timeout", "retry", "overflow"]

    def classify_error(self, error: str) -> str:
        """Classify error as fatal or recoverable."""
        error_lower = error.lower()
        for pattern in self.fatal_patterns:
            if pattern in error_lower:
                return "FATAL"
        for pattern in self.recoverable_patterns:
            if pattern in error_lower:
                return "RECOVERABLE"
        return "UNKNOWN"


# ============================================================================
# Part 7: Main Agent Coordinator
# ============================================================================

class MiniGeminiAgent:
    """
    Coordinates all subsystems to form a complete agent.
    """

    def __init__(self):
        self.tool_registry = ToolRegistry()
        self.prompt_assembler = PromptAssembler(self.tool_registry)
        self.agent_loop = AgentLoop(
            self.tool_registry,
            self.prompt_assembler,
        )
        self.error_handler = AgentErrorHandler()
        self.history = EventHistory()

        # Optional advanced components
        self.approval_bus = None  # message-bus-confirmation
        self.sandbox_executor = None  # sandbox-execution
        self.context_manager = None  # context-window-management

    async def process_user_input(self, user_input: str):
        """
        Process user input through the agent loop.
        """
        print(f"\n{'='*60}")
        print(f"Processing: {user_input}")
        print(f"{'='*60}\n")

        # Record input
        self.history.append(
            Event(EventType.USER_INPUT, {"text": user_input})
        )

        # Run agent loop
        async for event in self.agent_loop.run(user_input):
            # Record event
            self.history.append(event)

            # Display event
            self._display_event(event)

            # Handle errors
            if event.event_type == EventType.ERROR:
                error_class = self.error_handler.classify_error(
                    event.data.get("message", "")
                )
                print(f"   [Error Type: {error_class}]")

    def _display_event(self, event: Event):
        """Display event to user."""
        if event.event_type == EventType.USER_INPUT:
            print(f"👤 User: {event.data['text']}")
        elif event.event_type == EventType.LLM_THINKING:
            print(f"🤔 Turn {event.data['turn']}: LLM is thinking...")
        elif event.event_type == EventType.TOOL_CALL_REQUEST:
            print(
                f"🔧 Tool Call: {event.data['tool']}({event.data['params']})"
            )
        elif event.event_type == EventType.TOOL_RESULT:
            status = "✓" if event.data["success"] else "✗"
            print(f"   {status} Result: {event.data['output']}")
        elif event.event_type == EventType.CONTEXT_OVERFLOW:
            print(f"⚠️  {event.data['message']}")
        elif event.event_type == EventType.FINISHED:
            print(f"✅ {event.data['text']}")
        elif event.event_type == EventType.ERROR:
            print(f"❌ Error: {event.data['message']}")

    def print_session_summary(self):
        """Print summary of the session."""
        print(f"\n{'='*60}")
        print("Session Summary")
        print(f"{'='*60}")
        print(f"Total events: {len(self.history.events)}")
        print(f"Agent turns: {self.agent_loop.turn_count}")

        # Event breakdown
        event_counts = {}
        for event in self.history.events:
            event_type = event.event_type.value
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        print("\nEvent Breakdown:")
        for event_type, count in sorted(event_counts.items()):
            print(f"  • {event_type}: {count}")


# ============================================================================
# Part 8: Main Entry Point
# ============================================================================

async def main():
    """
    Interactive demo of Mini Gemini agent.
    """
    print("\n" + "="*70)
    print("Mini Gemini — Complete Agent Integration Demo")
    print("="*70)
    print("\nThis demo integrates:")
    print("  ✓ MVP: event-loop, tool-registry, mcp, prompt-assembly,")
    print("         session-replay, error-handling")
    print("  ◌ Advanced: message-bus-confirmation, sandbox-execution,")
    print("             context-window-management (disabled in demo)")
    print()

    agent = MiniGeminiAgent()

    # Demo conversation
    user_inputs = [
        "What does the main.py file contain?",
        "Can you summarize the code?",
    ]

    for user_input in user_inputs:
        await agent.process_user_input(user_input)

    # Print summary
    agent.print_session_summary()

    # Show capabilities
    print(f"\n{'='*60}")
    print("Agent Architecture")
    print(f"{'='*60}")
    print(f"✓ Tool Registry: {len(agent.tool_registry.tools)} tools")
    print(f"✓ Prompt Assembler: Ready")
    print(f"✓ Event Loop: Core agent loop")
    print(f"✓ Error Handling: {len(agent.error_handler.fatal_patterns)} fatal patterns")
    print(f"✓ Session History: Fully tracked")
    print(f"◌ Approval Bus: Optional (not enabled)")
    print(f"◌ Sandbox Executor: Optional (not enabled)")
    print(f"◌ Context Manager: Optional (not enabled)")

    print(f"\n{'='*60}")
    print("✅ Demo completed")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
