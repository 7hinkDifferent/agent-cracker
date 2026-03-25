"""
Eigent — 多层 Skill 配置体系 Demo

复现 eigent 的 Skill 配置机制：
1. 三层配置优先级：项目级 > 用户全局 > legacy 默认
2. skills-config.json 格式：enabled/scope/selectedAgents
3. 按 Agent 类型过滤（_is_agent_allowed）
4. 合并配置加载（_get_merged_skill_config）

原实现: backend/app/agent/toolkit/skill_toolkit.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ─── Skill 配置模型 ──────────────────────────────────────────

class SkillScope(str, Enum):
    """Skill 适用范围。"""
    ALL_AGENTS = "all_agents"        # 所有 Agent 可用
    SELECTED_AGENTS = "selected"     # 仅指定 Agent 可用


@dataclass
class SkillConfig:
    """单个 Skill 的配置 — 对应 skills-config.json 中的一项。

    原实现: skill_toolkit.py 中 skills-config.json 的结构
    """
    name: str
    enabled: bool = True
    scope: SkillScope = SkillScope.ALL_AGENTS
    selected_agents: list[str] = field(default_factory=list)
    description: str = ""
    instructions: str = ""         # Skill 注入到 system prompt 的指令

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "scope": self.scope.value,
            "selectedAgents": self.selected_agents,
            "description": self.description,
        }


# ─── 三层配置存储 ─────────────────────────────────────────────

class SkillConfigStore:
    """三层 Skill 配置存储 — 模拟 eigent 的配置文件层级。

    原实现的配置来源:
    1. 项目级: /project/<id>/skills-config.json（最高优先级）
    2. 用户全局: /user/<id>/skills-config.json
    3. Legacy 默认: 硬编码的默认 Skill 列表

    合并规则: 项目级覆盖用户级，用户级覆盖 legacy。
    """

    def __init__(self) -> None:
        # Legacy 默认配置（最低优先级）
        self._legacy: dict[str, SkillConfig] = {}
        # 用户全局配置
        self._user_configs: dict[str, dict[str, SkillConfig]] = {}  # user_id -> skills
        # 项目级配置（最高优先级）
        self._project_configs: dict[str, dict[str, SkillConfig]] = {}  # project_id -> skills

    def set_legacy(self, configs: list[SkillConfig]) -> None:
        """设置 legacy 默认配置。"""
        self._legacy = {c.name: c for c in configs}

    def set_user_config(self, user_id: str, configs: list[SkillConfig]) -> None:
        """设置用户全局配置。"""
        self._user_configs[user_id] = {c.name: c for c in configs}

    def set_project_config(self, project_id: str, configs: list[SkillConfig]) -> None:
        """设置项目级配置。"""
        self._project_configs[project_id] = {c.name: c for c in configs}

    def get_merged_config(self, user_id: str,
                          project_id: str) -> dict[str, SkillConfig]:
        """合并三层配置 — 核心方法。

        原实现: skill_toolkit.py _get_merged_skill_config()

        合并策略:
        1. 从 legacy 开始
        2. 用户级覆盖同名 Skill
        3. 项目级覆盖同名 Skill（最终生效）
        """
        merged = dict(self._legacy)

        # 用户级覆盖
        user_skills = self._user_configs.get(user_id, {})
        for name, config in user_skills.items():
            merged[name] = config

        # 项目级覆盖（最高优先级）
        project_skills = self._project_configs.get(project_id, {})
        for name, config in project_skills.items():
            merged[name] = config

        return merged


# ─── SkillToolkit ────────────────────────────────────────────

class SkillToolkit:
    """Skill 工具集 — 按配置和 Agent 类型过滤可用 Skill。

    原实现: backend/app/agent/toolkit/skill_toolkit.py

    关键方法:
    - _is_agent_allowed(): 检查 Skill 是否对当前 Agent 可用
    - get_available_skills(): 返回当前 Agent 的可用 Skill 列表
    - load_skill(): 加载 Skill 指令到上下文
    """

    def __init__(self, agent_name: str, config_store: SkillConfigStore,
                 user_id: str = "", project_id: str = "") -> None:
        self.agent_name = agent_name
        self._store = config_store
        self._user_id = user_id
        self._project_id = project_id

    def _is_agent_allowed(self, config: SkillConfig) -> bool:
        """检查当前 Agent 是否有权使用此 Skill。

        原实现: skill_toolkit.py _is_agent_allowed()

        规则:
        - scope=all_agents → 所有 Agent 可用
        - scope=selected → 仅 selectedAgents 列表中的 Agent 可用
        """
        if not config.enabled:
            return False
        if config.scope == SkillScope.ALL_AGENTS:
            return True
        return self.agent_name in config.selected_agents

    def get_available_skills(self) -> list[SkillConfig]:
        """获取当前 Agent 的可用 Skill 列表。"""
        merged = self._store.get_merged_config(self._user_id, self._project_id)
        return [
            config for config in merged.values()
            if self._is_agent_allowed(config)
        ]

    def list_skills(self) -> str:
        """列出可用 Skill — 供 LLM 调用。"""
        available = self.get_available_skills()
        if not available:
            return "No skills available for this agent."
        lines = [f"Available skills for {self.agent_name}:"]
        for s in available:
            status = "enabled" if s.enabled else "disabled"
            lines.append(f"  - {s.name}: {s.description} [{status}]")
        return "\n".join(lines)

    def load_skill(self, skill_name: str) -> str:
        """加载 Skill 指令 — 注入到 Agent 上下文。"""
        merged = self._store.get_merged_config(self._user_id, self._project_id)
        config = merged.get(skill_name)
        if not config:
            return f"Skill '{skill_name}' not found."
        if not self._is_agent_allowed(config):
            return f"Skill '{skill_name}' is not available for {self.agent_name}."
        return f"[Skill: {skill_name}]\n{config.instructions}"


# ─── Demo ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Eigent 多层 Skill 配置体系 Demo")
    print("=" * 60)

    store = SkillConfigStore()

    # 1. 设置三层配置
    print("\n--- 配置三层 Skill ---\n")

    # Legacy 默认
    store.set_legacy([
        SkillConfig("data-analyzer", description="Analyze CSV/JSON data",
                    instructions="Use pandas to load and analyze data files."),
        SkillConfig("pdf-reader", description="Extract text from PDF",
                    instructions="Use PyPDF2 to extract text from uploaded PDFs."),
        SkillConfig("code-reviewer", description="Review code quality",
                    instructions="Check code style, complexity, and potential bugs."),
    ])
    print("  [legacy]  3 default skills: data-analyzer, pdf-reader, code-reviewer")

    # 用户全局配置（覆盖 pdf-reader 的 scope，新增 translator）
    store.set_user_config("user-1", [
        SkillConfig("pdf-reader", description="Extract text from PDF",
                    scope=SkillScope.SELECTED_AGENTS,
                    selected_agents=["document_agent", "browser_agent"],
                    instructions="Use PyPDF2. Only for document-related agents."),
        SkillConfig("translator", description="Translate between languages",
                    instructions="Translate text using standard patterns."),
    ])
    print("  [user]    Override pdf-reader scope, add translator")

    # 项目级配置（禁用 code-reviewer，新增 api-tester）
    store.set_project_config("proj-1", [
        SkillConfig("code-reviewer", enabled=False,
                    description="Review code quality"),
        SkillConfig("api-tester", description="Test REST APIs",
                    scope=SkillScope.SELECTED_AGENTS,
                    selected_agents=["developer_agent"],
                    instructions="Use httpx to test API endpoints."),
    ])
    print("  [project] Disable code-reviewer, add api-tester (dev only)")

    # 2. 展示合并结果
    print(f"\n{'─' * 40}")
    print("--- 合并后的配置 (user-1 / proj-1) ---\n")
    merged = store.get_merged_config("user-1", "proj-1")
    for name, config in merged.items():
        scope_info = (f"agents={config.selected_agents}"
                      if config.scope == SkillScope.SELECTED_AGENTS else "all")
        status = "enabled" if config.enabled else "DISABLED"
        print(f"  {name:20s} [{status:8s}] scope={scope_info}")

    # 3. 不同 Agent 看到的 Skill 列表
    print(f"\n{'─' * 40}")
    print("--- 按 Agent 类型过滤 ---\n")

    agents = ["developer_agent", "browser_agent", "document_agent", "mcp_agent"]
    for agent_name in agents:
        toolkit = SkillToolkit(agent_name, store, "user-1", "proj-1")
        available = toolkit.get_available_skills()
        skill_names = [s.name for s in available]
        print(f"  {agent_name:20s} -> {skill_names}")

    # 4. 加载 Skill
    print(f"\n{'─' * 40}")
    print("--- 加载 Skill 指令 ---\n")

    dev_toolkit = SkillToolkit("developer_agent", store, "user-1", "proj-1")
    print(f"  {dev_toolkit.load_skill('api-tester')}")
    print()
    print(f"  {dev_toolkit.load_skill('data-analyzer')}")

    # 5. 权限拒绝测试
    print(f"\n{'─' * 40}")
    print("--- 权限拒绝测试 ---\n")

    mcp_toolkit = SkillToolkit("mcp_agent", store, "user-1", "proj-1")
    print(f"  mcp_agent load api-tester: {mcp_toolkit.load_skill('api-tester')}")
    print(f"  mcp_agent load pdf-reader: {mcp_toolkit.load_skill('pdf-reader')}")

    # 6. 不同用户/项目的配置隔离
    print(f"\n{'─' * 40}")
    print("--- 配置隔离 (user-2 / proj-2) ---\n")

    other_toolkit = SkillToolkit("developer_agent", store, "user-2", "proj-2")
    available = other_toolkit.get_available_skills()
    print(f"  developer_agent (user-2/proj-2): {[s.name for s in available]}")
    print(f"  (only legacy defaults, no user/project overrides)")

    # 7. skills-config.json 格式示例
    print(f"\n{'─' * 40}")
    print("--- skills-config.json 格式 ---\n")
    sample_config = {
        "skills": [config.to_dict() for config in list(merged.values())[:3]]
    }
    print(json.dumps(sample_config, indent=2, ensure_ascii=False))

    print(f"\nDemo 完成")


if __name__ == "__main__":
    main()
