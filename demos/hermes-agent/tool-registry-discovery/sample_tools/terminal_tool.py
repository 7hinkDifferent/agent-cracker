from tool_registry import registry


registry.register(
    name="terminal",
    toolset="terminal",
    description="Run a shell command",
    handler=lambda args: f"$ {args.get('command', 'echo demo')} -> ok",
)
