"""
OpenClaw — Tool Profile 机制复现

复现 OpenClaw 的 4 档渐进 Tool Profile 策略：
- 4 档 profile（minimal → coding → messaging → full）
- Tool Policy Pipeline（profile → owner-only → allow/deny → plugin 扩展）
- 场景化工具集合，避免工具过载

对应源码: src/agents/tool-catalog.ts, src/agents/tool-policy.ts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── 数据模型 ──────────────────────────────────────────────────────

class ToolProfileId(str, Enum):
    MINIMAL = "minimal"       # 极简监控
    CODING = "coding"         # 编码任务
    MESSAGING = "messaging"   # 消息通信
    FULL = "full"             # 全功能


class TrustLevel(str, Enum):
    OWNER = "owner"           # 完全信任（本地 CLI / allowlist）
    ALLOWED = "allowed"       # 受限信任
    UNKNOWN = "unknown"       # 不受信任


@dataclass
class ToolDefinition:
    """工具定义"""
    id: str
    section: str              # 分组（Files, Runtime, Memory, Sessions, ...）
    label: str
    description: str
    profiles: list[ToolProfileId]  # 该 tool 属于哪些 profile
    owner_only: bool = False  # 是否仅 owner 可用


@dataclass
class ToolPolicyConfig:
    """运行时策略配置"""
    profile: ToolProfileId = ToolProfileId.FULL
    trust_level: TrustLevel = TrustLevel.OWNER
    allow_list: list[str] = field(default_factory=list)    # 额外允许
    deny_list: list[str] = field(default_factory=list)     # 额外禁止
    sandbox_enabled: bool = False
    plugin_tools: list[str] = field(default_factory=list)  # 插件注入的工具


# ── 工具目录 ──────────────────────────────────────────────────────

CORE_TOOLS: list[ToolDefinition] = [
    # ── Files ──
    ToolDefinition("read", "Files", "Read File", "读取文件内容",
                   [ToolProfileId.CODING]),
    ToolDefinition("write", "Files", "Write File", "写入文件",
                   [ToolProfileId.CODING]),
    ToolDefinition("edit", "Files", "Edit File", "编辑文件局部内容",
                   [ToolProfileId.CODING]),
    ToolDefinition("apply_patch", "Files", "Apply Patch", "应用 unified diff 补丁",
                   [ToolProfileId.CODING]),

    # ── Runtime ──
    ToolDefinition("exec", "Runtime", "Execute", "执行 shell 命令",
                   [ToolProfileId.CODING]),
    ToolDefinition("process", "Runtime", "Process", "后台进程管理",
                   [ToolProfileId.CODING]),

    # ── Web ──
    ToolDefinition("web_search", "Web", "Web Search", "网络搜索",
                   [ToolProfileId.FULL]),
    ToolDefinition("web_fetch", "Web", "Web Fetch", "获��网页内容",
                   [ToolProfileId.FULL]),

    # ── Memory ──
    ToolDefinition("memory_search", "Memory", "Memory Search", "语义记忆检索",
                   [ToolProfileId.CODING]),
    ToolDefinition("memory_get", "Memory", "Memory Get", "读取记忆文件",
                   [ToolProfileId.CODING]),

    # ── Sessions ──
    ToolDefinition("sessions_list", "Sessions", "List Sessions", "列出会话",
                   [ToolProfileId.CODING, ToolProfileId.MESSAGING]),
    ToolDefinition("sessions_history", "Sessions", "Session History", "查看会话历史",
                   [ToolProfileId.CODING, ToolProfileId.MESSAGING]),
    ToolDefinition("sessions_send", "Sessions", "Send to Session", "向会话发送消息",
                   [ToolProfileId.CODING, ToolProfileId.MESSAGING]),
    ToolDefinition("sessions_spawn", "Sessions", "Spawn Session", "派生子 agent",
                   [ToolProfileId.CODING]),

    # ── Messaging ──
    ToolDefinition("message", "Messaging", "Send Message", "通道消息发送",
                   [ToolProfileId.MESSAGING]),

    # ── Automation ──
    ToolDefinition("cron", "Automation", "Cron", "定时任务管理",
                   [ToolProfileId.FULL], owner_only=True),
    ToolDefinition("gateway", "Automation", "Gateway", "网关控制",
                   [ToolProfileId.FULL], owner_only=True),

    # ── Status ──
    ToolDefinition("session_status", "Status", "Session Status", "查看会话状态",
                   [ToolProfileId.MINIMAL, ToolProfileId.CODING, ToolProfileId.MESSAGING]),

    # ── UI ──
    ToolDefinition("browser", "UI", "Browser", "浏览器自动化",
                   [ToolProfileId.FULL]),
    ToolDefinition("canvas", "UI", "Canvas", "A2UI 可视化",
                   [ToolProfileId.FULL]),

    # ── Media ──
    ToolDefinition("image", "Media", "Image Gen", "图像生成",
                   [ToolProfileId.CODING]),
    ToolDefinition("tts", "Media", "TTS", "语音合成",
                   [ToolProfileId.FULL]),

    # ── Agents ──
    ToolDefinition("subagents", "Agents", "Subagents", "子 agent 管理",
                   [ToolProfileId.CODING]),
]


# ── Tool Policy Pipeline ─────────────────────────────────────────

class ToolPolicyPipeline:
    """
    OpenClaw Tool Policy Pipeline 复现

    过滤链:
    1. Profile 过滤 — 按 profile 等级筛选工具集合
    2. Owner-only 检查 — 非 owner 移除敏感工具
    3. Allow/Deny list — 显式覆盖
    4. Plugin 扩展 — 注入插件工具
    """

    def __init__(self, tools: list[ToolDefinition]):
        self.all_tools = {t.id: t for t in tools}

    def resolve(self, config: ToolPolicyConfig) -> list[ToolDefinition]:
        """执行完整的策略流水线，返回最终可用工具集"""
        available = list(self.all_tools.values())

        # ── Stage 1: Profile 过滤 ──
        if config.profile != ToolProfileId.FULL:
            available = [
                t for t in available
                if config.profile in t.profiles
            ]
        # full profile 不施加限制

        # ── Stage 2: Owner-only 检查 ──
        if config.trust_level != TrustLevel.OWNER:
            available = [t for t in available if not t.owner_only]

        # ── Stage 3: Deny list ──
        if config.deny_list:
            deny_set = set(config.deny_list)
            available = [t for t in available if t.id not in deny_set]

        # ── Stage 4: Allow list（额外添加被 profile 过滤掉的工具） ──
        if config.allow_list:
            available_ids = {t.id for t in available}
            for tool_id in config.allow_list:
                if tool_id not in available_ids and tool_id in self.all_tools:
                    tool = self.all_tools[tool_id]
                    if not tool.owner_only or config.trust_level == TrustLevel.OWNER:
                        available.append(tool)

        # ── Stage 5: Plugin 扩展 ──
        for plugin_id in config.plugin_tools:
            available.append(ToolDefinition(
                plugin_id, "Plugins", plugin_id,
                f"Plugin tool: {plugin_id}",
                [ToolProfileId.FULL],
            ))

        return available


# ── Demo ──────────────────────────────────────────────────────────

def print_tools(tools: list[ToolDefinition]):
    """按 section 分组打印工具"""
    by_section: dict[str, list[str]] = {}
    for t in tools:
        by_section.setdefault(t.section, []).append(t.id)
    for section, ids in by_section.items():
        print(f"    {section:12s}: {', '.join(ids)}")


def main():
    pipeline = ToolPolicyPipeline(CORE_TOOLS)

    print("=" * 64)
    print("OpenClaw Tool Profile Demo")
    print("=" * 64)

    # ── Profile 对比 ──
    print("\n── 4 档 Profile 对比 ──")

    for profile in ToolProfileId:
        config = ToolPolicyConfig(profile=profile, trust_level=TrustLevel.OWNER)
        tools = pipeline.resolve(config)
        print(f"\n  [{profile.value}] ({len(tools)} tools)")
        print_tools(tools)

    # ── Owner vs Allowed 对比 ──
    print("\n── 信任级别对比 (full profile) ──")

    for trust in TrustLevel:
        config = ToolPolicyConfig(profile=ToolProfileId.FULL, trust_level=trust)
        tools = pipeline.resolve(config)
        owner_only_ids = [t.id for t in CORE_TOOLS if t.owner_only]
        has_sensitive = [t.id for t in tools if t.id in owner_only_ids]
        print(f"\n  [{trust.value}] {len(tools)} tools, owner-only 工具: {has_sensitive or '无'}")

    # ── Policy Pipeline 演示 ──
    print("\n── Policy Pipeline 演示 ──")

    # 子 agent 场景：minimal profile + 额外允许 exec
    print("\n  场景 1: 子 agent（minimal + 额外允许 exec）")
    config = ToolPolicyConfig(
        profile=ToolProfileId.MINIMAL,
        trust_level=TrustLevel.OWNER,
        allow_list=["exec"],
    )
    tools = pipeline.resolve(config)
    print(f"    结果: {[t.id for t in tools]}")

    # 外部用户场景：messaging profile + 禁用 sessions_spawn
    print("\n  场景 2: 外部用户（messaging + deny sessions_spawn）")
    config = ToolPolicyConfig(
        profile=ToolProfileId.MESSAGING,
        trust_level=TrustLevel.ALLOWED,
        deny_list=["sessions_spawn"],
    )
    tools = pipeline.resolve(config)
    print(f"    结果: {[t.id for t in tools]}")

    # 插件场景：coding + 两个插件工具
    print("\n  场景 3: 插件扩展（coding + 2 plugins）")
    config = ToolPolicyConfig(
        profile=ToolProfileId.CODING,
        trust_level=TrustLevel.OWNER,
        plugin_tools=["github_pr_review", "jira_create_issue"],
    )
    tools = pipeline.resolve(config)
    plugin_ids = [t.id for t in tools if t.section == "Plugins"]
    print(f"    核心工具: {len(tools) - len(plugin_ids)}, 插件工具: {plugin_ids}")


if __name__ == "__main__":
    main()
