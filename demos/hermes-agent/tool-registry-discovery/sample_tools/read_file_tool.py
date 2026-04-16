from tool_registry import registry


registry.register(
    name="read_file",
    toolset="file",
    description="Read a text file",
    handler=lambda args: f"reading {args.get('path', '?')}",
)
