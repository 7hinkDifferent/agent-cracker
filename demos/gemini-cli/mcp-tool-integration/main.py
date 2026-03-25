#!/usr/bin/env python3
"""
MCP Tool Integration — Minimal reproduction of Gemini CLI's MCP support

This demo implements MCP (Model Context Protocol) client functionality:

1. Connect to an MCP server (simulated with mock data)
2. Discover available tools from the server
3. Convert MCP tool definitions to FunctionDeclaration
4. Execute tools via MCP protocol

Key insights:
- MCP enables plugin-style tool extension without modifying agent core
- Tool metadata is standardized (name, description, input_schema)
- MCP calls are async RPC-style (request -> await response)
- Tools can be chained and composed
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Optional
import logging
import uuid


# ============================================================================
# MCP Protocol Types
# ============================================================================

@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 request format"""
    jsonrpc: str = "2.0"
    method: str = ""
    params: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params,
            "id": self.id,
        }


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 response format"""
    result: Optional[dict] = None
    error: Optional[dict] = None
    id: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "JSONRPCResponse":
        return cls(
            result=data.get("result"),
            error=data.get("error"),
            id=data.get("id"),
        )


@dataclass
class MCPToolDefinition:
    """MCP tool metadata"""
    name: str
    description: str
    input_schema: dict  # JSON Schema


@dataclass
class MCPToolResult:
    """Result from MCP tool execution"""
    output: str
    error: Optional[str] = None


# ============================================================================
# MCP Client (Simulated)
# ============================================================================

class MCPServerSimulator:
    """
    Simulates an MCP server for demo purposes.
    In real scenario, would connect via subprocess or HTTP.
    """

    def __init__(self, name: str = "example-server"):
        self.name = name
        self.logger = logging.getLogger(f"MCPServer/{name}")
        self.tools = self._initialize_tools()

    def _initialize_tools(self) -> list[MCPToolDefinition]:
        """Define tools provided by this MCP server"""
        return [
            MCPToolDefinition(
                name="fetch_weather",
                description="Get current weather for a location",
                input_schema={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name or coordinates",
                        },
                    },
                    "required": ["location"],
                },
            ),
            MCPToolDefinition(
                name="fetch_url",
                description="Fetch content from a URL",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch",
                        },
                    },
                    "required": ["url"],
                },
            ),
            MCPToolDefinition(
                name="execute_query",
                description="Execute a database query (demo)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "SQL-like query string",
                        },
                    },
                    "required": ["query"],
                },
            ),
        ]

    async def call_tool(
        self, tool_name: str, params: dict[str, Any]
    ) -> MCPToolResult:
        """Execute a tool call"""
        self.logger.info(f"Calling tool: {tool_name} with {params}")

        # Simulate different tool behaviors
        if tool_name == "fetch_weather":
            location = params.get("location", "Unknown")
            return MCPToolResult(
                output=f"Weather in {location}: Sunny, 25°C, Wind: 5 km/h"
            )

        elif tool_name == "fetch_url":
            url = params.get("url", "")
            if not url:
                return MCPToolResult(output="", error="Missing 'url' parameter")
            return MCPToolResult(
                output=f"Content from {url}:\n<html>Sample page</html>"
            )

        elif tool_name == "execute_query":
            query = params.get("query", "")
            return MCPToolResult(
                output=f"Query result: {len(query)} characters processed\n[Row 1: id=1, value='test']"
            )

        else:
            return MCPToolResult(output="", error=f"Unknown tool: {tool_name}")


# ============================================================================
# MCP Client Manager
# ============================================================================

class MCPClientManager:
    """
    Manages connections to MCP servers and provides unified tool interface.
    Mirrors mcp-client-manager.ts functionality.
    """

    def __init__(self):
        self.logger = logging.getLogger("MCPClientManager")
        self.servers: dict[str, MCPServerSimulator] = {}
        self.tool_cache: dict[str, tuple[str, MCPToolDefinition]] = {}

    async def connect_server(self, server_name: str) -> bool:
        """Connect to an MCP server (simulated)"""
        try:
            server = MCPServerSimulator(name=server_name)
            self.servers[server_name] = server
            self.logger.info(f"Connected to MCP server: {server_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to {server_name}: {e}")
            return False

    async def discover_tools(self) -> dict[str, MCPToolDefinition]:
        """
        Discover all tools from all connected MCP servers.
        Returns: {prefixed_tool_name -> tool_definition}
        """
        discovered = {}

        for server_name, server in self.servers.items():
            for tool in server.tools:
                # Prefix tool name with server name to avoid collisions
                prefixed_name = f"{server_name}_{tool.name}"

                # Check for duplicates
                if prefixed_name in discovered:
                    self.logger.warning(
                        f"Tool name conflict: {prefixed_name}, renaming..."
                    )
                    prefixed_name = f"{server_name}_{tool.name}_{uuid.uuid4().hex[:4]}"

                discovered[prefixed_name] = tool
                self.tool_cache[prefixed_name] = (server_name, tool)
                self.logger.info(f"Discovered tool: {prefixed_name}")

        return discovered

    async def invoke_tool(
        self, tool_name: str, params: dict[str, Any]
    ) -> MCPToolResult:
        """
        Invoke a tool by name.
        Internally:
        1. Look up which server provides this tool
        2. Forward to that server
        3. Return result
        """
        if tool_name not in self.tool_cache:
            return MCPToolResult(output="", error=f"Tool not found: {tool_name}")

        server_name, tool_def = self.tool_cache[tool_name]
        server = self.servers.get(server_name)

        if not server:
            return MCPToolResult(
                output="",
                error=f"Server not connected: {server_name}",
            )

        # Call the server's tool (remove server prefix from tool name)
        actual_tool_name = tool_def.name
        return await server.call_tool(actual_tool_name, params)

    async def invoke_parallel(
        self, tool_calls: list[tuple[str, dict[str, Any]]]
    ) -> list[MCPToolResult]:
        """Execute multiple tool calls in parallel"""
        tasks = [
            self.invoke_tool(tool_name, params)
            for tool_name, params in tool_calls
        ]
        return await asyncio.gather(*tasks)


# ============================================================================
# Example Usage
# ============================================================================

async def main():
    """Demonstrate MCP tool integration"""

    logging.basicConfig(level=logging.INFO)

    # Create and initialize MCP client manager
    manager = MCPClientManager()

    # Connect to MCP servers
    print("=" * 60)
    print("MCP TOOL INTEGRATION")
    print("=" * 60)

    print("\n1. Connecting to MCP servers...")
    await manager.connect_server("example-server")

    # Discover tools
    print("\n2. Discovering tools from MCP servers...")
    tools = await manager.discover_tools()

    print(f"\n✓ Discovered {len(tools)} tools:")
    for tool_name, tool_def in tools.items():
        print(f"  - {tool_name}: {tool_def.description}")

    # Print tool declarations (for LLM)
    print("\n3. Tool declarations (for LLM):")
    declarations = [
        {
            "name": tool_name,
            "description": tool_def.description,
            "parameters": tool_def.input_schema,
        }
        for tool_name, tool_def in tools.items()
    ]
    print(json.dumps(declarations, indent=2))

    # Single tool invocation
    print("\n" + "=" * 60)
    print("4. Single tool invocation")
    print("=" * 60)

    result = await manager.invoke_tool(
        "example-server_fetch_weather",
        {"location": "San Francisco"},
    )
    print(f"\nTool: example-server_fetch_weather")
    print(f"Result: {result.output}")
    if result.error:
        print(f"Error: {result.error}")

    # Parallel tool execution
    print("\n" + "=" * 60)
    print("5. Parallel tool execution")
    print("=" * 60)

    tool_calls = [
        ("example-server_fetch_weather", {"location": "Tokyo"}),
        ("example-server_fetch_url", {"url": "https://example.com"}),
        ("example-server_execute_query", {"query": "SELECT * FROM users"}),
    ]

    print(f"\nExecuting {len(tool_calls)} MCP tools in parallel...")
    results = await manager.invoke_parallel(tool_calls)

    for i, (tool_name, params) in enumerate(tool_calls):
        result = results[i]
        print(f"\n[{i+1}] {tool_name}")
        if result.error:
            print(f"    Error: {result.error}")
        else:
            print(f"    Output: {result.output[:100]}")


if __name__ == "__main__":
    asyncio.run(main())
