"""
Pi-Agent Extension Hooks Demo

复现 Pi-Agent 的深度扩展系统：
- 生命周期钩子（input/beforeAgentStart/context/toolCall/toolResult/turnStart/turnEnd）
- 动态 tool 注册
- 动态 command 注册
- Hook 拦截与转换

Run: uv run python main.py
"""

from dataclasses import dataclass, field
from typing import Callable, Any


# ── 扩展接口 ──────────────────────────────────────────────────────

HOOK_TYPES = [
    "input",              # 用户输入前（可拦截/转换）
    "beforeAgentStart",   # Agent 思考前（可注入 messages、改写 system prompt）
    "context",            # 上下文变换（可裁剪/富化消息）
    "toolCall",           # Tool 执行前
    "toolResult",         # Tool 执行后
    "turnStart",          # 每轮开始
    "turnEnd",            # 每轮结束
    "resourcesDiscover",  # 资源发现（注册 provider、tool、command）
]


@dataclass
class HookResult:
    """钩子执行结果。"""
    modified: bool = False
    data: Any = None
    cancelled: bool = False  # 拦截/取消


@dataclass
class Extension:
    """扩展定义，对应 pi-agent 的扩展注册机制。"""
    name: str
    description: str = ""
    hooks: dict[str, Callable] = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)
    commands: list[dict] = field(default_factory=list)


# ── 扩展管理器 ────────────────────────────────────────────────────

class ExtensionManager:
    """
    扩展管理器，管理扩展注册和钩子调用。
    对应 pi-agent 的 Extension 系统。
    """

    def __init__(self):
        self._extensions: list[Extension] = []
        self._hooks: dict[str, list[tuple[str, Callable]]] = {h: [] for h in HOOK_TYPES}
        self._tools: dict[str, dict] = {}
        self._commands: dict[str, dict] = {}

    def register(self, ext: Extension):
        """注册扩展。"""
        self._extensions.append(ext)

        # 注册钩子
        for hook_type, handler in ext.hooks.items():
            if hook_type in self._hooks:
                self._hooks[hook_type].append((ext.name, handler))

        # 注册工具
        for tool in ext.tools:
            self._tools[tool["name"]] = {**tool, "_extension": ext.name}

        # 注册命令
        for cmd in ext.commands:
            self._commands[cmd["name"]] = {**cmd, "_extension": ext.name}

    async def run_hook(self, hook_type: str, data: Any = None) -> HookResult:
        """
        运行指定类型的所有钩子。
        钩子按注册顺序执行，任一返回 cancelled=True 则中断。
        """
        result = HookResult(data=data)

        for ext_name, handler in self._hooks.get(hook_type, []):
            hook_result = handler(data)
            if isinstance(hook_result, HookResult):
                if hook_result.cancelled:
                    return hook_result
                if hook_result.modified:
                    result.modified = True
                    result.data = hook_result.data
                    data = hook_result.data  # 传递给下一个钩子

        return result

    def get_tools(self) -> list[dict]:
        """获取所有扩展注册的工具。"""
        return list(self._tools.values())

    def get_commands(self) -> list[dict]:
        """获取所有扩展注册的命令。"""
        return list(self._commands.values())

    def list_extensions(self) -> list[str]:
        """列出所有已注册扩展。"""
        return [ext.name for ext in self._extensions]


# ── Demo 扩展 ─────────────────────────────────────────────────────

def create_safety_extension() -> Extension:
    """安全扩展：拦截危险命令。"""
    BLOCKED = ["rm -rf", "sudo rm", "mkfs", "dd if=", ":(){:|:&};:"]

    def on_tool_call(data):
        if data and data.get("name") == "bash":
            cmd = data.get("arguments", {}).get("command", "")
            for blocked in BLOCKED:
                if blocked in cmd:
                    return HookResult(
                        cancelled=True,
                        data={"reason": f"Blocked dangerous command: '{blocked}'"},
                    )
        return HookResult()

    return Extension(
        name="safety-guard",
        description="Block dangerous shell commands",
        hooks={"toolCall": on_tool_call},
    )


def create_logging_extension() -> Extension:
    """日志扩展：记录所有事件。"""
    log: list[str] = []

    def on_turn_start(data):
        log.append(f"[turn_start] turn={len(log) + 1}")
        return HookResult()

    def on_turn_end(data):
        log.append(f"[turn_end]")
        return HookResult()

    def on_tool_result(data):
        tool = data.get("name", "?") if data else "?"
        log.append(f"[tool_result] {tool}")
        return HookResult()

    ext = Extension(
        name="logger",
        description="Log all agent events",
        hooks={
            "turnStart": on_turn_start,
            "turnEnd": on_turn_end,
            "toolResult": on_tool_result,
        },
    )
    ext._log = log  # 暴露给 demo
    return ext


def create_context_extension() -> Extension:
    """上下文扩展：注入额外信息到 system prompt。"""
    def on_before_agent_start(data):
        messages = data or []
        injection = {
            "role": "system",
            "content": "[Extension: project-rules] Always use TypeScript. Never use var.",
        }
        return HookResult(modified=True, data=messages + [injection])

    return Extension(
        name="project-rules",
        description="Inject project-specific rules",
        hooks={"beforeAgentStart": on_before_agent_start},
    )


def create_custom_tools_extension() -> Extension:
    """自定义工具扩展：动态注册新工具。"""
    def jira_lookup(args):
        ticket = args.get("ticket_id", "UNKNOWN")
        return f"JIRA {ticket}: [Bug] Login page crashes on Safari. Priority: High."

    def run_tests(args):
        pattern = args.get("pattern", "*")
        return f"Running tests matching '{pattern}'... 12 passed, 0 failed."

    return Extension(
        name="dev-tools",
        description="Developer productivity tools",
        tools=[
            {
                "name": "jira_lookup",
                "description": "Look up a JIRA ticket",
                "execute": jira_lookup,
                "parameters": {"ticket_id": "string"},
            },
            {
                "name": "run_tests",
                "description": "Run test suite",
                "execute": run_tests,
                "parameters": {"pattern": "string"},
            },
        ],
        commands=[
            {
                "name": "/test",
                "description": "Run tests",
                "handler": lambda args: f"Tests: {run_tests(args)}",
            },
            {
                "name": "/ticket",
                "description": "Look up JIRA ticket",
                "handler": lambda args: f"Ticket: {jira_lookup(args)}",
            },
        ],
    )


# ── Demo 运行 ─────────────────────────────────────────────────────

import asyncio


async def demo_lifecycle_hooks():
    """演示生命周期钩子。"""
    print("=" * 60)
    print("Demo 1: Lifecycle Hooks (生命周期钩子)")
    print("=" * 60)

    mgr = ExtensionManager()

    # 注册扩展
    logging_ext = create_logging_extension()
    mgr.register(logging_ext)
    mgr.register(create_context_extension())

    print(f"\n  Registered: {mgr.list_extensions()}")
    print(f"\n  Simulating agent lifecycle:")

    # 模拟一轮 agent 执行
    print(f"\n  ── beforeAgentStart ──")
    result = await mgr.run_hook("beforeAgentStart", [{"role": "system", "content": "You are helpful."}])
    print(f"    Modified: {result.modified}")
    if result.modified:
        print(f"    Messages now: {len(result.data)} (injected project rules)")

    print(f"\n  ── turnStart ──")
    await mgr.run_hook("turnStart")

    print(f"\n  ── toolResult ──")
    await mgr.run_hook("toolResult", {"name": "read", "result": "file content..."})

    print(f"\n  ── turnEnd ──")
    await mgr.run_hook("turnEnd")

    print(f"\n  Log entries: {logging_ext._log}")


async def demo_tool_call_interception():
    """演示 toolCall 钩子拦截危险命令。"""
    print(f"\n{'=' * 60}")
    print("Demo 2: Tool Call Interception (工具拦截)")
    print("=" * 60)

    mgr = ExtensionManager()
    mgr.register(create_safety_extension())

    cases = [
        {"name": "bash", "arguments": {"command": "ls -la"}},
        {"name": "bash", "arguments": {"command": "rm -rf /"}},
        {"name": "bash", "arguments": {"command": "cat main.py"}},
        {"name": "bash", "arguments": {"command": "sudo rm -rf /tmp"}},
        {"name": "read", "arguments": {"path": "main.py"}},
    ]

    for tool_call in cases:
        result = await mgr.run_hook("toolCall", tool_call)
        cmd = tool_call.get("arguments", {}).get("command", tool_call.get("arguments", {}).get("path", ""))
        if result.cancelled:
            reason = result.data.get("reason", "unknown")
            print(f"\n  ✗ {tool_call['name']}(\"{cmd}\")")
            print(f"    BLOCKED: {reason}")
        else:
            print(f"\n  ✓ {tool_call['name']}(\"{cmd}\")")
            print(f"    Allowed")


async def demo_dynamic_tools():
    """演示动态工具注册。"""
    print(f"\n{'=' * 60}")
    print("Demo 3: Dynamic Tool Registration (动态工具)")
    print("=" * 60)

    mgr = ExtensionManager()
    dev_ext = create_custom_tools_extension()
    mgr.register(dev_ext)

    print(f"\n  Extension: {dev_ext.name}")

    # 列出注册的工具
    tools = mgr.get_tools()
    print(f"\n  Registered tools ({len(tools)}):")
    for tool in tools:
        print(f"    - {tool['name']}: {tool['description']} (from {tool['_extension']})")

    # 执行动态工具
    print(f"\n  Executing dynamic tools:")
    for tool in tools:
        result = tool["execute"]({"ticket_id": "PROJ-123", "pattern": "test_auth*"})
        print(f"    {tool['name']} → \"{result}\"")

    # 列出注册的命令
    commands = mgr.get_commands()
    print(f"\n  Registered commands ({len(commands)}):")
    for cmd in commands:
        print(f"    - {cmd['name']}: {cmd['description']}")


async def demo_hook_chain():
    """演示多扩展的钩子链式执行。"""
    print(f"\n{'=' * 60}")
    print("Demo 4: Hook Chain (多扩展链式执行)")
    print("=" * 60)

    mgr = ExtensionManager()

    # 创建两个修改 input 的扩展
    def trim_input(data):
        if isinstance(data, str):
            return HookResult(modified=True, data=data.strip())
        return HookResult()

    def add_prefix(data):
        if isinstance(data, str):
            return HookResult(modified=True, data=f"[processed] {data}")
        return HookResult()

    mgr.register(Extension(name="trimmer", hooks={"input": trim_input}))
    mgr.register(Extension(name="prefixer", hooks={"input": add_prefix}))

    # 链式执行
    original = "  Hello, please help me  "
    result = await mgr.run_hook("input", original)

    print(f"\n  Original:  \"{original}\"")
    print(f"  After chain: \"{result.data}\"")
    print(f"  Modified: {result.modified}")
    print(f"\n  Chain order: trimmer → prefixer")
    print(f"  Each hook receives the output of the previous one")


async def demo_full_extension():
    """演示完整的扩展系统。"""
    print(f"\n{'=' * 60}")
    print("Demo 5: Full Extension System (完整扩展)")
    print("=" * 60)

    mgr = ExtensionManager()
    mgr.register(create_safety_extension())
    mgr.register(create_logging_extension())
    mgr.register(create_context_extension())
    mgr.register(create_custom_tools_extension())

    print(f"\n  Extensions: {mgr.list_extensions()}")
    print(f"  Dynamic tools: {[t['name'] for t in mgr.get_tools()]}")
    print(f"  Custom commands: {[c['name'] for c in mgr.get_commands()]}")

    # 统计钩子
    hook_counts = {}
    for hook_type in HOOK_TYPES:
        count = len(mgr._hooks[hook_type])
        if count > 0:
            hook_counts[hook_type] = count
    print(f"  Active hooks: {hook_counts}")

    print(f"\n  ── Extension capabilities ──")
    print(f"  {'Extension':<20s} {'Hooks':<30s} {'Tools':<15s} {'Commands':<10s}")
    print(f"  {'─' * 75}")
    for ext in mgr._extensions:
        hooks = ", ".join(ext.hooks.keys()) or "-"
        tools = ", ".join(t["name"] for t in ext.tools) or "-"
        cmds = ", ".join(c["name"] for c in ext.commands) or "-"
        print(f"  {ext.name:<20s} {hooks:<30s} {tools:<15s} {cmds:<10s}")


async def async_main():
    print("Pi-Agent Extension Hooks Demo")
    print("Reproduces the lifecycle hook and dynamic registration system\n")

    await demo_lifecycle_hooks()
    await demo_tool_call_interception()
    await demo_dynamic_tools()
    await demo_hook_chain()
    await demo_full_extension()

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print("\n  Extension system capabilities:")
    print("    1. Lifecycle hooks (8 hook points)")
    print("    2. Tool call interception (cancel dangerous operations)")
    print("    3. Dynamic tool registration (add tools at runtime)")
    print("    4. Dynamic command registration (add slash commands)")
    print("    5. Hook chaining (multiple extensions, sequential execution)")
    print("\n  Hook points:")
    for h in HOOK_TYPES:
        print(f"    - {h}")
    print("\n✓ Demo complete!")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
