#!/usr/bin/env python3
"""
Error Handling & Recovery — Minimal reproduction of Gemini CLI's error flow

This demo shows how Gemini CLI handles different error types:

1. LLM errors: ContextWindowWillOverflow, InvalidStream, Error
2. Tool errors: STOP_EXECUTION, FATAL_ERROR, INVALID_PARAMS, TOOL_NOT_FOUND
3. Error propagation: Determines whether to continue or abort the agent loop

Key insights:
- Different error types are handled differently
- Some errors are "fatal" (abort loop), others are "recoverable" (continue)
- Tools can signal agent to stop gracefully (STOP_EXECUTION)
- All errors are recorded as events for audit trail
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
import logging

# ============================================================================
# Error Types
# ============================================================================

class LLMErrorType(str, Enum):
    """Types of errors from LLM"""
    CONTEXT_WINDOW_OVERFLOW = "context_window_overflow"
    INVALID_STREAM = "invalid_stream"
    ERROR = "error"
    UNKNOWN = "unknown"


class ToolErrorType(str, Enum):
    """Categories of tool execution errors"""
    # Non-fatal errors (loop continues)
    INVALID_PARAMS = "invalid_params"
    TOOL_NOT_FOUND = "tool_not_found"
    TIMEOUT = "timeout"

    # Important signals (loop may stop)
    STOP_EXECUTION = "stop_execution"  # User/tool requests stop
    FATAL_ERROR = "fatal_error"  # Tool execution failed critically


# ============================================================================
# Error Representations
# ============================================================================

@dataclass
class LLMError:
    """Error from LLM response"""
    type: LLMErrorType
    message: str
    recoverable: bool = False  # Can agent continue?

    def __str__(self) -> str:
        return f"LLMError[{self.type}]: {self.message}"


@dataclass
class ToolError:
    """Error from tool execution"""
    call_id: str
    tool_name: str
    error_type: ToolErrorType
    message: str

    def is_fatal(self) -> bool:
        """Check if this error should stop the agent loop"""
        return self.error_type == ToolErrorType.FATAL_ERROR

    def is_stop_signal(self) -> bool:
        """Check if this is a graceful stop signal"""
        return self.error_type == ToolErrorType.STOP_EXECUTION

    def __str__(self) -> str:
        return f"ToolError[{self.tool_name}]: {self.message}"


@dataclass
class ToolResult:
    """Result of tool execution (may contain error)"""
    call_id: str
    tool_name: str
    output: str = ""
    error: Optional[ToolError] = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def is_fatal(self) -> bool:
        return self.error.is_fatal() if self.error else False

    @property
    def is_stop_signal(self) -> bool:
        return self.error.is_stop_signal() if self.error else False


# ============================================================================
# Error Handling Logic
# ============================================================================

class AgentErrorHandler:
    """Handles errors in agent loop (mirrors legacy-agent-session.ts logic)"""

    def __init__(self):
        self.logger = logging.getLogger("ErrorHandler")

    def handle_llm_error(self, error: LLMError) -> str:
        """
        Decide what to do with LLM error.
        Returns: "abort", "continue", or "retry"
        """
        self.logger.error(f"LLM Error: {error}")

        if error.type == LLMErrorType.CONTEXT_WINDOW_OVERFLOW:
            self.logger.warning("Context window will overflow, aborting")
            return "abort"

        elif error.type == LLMErrorType.INVALID_STREAM:
            self.logger.warning("Invalid stream, aborting")
            return "abort"

        elif error.type == LLMErrorType.ERROR:
            self.logger.warning("LLM returned error, aborting")
            return "abort"

        else:
            self.logger.error(f"Unknown LLM error type: {error.type}")
            return "abort"

    def handle_tool_results(
        self, results: list[ToolResult]
    ) -> tuple[str, Optional[str]]:
        """
        Process tool results and determine loop flow.
        Returns: (action, reason)
        where action is one of: "continue", "stop_graceful", "stop_fatal"
        """
        # Check for stop signals
        for result in results:
            if result.is_stop_signal:
                self.logger.info(
                    f"Tool {result.tool_name} requested graceful stop"
                )
                return ("stop_graceful", result.tool_name)

        # Check for fatal errors
        fatal_tool = None
        for result in results:
            if result.is_fatal:
                fatal_tool = result.tool_name
                break

        if fatal_tool:
            self.logger.error(f"Tool {fatal_tool} failed fatally")
            return ("stop_fatal", fatal_tool)

        # All tools succeeded or had recoverable errors
        return ("continue", None)

    def categorize_tool_error(
        self, tool_name: str, exception: Exception
    ) -> ToolError:
        """
        Categorize a tool execution error.
        Maps exceptions to ToolErrorType.
        """
        message = str(exception)

        if "timeout" in message.lower():
            return ToolError(
                call_id="",
                tool_name=tool_name,
                error_type=ToolErrorType.TIMEOUT,
                message=message,
            )

        elif "not found" in message.lower():
            return ToolError(
                call_id="",
                tool_name=tool_name,
                error_type=ToolErrorType.TOOL_NOT_FOUND,
                message=message,
            )

        elif "invalid" in message.lower() or "parameter" in message.lower():
            return ToolError(
                call_id="",
                tool_name=tool_name,
                error_type=ToolErrorType.INVALID_PARAMS,
                message=message,
            )

        else:
            # Default to fatal
            return ToolError(
                call_id="",
                tool_name=tool_name,
                error_type=ToolErrorType.FATAL_ERROR,
                message=message,
            )


# ============================================================================
# Agent Loop with Error Handling
# ============================================================================

class AgentLoopWithErrorHandling:
    """
    Simplified agent loop showing error handling.
    Mirrors the switch statements in legacy-agent-session._runLoop().
    """

    def __init__(self):
        self.handler = AgentErrorHandler()
        self.logger = logging.getLogger("AgentLoop")

    async def run(self, user_query: str) -> str:
        """
        Run agent with error handling.
        Returns final status.
        """
        self.logger.info(f"Starting with query: {user_query}")

        turn = 0
        while True:
            turn += 1

            # [Hypothetical]  Call LLM
            llm_error = self._simulate_llm_call()
            if llm_error:
                action = self.handler.handle_llm_error(llm_error)
                if action == "abort":
                    self.logger.error("Agent aborted due to LLM error")
                    return "failed"
                continue

            # [Hypothetical] Execute tools
            tool_results = self._simulate_tool_execution()

            # Handle tool results
            action, reason = self.handler.handle_tool_results(tool_results)

            if action == "stop_graceful":
                self.logger.info(f"Agent stopped gracefully (tool: {reason})")
                return "completed"

            elif action == "stop_fatal":
                self.logger.error(f"Agent stopped due to fatal tool error (tool: {reason})")
                return "failed"

            elif action == "continue":
                if turn > 10:
                    self.logger.info("Reached max turns")
                    return "max_turns"
                continue

        return "unknown"

    def _simulate_llm_call(self) -> Optional[LLMError]:
        """
        Simulate LLM call.
        For demo, returns None (no error).
        """
        return None

    def _simulate_tool_execution(self) -> list[ToolResult]:
        """
        Simulate tool execution with various error scenarios.
        """
        # Demo: return different results based on call count
        return [
            ToolResult(
                call_id="1",
                tool_name="read-file",
                output="File contents...",
                error=None,
            ),
            ToolResult(
                call_id="2",
                tool_name="shell",
                output="",
                error=None,
            ),
        ]


# ============================================================================
# Example Usage
# ============================================================================

def main():
    """Demonstrate error handling"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(name)-15s | %(message)s",
    )

    print("=" * 70)
    print("ERROR HANDLING DEMONSTRATION")
    print("=" * 70)

    handler = AgentErrorHandler()

    # Test 1: LLM errors
    print("\n[Test 1] LLM Error Handling")
    print("-" * 70)

    llm_errors = [
        LLMError(LLMErrorType.CONTEXT_WINDOW_OVERFLOW, "Context too large"),
        LLMError(LLMErrorType.INVALID_STREAM, "Stream ended unexpectedly"),
        LLMError(LLMErrorType.ERROR, "Internal API error"),
    ]

    for error in llm_errors:
        action = handler.handle_llm_error(error)
        print(f"  {error.type.value:30s} → {action}")

    # Test 2: Tool error categorization
    print("\n[Test 2] Tool Error Categorization")
    print("-" * 70)

    exceptions = [
        ("shell", Exception("Command timed out after 30s")),
        ("read-file", Exception("Tool 'read-file' not found")),
        ("grep", Exception("Invalid parameter: 'pattern' required")),
        ("custom-tool", Exception("Unexpected failure: segmentation fault")),
    ]

    for tool_name, exc in exceptions:
        error = handler.categorize_tool_error(tool_name, exc)
        print(f"  {tool_name:15s} → {error.error_type.value:20s} ({error.message})")

    # Test 3: Tool result processing
    print("\n[Test 3] Tool Result Processing")
    print("-" * 70)

    # Scenario A: All succeeded
    results_success = [
        ToolResult("1", "read-file", output="content"),
        ToolResult("2", "grep", output="matches"),
    ]
    action, reason = handler.handle_tool_results(results_success)
    print(f"  All tools succeeded → action: {action}")

    # Scenario B: Stop signal
    results_stop = [
        ToolResult("1", "read-file", output="content"),
        ToolResult(
            "2",
            "ask-user",
            error=ToolError("2", "ask-user", ToolErrorType.STOP_EXECUTION, "User aborted"),
        ),
    ]
    action, reason = handler.handle_tool_results(results_stop)
    print(f"  Stop signal from {reason} → action: {action}")

    # Scenario C: Fatal error
    results_fatal = [
        ToolResult("1", "read-file", output="content"),
        ToolResult(
            "2",
            "shell",
            error=ToolError("2", "shell", ToolErrorType.FATAL_ERROR, "Command failed"),
        ),
    ]
    action, reason = handler.handle_tool_results(results_fatal)
    print(f"  Fatal error in {reason} → action: {action}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
