from tool_registry import registry


registry.register(
    name="memory",
    toolset="memory",
    description="Store a durable fact",
    handler=lambda args: f"saved memory: {args.get('fact', '')}",
)
