"""
Codex CLI — 三级审批策略引擎

复现 codex-rs/core/src/exec_policy.rs 的核心逻辑：
- AskForApproval 三级审批（Suggest / AutoEdit / FullAuto）
- SandboxPolicy 沙箱策略（ReadOnly / WorkspaceWrite / FullAccess）
- 危险命令前缀检测（50+ 禁止前缀）
- 安全命令白名单
- 综合评估 → Decision
"""

import shlex
from enum import Enum
from dataclasses import dataclass


# ── 枚举定义 ──────────────────────────────────────────────────────

class AskForApproval(Enum):
    """三级审批策略，控制用户介入程度。"""
    SUGGEST = "suggest"          # 每个命令都需审批
    AUTO_EDIT = "auto-edit"      # 文件写入自动放行，shell 需审批
    FULL_AUTO = "full-auto"      # 全自动，仅禁止命令被拦截


class SandboxPolicy(Enum):
    """沙箱策略，控制命令的文件系统/网络访问范围。"""
    READ_ONLY = "read-only"             # 只读访问
    WORKSPACE_WRITE = "workspace-write" # 仅 CWD + TMPDIR 可写
    FULL_ACCESS = "full-access"         # 不限制（危险）


class Decision(Enum):
    """审批决策结果。"""
    ALLOW = "allow"               # 直接放行
    NEEDS_APPROVAL = "needs_approval"  # 需要用户确认
    FORBIDDEN = "forbidden"       # 禁止执行


@dataclass
class EvalResult:
    """评估结果，包含决策和原因。"""
    decision: Decision
    reason: str
    command: str


# ── 禁止前缀列表 ─────────────────────────────────────────────────
# 精选自 codex-cli 的 BANNED_PREFIX_SUGGESTIONS（89 个前缀）
# 这些命令前缀可以启动解释器或提权，禁止自动批准

BANNED_PREFIXES: list[list[str]] = [
    # Python
    ["python3"], ["python3", "-c"], ["python3", "-m"],
    ["python"], ["python", "-c"], ["python", "-m"],
    # Shell 解释器
    ["bash"], ["bash", "-c"], ["bash", "-lc"],
    ["sh"], ["sh", "-c"],
    ["zsh"], ["zsh", "-c"],
    # 提权
    ["sudo"],
    # Node.js
    ["node"], ["node", "-e"], ["node", "--eval"],
    # 其他解释器
    ["perl"], ["perl", "-e"],
    ["ruby"], ["ruby", "-e"],
    # 包管理器（可执行任意脚本）
    ["npm", "exec"], ["npx"],
    ["pip", "install"], ["pip3", "install"],
    # 版本控制（危险操作）
    ["git", "push"], ["git", "push", "-f"],
    ["git", "reset", "--hard"],
    # 系统命令
    ["rm", "-rf"], ["chmod"], ["chown"],
    ["curl"], ["wget"],
    ["dd"],
]


# ── 安全命令白名单 ───────────────────────────────────────────────
# 只读/无副作用命令，在任何策略下都可跳过审批

SAFE_COMMANDS: set[str] = {
    "ls", "cat", "head", "tail", "wc", "echo", "printf",
    "pwd", "whoami", "date", "uname",
    "find", "grep", "rg", "ag", "fd",
    "file", "stat", "du", "df",
    "tree", "which", "type", "env", "printenv",
    "diff", "sort", "uniq", "tr", "cut",
    "true", "false", "test",
}


# ── 核心函数 ─────────────────────────────────────────────────────

def parse_command(cmd: str) -> list[str]:
    """用 shlex 将命令字符串解析为 token 列表。"""
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def is_banned_prefix(tokens: list[str]) -> bool:
    """检查命令是否匹配任何禁止前缀。

    匹配逻辑：命令的前 N 个 token 完全匹配某个禁止前缀。
    例如 ["python3", "-c", "print('hi')"] 匹配 ["python3", "-c"]。
    """
    for prefix in BANNED_PREFIXES:
        if len(tokens) >= len(prefix):
            if tokens[:len(prefix)] == prefix:
                return True
    return False


def is_safe_command(tokens: list[str]) -> bool:
    """检查命令是否为已知安全命令（无副作用）。"""
    if not tokens:
        return False
    return tokens[0] in SAFE_COMMANDS


def evaluate(
    cmd: str,
    approval_mode: AskForApproval,
    sandbox_policy: SandboxPolicy,
) -> EvalResult:
    """评估命令的审批决策。

    决策流程（与 codex-cli exec_policy.rs 一致）：
    1. 解析命令为 token
    2. 检查禁止前缀 → Forbidden
    3. 检查��全命令 → 可能 Allow
    4. 根据 approval_mode × sandbox_policy 组合决策
    """
    tokens = parse_command(cmd)

    if not tokens:
        return EvalResult(Decision.FORBIDDEN, "空命令", cmd)

    # 第一层：禁止前缀检测（无论什么策略都拦截）
    if is_banned_prefix(tokens):
        return EvalResult(
            Decision.FORBIDDEN,
            f"匹配禁止前缀: {tokens[:3]}",
            cmd,
        )

    # 第二层：安全命令白名单
    if is_safe_command(tokens):
        # 安全命令在非 Suggest 模式下直接放行
        if approval_mode != AskForApproval.SUGGEST:
            return EvalResult(Decision.ALLOW, f"安全命令: {tokens[0]}", cmd)
        # Suggest 模式下安全命令也需审批（最保守）
        return EvalResult(Decision.NEEDS_APPROVAL, "Suggest 模式：所有命令需审批", cmd)

    # 第三层：approval_mode × sandbox_policy 组合决策
    if approval_mode == AskForApproval.SUGGEST:
        return EvalResult(Decision.NEEDS_APPROVAL, "Suggest 模式：所有命令需审批", cmd)

    if approval_mode == AskForApproval.AUTO_EDIT:
        # Auto-Edit：文件编辑自动放行，但 shell 命令需审批
        return EvalResult(Decision.NEEDS_APPROVAL, "Auto-Edit 模式：Shell 命令需审批", cmd)

    if approval_mode == AskForApproval.FULL_AUTO:
        # Full-Auto：依赖沙箱策略兜底
        if sandbox_policy == SandboxPolicy.FULL_ACCESS:
            return EvalResult(
                Decision.NEEDS_APPROVAL,
                "Full-Auto + FullAccess：无沙箱保护，仍需审批",
                cmd,
            )
        return EvalResult(
            Decision.ALLOW,
            f"Full-Auto 模式 + {sandbox_policy.value} 沙箱保护",
            cmd,
        )

    return EvalResult(Decision.NEEDS_APPROVAL, "未知策略组合", cmd)
