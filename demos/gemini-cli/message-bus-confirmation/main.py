#!/usr/bin/env python3
"""
Message Bus Confirmation Demo

Reproduces Gemini CLI's permission confirmation mechanism for tool execution.
Demonstrates how tools can be gated behind approval policies: AUTO, INTERACTIVE, or DENY.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List
from abc import ABC, abstractmethod


class ApprovalMode(Enum):
    """Tool execution approval mode."""
    AUTO = "auto"                  # Automatically approve all executions
    INTERACTIVE = "interactive"    # Ask user before each execution
    DENY = "deny"                  # Reject all execution attempts


class ApprovalDecision(Enum):
    """User's approval decision."""
    APPROVED = "approved"
    DENIED = "denied"
    ALWAYS_ALLOW = "always_allow"  # Cache approval for future same tool
    DENY_ALL = "deny_all"          # Cache denial for future same tool


@dataclass
class ApprovalMessage:
    """Request for tool execution approval."""
    tool_name: str
    parameters: Dict = field(default_factory=dict)
    reason: str = "Tool execution requires approval"
    
    def __str__(self) -> str:
        params_str = ", ".join(f"{k}={v}" for k, v in self.parameters.items())
        return f"Tool: {self.tool_name}({params_str}) | Reason: {self.reason}"


@dataclass
class ApprovalResult:
    """Result of an approval request."""
    approved: bool
    decision: ApprovalDecision
    reason: str = ""
    cached: bool = False  # Whether this came from cached policy


class ToolExecutionError(Exception):
    """Raised when tool execution is denied."""
    pass


class ApprovalBus(ABC):
    """Abstract base for approval/confirmation buses."""

    @abstractmethod
    async def request_approval(self, message: ApprovalMessage) -> ApprovalResult:
        """Request approval for tool execution."""
        pass


class InteractiveApprovalBus(ApprovalBus):
    """
    Interactive confirmation bus supporting three approval modes.
    
    Maintains per-tool approval cache to avoid repeated user prompts.
    """

    def __init__(self, default_mode: ApprovalMode = ApprovalMode.INTERACTIVE):
        self.default_mode = default_mode
        self.approval_cache: Dict[str, ApprovalDecision] = {}  # tool_name -> decision
        self.denied_tools: set = set()  # Tools that user denied
        self.interaction_history: List[Dict] = []

    async def request_approval(self, message: ApprovalMessage) -> ApprovalResult:
        """
        Request approval for tool execution based on mode and cache.
        
        Flow:
        1. Check approval cache for this tool
        2. If cached, return cached decision
        3. Otherwise, check approval mode:
           - AUTO: approve immediately
           - INTERACTIVE: ask user
           - DENY: reject immediately
        4. Cache decision if user chose ALWAYS_ALLOW/DENY_ALL
        """
        tool_name = message.tool_name

        # Check cache first
        if tool_name in self.approval_cache:
            cached_decision = self.approval_cache[tool_name]
            approved = cached_decision in (ApprovalDecision.APPROVED, ApprovalDecision.ALWAYS_ALLOW)
            return ApprovalResult(
                approved=approved,
                decision=cached_decision,
                reason=f"Using cached decision for {tool_name}",
                cached=True,
            )

        # Auto-deny denied tools
        if tool_name in self.denied_tools:
            return ApprovalResult(
                approved=False,
                decision=ApprovalDecision.DENY_ALL,
                reason="Tool is in deny list",
                cached=True,
            )

        # Apply approval mode
        if self.default_mode == ApprovalMode.AUTO:
            decision = ApprovalDecision.APPROVED
            approved = True
        elif self.default_mode == ApprovalMode.DENY:
            decision = ApprovalDecision.DENIED
            approved = False
        else:  # INTERACTIVE
            # Simulate user interaction
            decision, approved = await self._ask_user(message)
            
            # Cache persistent decisions
            if decision in (ApprovalDecision.ALWAYS_ALLOW, ApprovalDecision.DENY_ALL):
                self.approval_cache[tool_name] = decision
                if decision == ApprovalDecision.DENY_ALL:
                    self.denied_tools.add(tool_name)

        result = ApprovalResult(
            approved=approved,
            decision=decision,
            reason=f"Mode: {self.default_mode.value}",
            cached=False,
        )
        
        # Record interaction
        self.interaction_history.append({
            "tool": tool_name,
            "message": str(message),
            "result": result.approved,
        })
        
        return result

    async def _ask_user(self, message: ApprovalMessage) -> tuple[ApprovalDecision, bool]:
        """
        Simulate interactive user confirmation.
        In real implementation, this would use Ink UI framework.
        """
        print(f"\n{'='*60}")
        print(f"⚠️  APPROVAL REQUIRED")
        print(f"{'='*60}")
        print(f"Tool: {message.tool_name}")
        if message.parameters:
            print(f"Parameters: {message.parameters}")
        print(f"Reason: {message.reason}")
        print(f"\nOptions:")
        print("  (y) Approve this execution")
        print("  (n) Deny this execution")
        print("  (a) Always allow this tool")
        print("  (x) Always deny this tool")
        print("  (q) Abort session")
        
        # Simulate user input (in real scenario, read from stdin)
        # For demo, cycle through different responses
        choice = self._simulate_user_input(message.tool_name)
        
        decision_map = {
            'y': (ApprovalDecision.APPROVED, True),
            'n': (ApprovalDecision.DENIED, False),
            'a': (ApprovalDecision.ALWAYS_ALLOW, True),
            'x': (ApprovalDecision.DENY_ALL, False),
            'q': (ApprovalDecision.DENIED, False),  # Would abort session in real impl
        }
        
        decision, approved = decision_map[choice]
        print(f"→ User choice: {choice} ({['DENIED', 'APPROVED'][approved]})")
        
        return decision, approved

    def _simulate_user_input(self, tool_name: str) -> str:
        """Simulate different user decisions for demo purposes."""
        # Strategy: auto-approve read tools, ask about write/shell tools
        if tool_name.startswith("read"):
            return 'y'
        elif tool_name.startswith("write") or tool_name == "shell":
            return 'y' if len(self.interaction_history) == 0 else 'n'
        else:
            return 'y'


class ToolScheduler:
    """
    Tool execution scheduler with approval gate.
    
    Integrates with ApprovalBus to gate tool execution.
    """

    def __init__(self, approval_bus: ApprovalBus):
        self.approval_bus = approval_bus
        self.tool_registry: Dict[str, callable] = {}
        self._register_demo_tools()

    def _register_demo_tools(self):
        """Register demo tools for testing."""
        self.tool_registry = {
            "read_file": self._tool_read_file,
            "write_file": self._tool_write_file,
            "shell": self._tool_shell,
            "grep": self._tool_grep,
        }

    async def execute_tool(self, tool_name: str, parameters: Dict) -> Dict:
        """
        Execute tool with approval gate.
        
        1. Build approval message
        2. Request approval
        3. Execute tool if approved
        4. Return result or error
        """
        # Request approval
        approval_msg = ApprovalMessage(
            tool_name=tool_name,
            parameters=parameters,
            reason=f"Executing tool: {tool_name}",
        )
        
        result = await self.approval_bus.request_approval(approval_msg)
        
        if not result.approved:
            return {
                "success": False,
                "error": f"Tool execution denied: {result.reason}",
                "error_type": "APPROVAL_DENIED",
            }

        # Execute tool
        if tool_name not in self.tool_registry:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "error_type": "UNKNOWN_TOOL",
            }

        try:
            tool_func = self.tool_registry[tool_name]
            output = await tool_func(parameters)
            return {
                "success": True,
                "output": output,
                "tool": tool_name,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "EXECUTION_ERROR",
            }

    # Demo tool implementations
    async def _tool_read_file(self, params: Dict) -> str:
        """Simulate file reading."""
        file_path = params.get("file", "unknown")
        await asyncio.sleep(0.1)  # Simulate I/O
        return f"Content of {file_path}:\n# Demo file content"

    async def _tool_write_file(self, params: Dict) -> str:
        """Simulate file writing."""
        file_path = params.get("file", "unknown")
        content = params.get("content", "")
        await asyncio.sleep(0.1)
        return f"✓ Wrote {len(content)} bytes to {file_path}"

    async def _tool_shell(self, params: Dict) -> str:
        """Simulate shell command execution."""
        command = params.get("command", "echo 'demo'")
        await asyncio.sleep(0.2)
        return f"$ {command}\nSuccess: command executed"

    async def _tool_grep(self, params: Dict) -> str:
        """Simulate grep search."""
        query = params.get("query", "")
        await asyncio.sleep(0.1)
        return f"Matches for '{query}':\nLine 1: matching content\nLine 5: more matches"


async def main():
    """
    Demo: Different approval modes and caching behavior.
    """
    print("\n" + "="*70)
    print("Gemini CLI: Message Bus Confirmation Demo")
    print("="*70)

    # Demo 1: AUTO mode (approve all)
    print("\n[DEMO 1] ApprovalMode.AUTO - Auto-approve all tools")
    print("-" * 70)
    bus_auto = InteractiveApprovalBus(ApprovalMode.AUTO)
    scheduler_auto = ToolScheduler(bus_auto)
    
    result = await scheduler_auto.execute_tool("read_file", {"file": "main.py"})
    print(f"Result: {result}")

    # Demo 2: DENY mode (reject all)
    print("\n[DEMO 2] ApprovalMode.DENY - Reject all tools")
    print("-" * 70)
    bus_deny = InteractiveApprovalBus(ApprovalMode.DENY)
    scheduler_deny = ToolScheduler(bus_deny)
    
    result = await scheduler_deny.execute_tool("shell", {"command": "rm -rf /"})
    print(f"Result: {result}")

    # Demo 3: INTERACTIVE mode with caching
    print("\n[DEMO 3] ApprovalMode.INTERACTIVE - User decides, with caching")
    print("-" * 70)
    bus_interactive = InteractiveApprovalBus(ApprovalMode.INTERACTIVE)
    scheduler_interactive = ToolScheduler(bus_interactive)
    
    # First call: user decides
    print("\n→ Execute read_file (first time)")
    result1 = await scheduler_interactive.execute_tool("read_file", {"file": "test.txt"})
    print(f"Result: {result1['success']}")
    
    # Second call: same tool, should use cache
    print("\n→ Execute read_file (second time, should be cached)")
    result2 = await scheduler_interactive.execute_tool("read_file", {"file": "another.txt"})
    print(f"Result: {result2}")

    # Demo 4: Complex scenario with multiple tools
    print("\n[DEMO 4] Mixed tool execution with approval chain")
    print("-" * 70)
    bus_mixed = InteractiveApprovalBus(ApprovalMode.INTERACTIVE)
    scheduler_mixed = ToolScheduler(bus_mixed)
    
    tools_to_execute = [
        ("read_file", {"file": "config.json"}),
        ("grep", {"query": "api_key", "file": "config.json"}),
        ("write_file", {"file": "output.txt", "content": "results"}),
    ]
    
    for tool_name, params in tools_to_execute:
        print(f"\n→ Executing {tool_name}")
        result = await scheduler_mixed.execute_tool(tool_name, params)
        status = "✓ SUCCESS" if result['success'] else "✗ FAILED"
        print(f"{status}: {result.get('output') or result.get('error')}")

    # Summary
    print("\n" + "="*70)
    print("Approval Bus Statistics")
    print("="*70)
    print(f"Interactive bus interactions: {len(bus_interactive.interaction_history)}")
    print(f"Mixed bus interactions: {len(bus_mixed.interaction_history)}")
    print(f"Approval cache (mixed): {dict(bus_mixed.approval_cache)}")
    print(f"Denied tools (mixed): {bus_mixed.denied_tools}")


if __name__ == "__main__":
    asyncio.run(main())
