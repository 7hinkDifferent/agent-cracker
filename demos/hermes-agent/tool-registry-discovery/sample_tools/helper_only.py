def helper_format(name: str) -> str:
    return f"helper for {name}"


def register_later(registry):
    registry.register(
        name="hidden",
        toolset="debug",
        description="Should not be discovered because register is not top-level",
        handler=lambda args: helper_format(args.get('name', 'anon')),
    )
