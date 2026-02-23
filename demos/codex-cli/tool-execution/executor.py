"""
Codex CLI Tool Execution 核心模块。

提供 Tool 路由 + 审批 + 沙箱执行管线，可被 mini-codex 导入复用。

核心接口:
  - ToolRouter: Tool call 分发器
  - ExecPolicy: 审批策略引擎（复用 approval-policy demo）
  - SandboxWrapper: 沙箱包装（模拟 Seatbelt/Landlock）
"""

import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum


# ── Tool 类型 ─────────────────────────────────────────────────────

class ToolType(Enum):
    SHELL = "shell"
    APPLY_PATCH = "apply_patch"
    SEARCH = "search"
    MCP = "mcp"


class ApprovalStatus(Enum):
    APPROVED = "approved"
    NEEDS_APPROVAL = "needs_approval"
    FORBIDDEN = "forbidden"


# ── Tool Call ─────────────────────────────────────────────────────

@dataclass
class ToolCall:
    tool_type: ToolType
    name: str
    arguments: dict = field(default_factory=dict)
    call_id: str = ""


@dataclass
class ToolResult:
    output: str = ""
    exit_code: int = 0
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED
    sandboxed: bool = False
    blocked_reason: str = ""


# ── 审批策略 ──────────────────────────────────────────────────────

# 安全命令前缀（自动放行）
SAFE_COMMANDS = [
    "cat ", "ls ", "head ", "tail ", "wc ", "echo ",
    "pwd", "whoami", "date", "uname",
    "grep ", "rg ", "find ", "which ",
    "git status", "git diff", "git log",
    "python --version", "node --version", "rustc --version",
]

# 禁止命令（永远拒绝）
BANNED_COMMANDS = [
    "rm -rf /", "mkfs", ":(){:|:&};:", "dd if=/dev/zero",
    "chmod -R 777 /", "curl | sh", "wget | sh",
]


class ApprovalMode(Enum):
    SUGGEST = "suggest"      # 每个操作都需审批
    AUTO_EDIT = "auto_edit"  # 文件编辑自动放行，shell 需审批
    FULL_AUTO = "full_auto"  # 全部自动放行（仅禁止命令拦截）


def evaluate_approval(
    tool_call: ToolCall,
    mode: ApprovalMode,
) -> ApprovalStatus:
    """
    评估 tool call 的审批状态。
    对应 codex-cli 的 ExecPolicy 规则引擎。
    """
    # 禁止命令 → 永远拒绝
    if tool_call.tool_type == ToolType.SHELL:
        cmd = tool_call.arguments.get("command", "")
        for banned in BANNED_COMMANDS:
            if banned in cmd:
                return ApprovalStatus.FORBIDDEN

    # Full-Auto → 除禁止外全部放行
    if mode == ApprovalMode.FULL_AUTO:
        return ApprovalStatus.APPROVED

    # Auto-Edit → 文件操作放行，shell 需审批
    if mode == ApprovalMode.AUTO_EDIT:
        if tool_call.tool_type in (ToolType.APPLY_PATCH, ToolType.SEARCH):
            return ApprovalStatus.APPROVED
        if tool_call.tool_type == ToolType.SHELL:
            cmd = tool_call.arguments.get("command", "")
            for safe in SAFE_COMMANDS:
                if cmd.strip().startswith(safe):
                    return ApprovalStatus.APPROVED
            return ApprovalStatus.NEEDS_APPROVAL

    # Suggest → 全部需审批
    if mode == ApprovalMode.SUGGEST:
        if tool_call.tool_type == ToolType.SEARCH:
            return ApprovalStatus.APPROVED  # 搜索无害
        return ApprovalStatus.NEEDS_APPROVAL

    return ApprovalStatus.NEEDS_APPROVAL


# ── 沙箱包装 ──────────────────────────────────────────────────────

@dataclass
class SandboxConfig:
    """沙箱配置。"""
    enabled: bool = True
    writable_dirs: list[str] = field(default_factory=lambda: ["."])
    readable_dirs: list[str] = field(default_factory=lambda: ["/"])
    network_allowed: bool = False


def sandbox_wrap_command(command: str, config: SandboxConfig) -> tuple[str, bool]:
    """
    用沙箱包装命令。
    对应 Seatbelt (macOS) / Landlock (Linux) 策略生成。
    返回 (wrapped_command, is_sandboxed)。
    """
    if not config.enabled:
        return command, False

    # 模拟沙箱包装（实际实现会生成 Seatbelt/Landlock 策略）
    sandbox_info = []
    sandbox_info.append(f"writable={config.writable_dirs}")
    sandbox_info.append(f"network={'yes' if config.network_allowed else 'no'}")
    # 实际中会生成 sandbox-exec -p '(version 1)(allow ...)' 或 landlock 策略
    return command, True


# ── Tool 路由器 ───────────────────────────────────────────────────

class ToolRouter:
    """
    Tool call 路由器，分发到对应的执行逻辑。
    对应 codex-cli 的 tools/router.rs。
    """

    def __init__(
        self,
        cwd: str = ".",
        approval_mode: ApprovalMode = ApprovalMode.AUTO_EDIT,
        sandbox: SandboxConfig | None = None,
        approval_callback=None,  # (ToolCall) -> bool
    ):
        self.cwd = cwd
        self.approval_mode = approval_mode
        self.sandbox = sandbox or SandboxConfig()
        self.approval_callback = approval_callback

    def build_tool_call(self, item: dict) -> ToolCall | None:
        """
        从 LLM 响应构建 ToolCall。
        对应 build_tool_call() — 分类 tool 类型。
        """
        name = item.get("name", "")
        call_id = item.get("id", "")
        arguments = item.get("arguments", {})

        # Shell 命令
        if name in ("shell", "bash", "terminal"):
            return ToolCall(ToolType.SHELL, name, arguments, call_id)

        # 文件补丁
        if name == "apply_patch":
            return ToolCall(ToolType.APPLY_PATCH, name, arguments, call_id)

        # 搜索
        if name in ("search", "grep", "find"):
            return ToolCall(ToolType.SEARCH, name, arguments, call_id)

        # MCP 工具（格式: server__tool_name）
        if "__" in name:
            return ToolCall(ToolType.MCP, name, arguments, call_id)

        return None

    def execute(self, tool_call: ToolCall) -> ToolResult:
        """
        执行 tool call 的完整管线：审批 → 沙箱 → 执行 → 结果。
        """
        # 1. 审批检查
        status = evaluate_approval(tool_call, self.approval_mode)

        if status == ApprovalStatus.FORBIDDEN:
            return ToolResult(
                output=f"Forbidden: command blocked by policy",
                exit_code=1,
                approval_status=status,
            )

        if status == ApprovalStatus.NEEDS_APPROVAL:
            if self.approval_callback:
                approved = self.approval_callback(tool_call)
                if not approved:
                    return ToolResult(
                        output="Denied by user",
                        exit_code=1,
                        approval_status=status,
                    )
            else:
                return ToolResult(
                    output="Needs approval (no callback)",
                    exit_code=1,
                    approval_status=status,
                )

        # 2. 执行
        if tool_call.tool_type == ToolType.SHELL:
            return self._execute_shell(tool_call)
        elif tool_call.tool_type == ToolType.APPLY_PATCH:
            return self._execute_patch(tool_call)
        elif tool_call.tool_type == ToolType.SEARCH:
            return self._execute_search(tool_call)
        else:
            return ToolResult(output=f"Unknown tool type: {tool_call.tool_type}")

    def _execute_shell(self, tc: ToolCall) -> ToolResult:
        """执行 shell 命令（含沙箱包装）。"""
        command = tc.arguments.get("command", "")
        wrapped, sandboxed = sandbox_wrap_command(command, self.sandbox)

        try:
            result = subprocess.run(
                wrapped, shell=True, cwd=self.cwd,
                capture_output=True, text=True, timeout=30,
            )
            return ToolResult(
                output=(result.stdout + result.stderr).strip(),
                exit_code=result.returncode,
                approval_status=ApprovalStatus.APPROVED,
                sandboxed=sandboxed,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(output="Command timed out", exit_code=124)
        except Exception as e:
            return ToolResult(output=f"Error: {e}", exit_code=1)

    def _execute_patch(self, tc: ToolCall) -> ToolResult:
        """模拟 apply_patch 执行。"""
        diff = tc.arguments.get("diff", "")
        path = tc.arguments.get("path", "unknown")
        return ToolResult(
            output=f"Patch applied to {path} ({len(diff)} chars)",
            approval_status=ApprovalStatus.APPROVED,
        )

    def _execute_search(self, tc: ToolCall) -> ToolResult:
        """模拟搜索执行。"""
        pattern = tc.arguments.get("pattern", "")
        return ToolResult(
            output=f"Search for '{pattern}': 3 results found",
            approval_status=ApprovalStatus.APPROVED,
        )
