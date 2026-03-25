#!/usr/bin/env python3
"""
Prompt Assembly — Minimal reproduction of Gemini CLI's dynamic prompt assembly

This demo shows how Gemini CLI builds the complete prompt sent to LLM:

1. Start with base system prompt
2. Inject tool definitions (as function calling schema)
3. Add MCP prompts (from PromptRegistry)
4. Add file context (code snippets provided by user)
5. Add conversation history
6. Estimate token count and truncate if needed

Key insights:
- Prompts are assembled dynamically, not hardcoded
- Each component can be modified independently
- Token counting ensures we don't overflow context window
- MCP allows third-party prompt injection
"""

import json
from dataclasses import dataclass
from typing import Optional
import logging


# ============================================================================
# Prompt Building Blocks
# ============================================================================

@dataclass
class ToolDefinition:
    """Tool definition for function calling"""
    name: str
    description: str
    parameters: dict


@dataclass
class MCPPrompt:
    """Prompt provided by an MCP server"""
    name: str
    description: str
    content: str
    server_name: str = ""


@dataclass
class FileContext:
    """Code file context"""
    path: str
    content: str
    language: str = "python"


@dataclass
class ConversationTurn:
    """Single turn in conversation"""
    role: str  # "user" or "assistant"
    content: str


# ============================================================================
# Prompt Assembly Logic
# ============================================================================

def estimate_tokens(text: str) -> int:
    """
    Rough token estimation (1 token ≈ 4 characters for English).
    Real implementation uses actual tokenizer.
    """
    return len(text) // 4


class PromptAssembler:
    """Assembles the complete prompt for LLM"""

    def __init__(self, max_tokens: int = 100000):
        self.max_tokens = max_tokens
        self.logger = logging.getLogger("PromptAssembler")

    def assemble(
        self,
        user_query: str,
        tools: list[ToolDefinition],
        mcp_prompts: list[MCPPrompt],
        file_contexts: list[FileContext],
        conversation_history: list[ConversationTurn],
    ) -> str:
        """
        Assemble complete prompt from components.

        Assembly order matters:
        1. Base system prompt (highest priority)
        2. Tool definitions (required for agent to act)
        3. MCP prompts (augmentation)
        4. File context (input data)
        5. Conversation history (recent context)
        """
        parts = []

        # 1. Base system prompt
        base_system = self._build_base_system_prompt()
        parts.append(("system", base_system))

        # 2. Tool definitions
        tools_prompt = self._build_tools_prompt(tools)
        parts.append(("tools", tools_prompt))

        # 3. MCP prompts
        mcp_section = self._build_mcp_section(mcp_prompts)
        if mcp_section:
            parts.append(("mcp", mcp_section))

        # 4. File context
        context_section = self._build_context_section(file_contexts)
        if context_section:
            parts.append(("context", context_section))

        # 5. Conversation history
        history_section = self._build_history_section(conversation_history)
        if history_section:
            parts.append(("history", history_section))

        # 6. Current user query
        parts.append(("query", user_query))

        # Assemble and truncate to fit token limit
        return self._assemble_and_truncate(parts)

    def _build_base_system_prompt(self) -> str:
        """Base system prompt for the LLM"""
        return """You are Gemini CLI, an AI coding assistant running in the terminal.

Your role:
- Help users write, review, and debug code
- Execute tools to read files, run commands, search codebases
- Provide clear explanations and ask for clarification when needed
- Respect user choices and safety constraints

Capabilities:
- You have access to tools listed below
- You can read/write files, execute shell commands, search code
- You can see file context and understand project structure
- You operate in a terminal environment

Guidelines:
- Be concise and direct
- Explain your reasoning for tool calls
- Ask before making major changes
- Handle errors gracefully
"""

    def _build_tools_prompt(self, tools: list[ToolDefinition]) -> str:
        """Build section describing available tools"""
        if not tools:
            return "(no tools available)"

        lines = ["Available tools:\n"]
        for tool in tools:
            lines.append(f"- {tool.name}: {tool.description}")

        lines.append("\nTool parameters:")
        for tool in tools:
            params = tool.parameters.get("properties", {})
            if params:
                lines.append(f"\n{tool.name}:")
                for param_name, param_spec in params.items():
                    lines.append(
                        f"  - {param_name} ({param_spec.get('type', 'any')}): "
                        f"{param_spec.get('description', '')}"
                    )

        return "\n".join(lines)

    def _build_mcp_section(self, mcp_prompts: list[MCPPrompt]) -> str:
        """Build section with MCP-provided prompts"""
        if not mcp_prompts:
            return ""

        lines = ["=== Prompts from MCP Servers ===\n"]
        for prompt in mcp_prompts:
            lines.append(f"[{prompt.server_name}] {prompt.name}")
            lines.append(f"Description: {prompt.description}")
            lines.append(f"Content:\n{prompt.content}\n")

        return "\n".join(lines)

    def _build_context_section(self, file_contexts: list[FileContext]) -> str:
        """Build section with file context"""
        if not file_contexts:
            return ""

        lines = ["=== File Context ===\n"]
        for fc in file_contexts:
            lines.append(f"File: {fc.path} ({fc.language})")
            lines.append("---")
            # Truncate large files
            content = fc.content
            if len(content) > 2000:
                content = content[:2000] + "\n... (truncated)"
            lines.append(content)
            lines.append("---\n")

        return "\n".join(lines)

    def _build_history_section(
        self, conversation_history: list[ConversationTurn]
    ) -> str:
        """Build section with recent conversation history"""
        if not conversation_history:
            return ""

        lines = ["=== Conversation History ===\n"]
        for turn in conversation_history:
            role = turn.role.upper()
            lines.append(f"{role}:")
            lines.append(turn.content)
            lines.append("")

        return "\n".join(lines)

    def _assemble_and_truncate(self, parts: list[tuple[str, str]]) -> str:
        """
        Assemble all parts and truncate to fit token limit.
        Prioritize earlier parts (system > tools > mcp > context > history).
        """
        assembled = "\n\n".join([content for _, content in parts])
        tokens = estimate_tokens(assembled)

        if tokens <= self.max_tokens:
            self.logger.info(f"Assembled prompt: {tokens}/{self.max_tokens} tokens")
            return assembled

        # Truncate from end (history first, then context)
        self.logger.warning(
            f"Prompt exceeds limit ({tokens}/{self.max_tokens}), truncating..."
        )

        # Try removing each section from the end
        for i in range(len(parts) - 1, -1, -1):
            parts_to_keep = parts[:i]
            if parts_to_keep:
                assembled = "\n\n".join([content for _, content in parts_to_keep])
                tokens = estimate_tokens(assembled)
                if tokens <= self.max_tokens:
                    self.logger.info(f"Truncated to {tokens}/{self.max_tokens} tokens")
                    return assembled

        # Fallback: just return system prompt
        return parts[0][1] if parts else "(empty prompt)"


# ============================================================================
# Example Usage
# ============================================================================

def main():
    """Demonstrate prompt assembly"""

    logging.basicConfig(level=logging.INFO)

    # Create assembler
    assembler = PromptAssembler(max_tokens=5000)

    # Define tools
    tools = [
        ToolDefinition(
            name="read-file",
            description="Read a file",
            parameters={
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                }
            },
        ),
        ToolDefinition(
            name="shell",
            description="Execute a shell command",
            parameters={
                "properties": {
                    "command": {"type": "string", "description": "Command to run"}
                }
            },
        ),
    ]

    # MCP prompts
    mcp_prompts = [
        MCPPrompt(
            name="code-style",
            description="Code style guide from cpp-server",
            content="Follow PEP 8 for Python. Use type hints.",
            server_name="cpp-server",
        ),
    ]

    # File context
    file_contexts = [
        FileContext(
            path="main.py",
            content="""def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(hello("World"))
""",
            language="python",
        ),
    ]

    # Conversation history
    conversation_history = [
        ConversationTurn(
            role="user",
            content="What does the hello function do?",
        ),
        ConversationTurn(
            role="assistant",
            content="The hello function takes a name and returns a greeting string.",
        ),
    ]

    # User query
    user_query = "Now add a goodbye function."

    # Assembly
    print("=" * 60)
    print("PROMPT ASSEMBLY DEMO")
    print("=" * 60)

    prompt = assembler.assemble(
        user_query=user_query,
        tools=tools,
        mcp_prompts=mcp_prompts,
        file_contexts=file_contexts,
        conversation_history=conversation_history,
    )

    print("\n" + "=" * 60)
    print("ASSEMBLED PROMPT")
    print("=" * 60)
    print(prompt)

    # Token count
    tokens = estimate_tokens(prompt)
    print(f"\n✓ Final prompt size: {tokens} tokens (limit: 5000)")


if __name__ == "__main__":
    main()
