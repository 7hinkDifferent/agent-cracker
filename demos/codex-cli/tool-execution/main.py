"""
Codex CLI Tool Execution Demo

复现 Codex CLI 的 Tool 沙箱执行管线：
- Tool 路由（shell / apply_patch / search / MCP）
- 三级审批（Suggest / Auto-Edit / Full-Auto）
- 沙箱包装（Seatbelt / Landlock 模拟）
- 完整执行管线

Run: uv run python main.py
"""

from executor import (
    ToolRouter, ToolCall, ToolResult, ToolType,
    ApprovalMode, ApprovalStatus, SandboxConfig,
    evaluate_approval, SAFE_COMMANDS, BANNED_COMMANDS,
)


def demo_tool_routing():
    """演示 tool call 类型路由。"""
    print("=" * 60)
    print("Demo 1: Tool Routing (tool call 分发)")
    print("=" * 60)

    router = ToolRouter()

    items = [
        {"name": "shell", "id": "call_1", "arguments": {"command": "ls -la"}},
        {"name": "apply_patch", "id": "call_2", "arguments": {"diff": "--- a/f\n+++ b/f"}},
        {"name": "search", "id": "call_3", "arguments": {"pattern": "TODO"}},
        {"name": "mcp_server__tool", "id": "call_4", "arguments": {"input": "data"}},
        {"name": "unknown_tool", "id": "call_5", "arguments": {}},
    ]

    for item in items:
        tc = router.build_tool_call(item)
        if tc:
            print(f"\n  {item['name']:25s} → {tc.tool_type.value}")
        else:
            print(f"\n  {item['name']:25s} → (not recognized)")


def demo_approval_modes():
    """演示三级审批策略。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Three-Tier Approval (三级审批)")
    print("=" * 60)

    tools = [
        ToolCall(ToolType.SHELL, "shell", {"command": "ls -la"}),
        ToolCall(ToolType.SHELL, "shell", {"command": "npm install"}),
        ToolCall(ToolType.SHELL, "shell", {"command": "rm -rf /"}),
        ToolCall(ToolType.APPLY_PATCH, "apply_patch", {"diff": "..."}),
        ToolCall(ToolType.SEARCH, "search", {"pattern": "TODO"}),
    ]

    for mode in ApprovalMode:
        print(f"\n  ── {mode.value} mode ──")
        for tc in tools:
            status = evaluate_approval(tc, mode)
            cmd = tc.arguments.get("command", tc.arguments.get("pattern", tc.arguments.get("diff", "")[:20]))
            icon = {"approved": "✓", "needs_approval": "?", "forbidden": "✗"}[status.value]
            print(f"    {icon} {tc.tool_type.value:12s} {cmd:25s} → {status.value}")


def demo_sandbox():
    """演示沙箱配置。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Sandbox Configuration (沙箱策略)")
    print("=" * 60)

    configs = [
        ("默认沙箱", SandboxConfig()),
        ("宽松沙箱", SandboxConfig(writable_dirs=[".", "/tmp"], network_allowed=True)),
        ("禁用沙箱", SandboxConfig(enabled=False)),
    ]

    for label, config in configs:
        print(f"\n  ── {label} ──")
        print(f"    enabled:   {config.enabled}")
        print(f"    writable:  {config.writable_dirs}")
        print(f"    readable:  {config.readable_dirs}")
        print(f"    network:   {config.network_allowed}")


def demo_full_pipeline():
    """演示完整执行管线。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Full Execution Pipeline (完整管线)")
    print("=" * 60)

    # Auto-Edit 模式：安全命令放行，危险命令审批/禁止
    approval_log = []

    def mock_approval(tc):
        approval_log.append(tc.arguments.get("command", ""))
        return True  # 模拟用户批准

    router = ToolRouter(
        cwd=".",
        approval_mode=ApprovalMode.AUTO_EDIT,
        approval_callback=mock_approval,
    )

    items = [
        {"name": "shell", "id": "1", "arguments": {"command": "echo hello"}},
        {"name": "shell", "id": "2", "arguments": {"command": "pip install flask"}},
        {"name": "shell", "id": "3", "arguments": {"command": "rm -rf /"}},
        {"name": "search", "id": "4", "arguments": {"pattern": "def main"}},
        {"name": "apply_patch", "id": "5", "arguments": {"diff": "+new line", "path": "main.py"}},
    ]

    print(f"\n  Mode: {router.approval_mode.value}")
    print()

    for item in items:
        tc = router.build_tool_call(item)
        if not tc:
            continue

        result = router.execute(tc)
        cmd = tc.arguments.get("command", tc.arguments.get("pattern", ""))
        status_icon = {
            "approved": "✓",
            "needs_approval": "?",
            "forbidden": "✗",
        }[result.approval_status.value]

        sandbox_tag = " [sandboxed]" if result.sandboxed else ""
        output_preview = result.output[:60].replace("\n", "\\n")

        print(f"  {status_icon} {tc.tool_type.value:12s} {cmd:30s}")
        print(f"    exit={result.exit_code} {sandbox_tag}")
        print(f"    output: \"{output_preview}\"")
        print()

    if approval_log:
        print(f"  User approved: {approval_log}")


def demo_safe_commands():
    """展示安全和禁止命令列表。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Command Lists (安全/禁止命令)")
    print("=" * 60)

    print(f"\n  Safe commands (auto-approve):")
    for cmd in SAFE_COMMANDS[:8]:
        print(f"    ✓ {cmd}")
    print(f"    ... ({len(SAFE_COMMANDS)} total)")

    print(f"\n  Banned commands (always reject):")
    for cmd in BANNED_COMMANDS[:5]:
        print(f"    ✗ {cmd}")
    print(f"    ... ({len(BANNED_COMMANDS)} total)")


def main():
    print("Codex CLI Tool Execution Demo")
    print("Reproduces the tool routing + approval + sandbox pipeline\n")

    demo_tool_routing()
    demo_approval_modes()
    demo_sandbox()
    demo_full_pipeline()
    demo_safe_commands()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("\n  Tool execution pipeline:")
    print("    1. build_tool_call() — classify tool type")
    print("    2. evaluate_approval() — check ExecPolicy")
    print("    3. sandbox_wrap() — apply Seatbelt/Landlock")
    print("    4. execute — run and capture output")
    print("\n  Approval modes:")
    print("    - Suggest:   everything needs approval")
    print("    - Auto-Edit: file ops auto, shell needs approval")
    print("    - Full-Auto: only banned commands blocked")
    print("\n✓ Demo complete!")


if __name__ == "__main__":
    main()
