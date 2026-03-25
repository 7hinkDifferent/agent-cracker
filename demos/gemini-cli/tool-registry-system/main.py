#!/usr/bin/env python3
"""
Tool Registry System — Minimal reproduction of Gemini CLI's tool registration

This demo implements the tool registry and execution framework:

1. Define tools by extending BaseDeclarativeTool
2. Each tool has metadata (name, description, parameters)
3. Registry maintains a map of tool_name -> tool instance
4. Tools are invoked with parameters validated against schema
5. Multiple tools execute in parallel (asyncio-based)

Key insights:
- Tool abstraction separates tool logic from agent loop
- FunctionDeclaration metadata enables type-safe invocation
- Tools can be added/removed without modifying agent core
"""

import asyncio
import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
import logging

# ============================================================================
# Tool Metadata & Declarations
# ============================================================================

@dataclass
class ParameterSchema:
    """JSON Schema fragment for a single parameter"""
    type: str  # "string", "number", "object", "array"
    description: str
    required: bool = False


@dataclass
class FunctionDeclaration:
    """
    Metadata that describes a tool to the LLM.
    Mirrors google.genai.FunctionDeclaration.
    """
    name: str
    description: str
    parameters: dict[str, ParameterSchema] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary form (for LLM)"""
        params = {
            "type": "object",
            "properties": {},
            "required": []
        }
        for param_name, schema in self.parameters.items():
            params["properties"][param_name] = {
                "type": schema.type,
                "description": schema.description,
            }
            if schema.required:
                params["required"].append(param_name)
        return {
            "name": self.name,
            "description": self.description,
            "parameters": params,
        }


@dataclass
class ToolResult:
    """Result from executing a tool"""
    output: str
    error: Optional[str] = None
    tool_name: str = ""


# ============================================================================
# Tool Base Class
# ============================================================================

class BaseDeclarativeTool(ABC):
    """Abstract base class for all tools"""

    @abstractmethod
    def get_declaration(self) -> FunctionDeclaration:
        """Return the tool's metadata declaration"""
        pass

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute the tool with given parameters"""
        pass

    async def build_and_execute(
        self, params: dict[str, Any]
    ) -> ToolResult:
        """
        Validate parameters and execute.
        In real implementation, Genai SDK validates before calling this.
        """
        try:
            result = await self.execute(params)
            result.tool_name = self.get_declaration().name
            return result
        except Exception as e:
            return ToolResult(
                output="",
                error=str(e),
                tool_name=self.get_declaration().name,
            )


# ============================================================================
# Concrete Tool Implementations
# ============================================================================

class ReadFileTool(BaseDeclarativeTool):
    """Read a file and return its contents"""

    def get_declaration(self) -> FunctionDeclaration:
        return FunctionDeclaration(
            name="read-file",
            description="Read the contents of a file",
            parameters={
                "file": ParameterSchema(
                    type="string",
                    description="Path to the file to read",
                    required=True,
                ),
            },
        )

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        file_path = params.get("file")
        if not file_path:
            return ToolResult(
                output="",
                error="Missing required parameter: file",
            )

        try:
            with open(file_path, "r") as f:
                content = f.read()
            return ToolResult(output=content)
        except FileNotFoundError:
            return ToolResult(output="", error=f"File not found: {file_path}")
        except Exception as e:
            return ToolResult(output="", error=str(e))


class WriteFileTool(BaseDeclarativeTool):
    """Write contents to a file"""

    def get_declaration(self) -> FunctionDeclaration:
        return FunctionDeclaration(
            name="write-file",
            description="Write contents to a file",
            parameters={
                "file": ParameterSchema(
                    type="string",
                    description="Path to the file",
                    required=True,
                ),
                "content": ParameterSchema(
                    type="string",
                    description="Content to write",
                    required=True,
                ),
            },
        )

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        file_path = params.get("file")
        content = params.get("content")

        if not file_path or content is None:
            return ToolResult(
                output="",
                error="Missing required parameters: file, content",
            )

        try:
            with open(file_path, "w") as f:
                f.write(content)
            return ToolResult(output=f"Wrote {len(content)} bytes to {file_path}")
        except Exception as e:
            return ToolResult(output="", error=str(e))


class ShellTool(BaseDeclarativeTool):
    """Execute a shell command"""

    def get_declaration(self) -> FunctionDeclaration:
        return FunctionDeclaration(
            name="shell",
            description="Execute a shell command",
            parameters={
                "command": ParameterSchema(
                    type="string",
                    description="Shell command to execute",
                    required=True,
                ),
            },
        )

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        command = params.get("command")
        if not command:
            return ToolResult(
                output="",
                error="Missing required parameter: command",
            )

        try:
            # Run with timeout
            result = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=5.0,
            )
            stdout, stderr = await result.communicate()
            output = stdout.decode("utf-8", errors="ignore")
            if result.returncode != 0:
                error = stderr.decode("utf-8", errors="ignore")
                return ToolResult(output=output, error=error)
            return ToolResult(output=output)
        except asyncio.TimeoutError:
            return ToolResult(output="", error="Command timed out after 5 seconds")
        except Exception as e:
            return ToolResult(output="", error=str(e))


class GrepTool(BaseDeclarativeTool):
    """Search for text patterns in files"""

    def get_declaration(self) -> FunctionDeclaration:
        return FunctionDeclaration(
            name="grep",
            description="Search for patterns in files",
            parameters={
                "pattern": ParameterSchema(
                    type="string",
                    description="Text pattern to search for",
                    required=True,
                ),
                "file": ParameterSchema(
                    type="string",
                    description="File to search in",
                    required=True,
                ),
            },
        )

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        pattern = params.get("pattern")
        file_path = params.get("file")

        if not pattern or not file_path:
            return ToolResult(
                output="",
                error="Missing required parameters: pattern, file",
            )

        try:
            with open(file_path, "r") as f:
                lines = f.readlines()

            matches = []
            for i, line in enumerate(lines, 1):
                if pattern.lower() in line.lower():
                    matches.append(f"{i}: {line.rstrip()}")

            output = "\n".join(matches) if matches else "(no matches)"
            return ToolResult(output=output)
        except FileNotFoundError:
            return ToolResult(output="", error=f"File not found: {file_path}")
        except Exception as e:
            return ToolResult(output="", error=str(e))


# ============================================================================
# Tool Registry
# ============================================================================

class ToolRegistry:
    """Registry that maintains all available tools"""

    def __init__(self):
        self.tools: dict[str, BaseDeclarativeTool] = {}
        self.logger = logging.getLogger(__name__)

    def register(self, tool: BaseDeclarativeTool) -> None:
        """Register a tool in the registry"""
        decl = tool.get_declaration()
        if decl.name in self.tools:
            self.logger.warning(f"Tool {decl.name} already registered, overwriting")
        self.tools[decl.name] = tool
        self.logger.info(f"Registered tool: {decl.name}")

    def get_tool(self, name: str) -> Optional[BaseDeclarativeTool]:
        """Retrieve a tool by name"""
        return self.tools.get(name)

    def get_all_declarations(self) -> list[FunctionDeclaration]:
        """Get all tool declarations (for LLM)"""
        return [tool.get_declaration() for tool in self.tools.values()]

    async def invoke_tool(
        self, tool_name: str, params: dict[str, Any]
    ) -> ToolResult:
        """Invoke a tool by name"""
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                output="",
                error=f"Tool not found: {tool_name}",
            )
        return await tool.build_and_execute(params)

    async def invoke_parallel(
        self, tool_calls: list[tuple[str, dict[str, Any]]]
    ) -> list[ToolResult]:
        """
        Execute multiple tool calls in parallel.
        Mirrors LegacyAgentSession._scheduler.schedule().
        """
        tasks = [
            self.invoke_tool(tool_name, params)
            for tool_name, params in tool_calls
        ]
        return await asyncio.gather(*tasks)


# ============================================================================
# Example Usage
# ============================================================================

async def main():
    """Demonstrate the tool registry system"""

    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Create and populate registry
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ShellTool())
    registry.register(GrepTool())

    print("=" * 60)
    print("TOOL REGISTRY SYSTEM")
    print("=" * 60)

    # Print all available tools
    print("\n✓ Registered tools:")
    for decl in registry.get_all_declarations():
        print(f"  - {decl.name}: {decl.description}")

    # Single tool invocation
    print("\n" + "=" * 60)
    print("SINGLE TOOL INVOCATION")
    print("=" * 60)

    result = await registry.invoke_tool("shell", {"command": "echo 'Hello from shell tool'"})
    print(f"\nTool: shell")
    print(f"Output: {result.output}")
    if result.error:
        print(f"Error: {result.error}")

    # Parallel tool execution
    print("\n" + "=" * 60)
    print("PARALLEL TOOL EXECUTION")
    print("=" * 60)

    # Create test file
    await registry.invoke_tool("write-file", {
        "file": "/tmp/test_registry.txt",
        "content": "Hello\nWorld\nTest\n",
    })

    tool_calls = [
        ("read-file", {"file": "/tmp/test_registry.txt"}),
        ("grep", {"pattern": "World", "file": "/tmp/test_registry.txt"}),
        ("shell", {"command": "date"}),
    ]

    print(f"\nExecuting {len(tool_calls)} tools in parallel...")
    results = await registry.invoke_parallel(tool_calls)

    for i, result in enumerate(results):
        print(f"\n[{i+1}] {result.tool_name}")
        if result.error:
            print(f"    Error: {result.error}")
        else:
            print(f"    Output: {result.output[:100]}..." if len(result.output) > 100 else f"    Output: {result.output}")

    # Print tool declarations (for LLM)
    print("\n" + "=" * 60)
    print("TOOL DECLARATIONS (FOR LLM)")
    print("=" * 60)
    print(json.dumps(
        [decl.to_dict() for decl in registry.get_all_declarations()],
        indent=2,
    ))


if __name__ == "__main__":
    asyncio.run(main())
