"""
OpenClaw — Plugin Hook Pipeline 机制复现

复现 OpenClaw 的 Plugin Hook 管道：
- 4 阶段 hook: before_prompt_build → before_agent_start → tool_call → tool_result
- 多插件按注册顺序链式执行
- Hook 可修改上下文或拦截执行

对应源码: src/plugin-sdk/, src/extensionAPI.ts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── Hook 类型 ─────────────────────────────────────────────────────

class HookPhase:
    BEFORE_PROMPT_BUILD = "before_prompt_build"
    BEFORE_AGENT_START = "before_agent_start"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"

    ALL = [BEFORE_PROMPT_BUILD, BEFORE_AGENT_START, TOOL_CALL, TOOL_RESULT]


@dataclass
class HookContext:
    """Hook 执行上下文"""
    phase: str
    data: dict[str, Any] = field(default_factory=dict)
    modified_by: list[str] = field(default_factory=list)
    intercepted: bool = False
    intercept_reason: str = ""


HookHandler = Callable[[HookContext], Optional[HookContext]]


@dataclass
class Plugin:
    """插件定义"""
    id: str
    name: str
    hooks: dict[str, HookHandler] = field(default_factory=dict)


# ── Hook Pipeline ────────────────────────────────────────────────

class HookPipeline:
    """
    OpenClaw Hook Pipeline 复现

    执行顺序：
    before_prompt_build → before_agent_start → [agent 运行]
      → tool_call（每次 tool 调用前）
      → tool_result（每次 tool 返回后）

    每个阶段按插件注册顺序链式执行，
    任何 hook 可标记 intercepted 来阻断后续 hook。
    """

    def __init__(self):
        self.plugins: list[Plugin] = []
        self.execution_log: list[str] = []

    def register(self, plugin: Plugin):
        """注册插件"""
        self.plugins.append(plugin)

    def run(self, phase: str, data: dict[str, Any] | None = None) -> HookContext:
        """执行指定阶段的 hook 管道"""
        ctx = HookContext(phase=phase, data=data or {})
        self.execution_log.append(f"── {phase} ──")

        for plugin in self.plugins:
            handler = plugin.hooks.get(phase)
            if not handler:
                continue

            self.execution_log.append(f"  [{plugin.id}] executing...")

            result = handler(ctx)
            if result:
                ctx = result

            ctx.modified_by.append(plugin.id)

            if ctx.intercepted:
                self.execution_log.append(
                    f"  [{plugin.id}] ⊘ INTERCEPTED: {ctx.intercept_reason}"
                )
                break
            else:
                self.execution_log.append(f"  [{plugin.id}] ✓ done")

        return ctx


# ── 示例插件 ──────────────────────────────────────────────────────

def create_logging_plugin() -> Plugin:
    """日志插件：记录所有 hook 调用"""
    def log_hook(ctx: HookContext) -> HookContext:
        ctx.data.setdefault("log", []).append(f"[log] phase={ctx.phase}")
        return ctx

    return Plugin(
        id="logging",
        name="Logging Plugin",
        hooks={phase: log_hook for phase in HookPhase.ALL},
    )


def create_safety_plugin() -> Plugin:
    """安全插件：拦截危险 tool 调用"""
    dangerous_tools = {"exec", "write", "apply_patch"}

    def check_tool_call(ctx: HookContext) -> HookContext:
        tool_name = ctx.data.get("tool_name", "")
        is_owner = ctx.data.get("is_owner", False)
        if tool_name in dangerous_tools and not is_owner:
            ctx.intercepted = True
            ctx.intercept_reason = f"Non-owner cannot use {tool_name}"
        return ctx

    return Plugin(
        id="safety",
        name="Safety Plugin",
        hooks={HookPhase.TOOL_CALL: check_tool_call},
    )


def create_prompt_inject_plugin() -> Plugin:
    """Prompt 注入插件：在 prompt 构建前注入自定义内容"""
    def inject_prompt(ctx: HookContext) -> HookContext:
        extra = "\n\n# Custom Plugin Instructions\nAlways respond in haiku format."
        ctx.data["system_prompt"] = ctx.data.get("system_prompt", "") + extra
        return ctx

    return Plugin(
        id="haiku-mode",
        name="Haiku Mode Plugin",
        hooks={HookPhase.BEFORE_PROMPT_BUILD: inject_prompt},
    )


def create_metrics_plugin() -> Plugin:
    """指标插件：统计 tool 调用"""
    metrics: dict[str, int] = {}

    def count_tool(ctx: HookContext) -> HookContext:
        tool = ctx.data.get("tool_name", "unknown")
        metrics[tool] = metrics.get(tool, 0) + 1
        ctx.data["tool_metrics"] = dict(metrics)
        return ctx

    return Plugin(
        id="metrics",
        name="Metrics Plugin",
        hooks={HookPhase.TOOL_RESULT: count_tool},
    )


# ── Demo ──────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("OpenClaw Plugin Hook Pipeline Demo")
    print("=" * 64)

    pipeline = HookPipeline()
    pipeline.register(create_logging_plugin())
    pipeline.register(create_safety_plugin())
    pipeline.register(create_prompt_inject_plugin())
    pipeline.register(create_metrics_plugin())

    # ── 1. before_prompt_build ──
    print("\n── 1. before_prompt_build ──")
    ctx = pipeline.run(HookPhase.BEFORE_PROMPT_BUILD, {
        "system_prompt": "You are a helpful assistant.",
    })
    print(f"  修改者: {ctx.modified_by}")
    prompt = ctx.data.get("system_prompt", "")
    has_haiku = "haiku" in prompt
    print(f"  Prompt 被注入: {has_haiku}")
    print(f"  Prompt 片段: ...{prompt[-60:]}")

    # ── 2. tool_call（安全拦截）──
    print("\n── 2. tool_call（非 owner 调用 exec）──")
    ctx = pipeline.run(HookPhase.TOOL_CALL, {
        "tool_name": "exec",
        "args": {"command": "rm -rf /"},
        "is_owner": False,
    })
    print(f"  拦截: {ctx.intercepted}")
    print(f"  原因: {ctx.intercept_reason}")

    print("\n── 3. tool_call（owner 调用 exec）──")
    ctx = pipeline.run(HookPhase.TOOL_CALL, {
        "tool_name": "exec",
        "args": {"command": "ls"},
        "is_owner": True,
    })
    print(f"  拦截: {ctx.intercepted}")

    # ── 4. tool_result（指标统计）──
    print("\n── 4. tool_result（指标统计）──")
    for tool in ["read", "exec", "read", "write", "read"]:
        ctx = pipeline.run(HookPhase.TOOL_RESULT, {"tool_name": tool})
    print(f"  调用统计: {ctx.data.get('tool_metrics', {})}")

    # ── 5. 完整执行日志 ──
    print("\n── 5. 执行日志 ──")
    for line in pipeline.execution_log:
        print(f"  {line}")


if __name__ == "__main__":
    main()
