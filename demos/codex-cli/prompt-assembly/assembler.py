"""
Codex CLI — 多层 Prompt 组装器

复现 codex-rs/core/src/codex.rs 的 build_initial_context() 逻辑：
- 7 层模板逐层叠加
- {{ variable }} 模板变量替换
- 人格切换（pragmatic / friendly）
- 协作模式切换（default / plan）
"""

import os
import re
from dataclasses import dataclass, field

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


@dataclass
class AssemblyConfig:
    """Prompt 组装配置。"""
    personality: str = "pragmatic"           # pragmatic / friendly
    collaboration_mode: str = "default"      # default / plan
    sandbox_policy: str = "workspace-write"  # read-only / workspace-write / full-access
    approval_policy: str = "auto-edit"       # suggest / auto-edit / full-auto
    cwd: str = "/home/user/project"
    enable_memory: bool = True
    custom_instructions: str = ""
    slash_command: str = ""


# ── 层定义 ────────────────────────────────────────────────────────

@dataclass
class Layer:
    """Prompt 的一层。"""
    name: str
    content: str
    source: str  # 来源描述


def _load_template(filename: str) -> str:
    """从 templates/ 目录加载模板文件。"""
    path = os.path.join(TEMPLATES_DIR, filename)
    with open(path) as f:
        return f.read().strip()


def _substitute(template: str, variables: dict[str, str]) -> str:
    """替换模板中的 {{ variable }} 占位符。"""
    def replacer(match):
        key = match.group(1).strip()
        return variables.get(key, match.group(0))
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, template)


# ── 7 层组装 ──────────────────────────────────────────────────────

def assemble(config: AssemblyConfig) -> list[Layer]:
    """按 7 层顺序组装 system prompt。

    层序（与 codex-cli build_initial_context() 一致）：
    1. Base Instructions — 角色定义 + 格式规则 + 工具规范
    2. Personality — 人格模板注入（pragmatic / friendly）
    3. Policy Constraints — 沙箱策略 + 审批策略 → 权限约束
    4. Collaboration Mode — 协作模式（default / plan）
    5. Memory Tool — 长期记忆管理指令
    6. Custom Instructions — 用户自定义指令
    7. Slash Command — 用户 slash 命令扩展
    """
    layers: list[Layer] = []

    # 第 1 层：基础指令
    personality_text = _load_template(f"personality_{config.personality}.md")
    base = _load_template("base.md")
    base = _substitute(base, {"personality": personality_text})
    layers.append(Layer("Base Instructions", base, "templates/base.md"))

    # 第 2 层：人格（已注入到 base 中，此处单独展示）
    layers.append(Layer(
        "Personality",
        f"[Personality: {config.personality}]\n{personality_text}",
        f"templates/personality_{config.personality}.md",
    ))

    # 第 3 层：策略约束
    policy_text = (
        f"# Policy Constraints\n"
        f"- Sandbox: {config.sandbox_policy}\n"
        f"- Approval: {config.approval_policy}\n"
        f"- Working directory: {config.cwd}\n"
    )
    if config.sandbox_policy == "read-only":
        policy_text += "- You may ONLY read files. Do NOT write or execute commands.\n"
    elif config.sandbox_policy == "workspace-write":
        policy_text += f"- You may write files ONLY within {config.cwd} and $TMPDIR.\n"
    else:
        policy_text += "- You have full file system access. Be careful.\n"
    layers.append(Layer("Policy Constraints", policy_text, "DeveloperInstructions::from_policy()"))

    # 第 4 层：协作模式
    mode_text = _load_template(f"mode_{config.collaboration_mode}.md")
    layers.append(Layer("Collaboration Mode", mode_text, f"templates/mode_{config.collaboration_mode}.md"))

    # 第 5 层：记忆工具
    if config.enable_memory:
        memory_text = (
            "# Memory Tool\n"
            "You have access to a persistent memory store at ~/.codex/memories/.\n"
            "- Use `memory_read` to recall previous context\n"
            "- Use `memory_write` to save important decisions\n"
            "- Check memories before starting complex tasks\n"
        )
        layers.append(Layer("Memory Tool", memory_text, "templates/memories/"))

    # 第 6 层：自定义指令
    if config.custom_instructions:
        layers.append(Layer(
            "Custom Instructions",
            f"# Custom Instructions\n{config.custom_instructions}",
            "developer_instructions",
        ))

    # 第 7 层：Slash 命令
    if config.slash_command:
        layers.append(Layer(
            "Slash Command",
            f"# Active Command: {config.slash_command}\n"
            f"Execute the /{config.slash_command} workflow as defined by the user.",
            "~/.codex/prompts/",
        ))

    return layers


def render(layers: list[Layer]) -> str:
    """将所有层渲染为最终的 system prompt 文本。"""
    parts = []
    for layer in layers:
        parts.append(layer.content)
    return "\n\n---\n\n".join(parts)
