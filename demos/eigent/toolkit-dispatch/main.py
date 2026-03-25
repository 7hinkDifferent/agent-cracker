"""
Eigent — Toolkit 分发 Demo

复现 eigent 的三层 Toolkit 体系：
1. AbstractToolkit 基类 + get_can_use_tools() 条件过滤
2. get_toolkits() 收集器 — 按名称查找 + 动态加载
3. @listen_toolkit / @auto_listen_toolkit 事件装饰器

原实现: backend/app/agent/toolkit/abstract_toolkit.py
       backend/app/agent/tools.py (get_toolkits, get_mcp_tools)
       backend/app/utils/listen/toolkit_listen.py (@listen_toolkit)
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from typing import Any, Callable


# ─── @listen_toolkit 装饰器 ──────────────────────────────────

def listen_toolkit(
    inputs: Callable | None = None,
    return_msg: Callable | None = None,
):
    """事件织入装饰器 — 在 Tool 方法前后自动发送 activate/deactivate 事件。

    原实现: backend/app/utils/listen/toolkit_listen.py

    关键设计:
    - 设置 __listen_toolkit__ = True 标记
    - ListenChatAgent._execute_tool() 检查此标记，避免重复发送事件
    - inputs/return_msg 参数控制事件数据格式
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 格式化输入
            input_msg = inputs(self, *args, **kwargs) if inputs else str(args)

            # 发送激活事件
            toolkit_name = self.toolkit_name() if hasattr(self, 'toolkit_name') else type(self).__name__
            print(f"    🔧 [activate] {toolkit_name}.{func.__name__}({input_msg[:50]})")

            # 执行方法
            result = func(self, *args, **kwargs)

            # 格式化结果
            result_msg = return_msg(result) if return_msg else str(result)[:100]
            print(f"    🔨 [deactivate] {toolkit_name}.{func.__name__} → {result_msg[:50]}")

            return result

        # 关键标记 — ListenChatAgent 检查此标记
        wrapper.__listen_toolkit__ = True
        return wrapper
    return decorator


def auto_listen_toolkit(base_class):
    """类级装饰器 — 自动为基类的所有公共方法注入事件。

    原实现: @auto_listen_toolkit(BaseGithubToolkit) 用法
    排除: get_tools, get_can_use_tools, toolkit_name, model_dump 等
    """
    excluded = {"get_tools", "get_can_use_tools", "toolkit_name",
                "model_dump", "dict", "json"}

    def decorator(cls):
        for name in dir(base_class):
            if name.startswith("_") or name in excluded:
                continue
            method = getattr(base_class, name, None)
            if callable(method) and not getattr(method, "__listen_toolkit__", False):
                wrapped = listen_toolkit()(method)
                setattr(cls, name, wrapped)
        return cls
    return decorator


# ─── AbstractToolkit 基类 ───────────────────────────────────

class AbstractToolkit:
    """所有 Toolkit 的基类 — 提供条件过滤接口。

    原实现: backend/app/agent/toolkit/abstract_toolkit.py

    关键方法:
    - get_can_use_tools(api_task_id): 类方法，按条件返回可用工具
    - toolkit_name(): 返回 Toolkit 名称
    - get_tools(): 返回所有工具列表
    """
    api_task_id: str = ""
    agent_name: str = ""

    def __init__(self, api_task_id: str = "", agent_name: str = "") -> None:
        self.api_task_id = api_task_id
        self.agent_name = agent_name

    @classmethod
    def toolkit_name(cls) -> str:
        return cls.__name__

    @classmethod
    def get_can_use_tools(cls, api_task_id: str = "", agent_name: str = "") -> list[dict]:
        """默认返回所有工具，子类可覆盖以按条件过滤。"""
        instance = cls(api_task_id, agent_name)
        return instance.get_tools()

    def get_tools(self) -> list[dict]:
        """返回所有工具定义（子类实现）。"""
        return []


# ─── 具体 Toolkit 实现 ──────────────────────────────────────

class TerminalToolkit(AbstractToolkit):
    """终端工具 — 执行 shell 命令。"""

    @listen_toolkit(
        inputs=lambda self, command: command,
        return_msg=lambda res: f"Output: {res}",
    )
    def shell_exec(self, command: str) -> str:
        """执行 shell 命令（模拟）"""
        return f"[simulated] $ {command} → OK"

    def get_tools(self) -> list[dict]:
        return [{"name": "shell_exec", "func": self.shell_exec,
                 "toolkit": self.toolkit_name()}]


class SearchToolkit(AbstractToolkit):
    """搜索工具 — 条件过滤示例。"""

    @classmethod
    def get_can_use_tools(cls, api_task_id: str = "", agent_name: str = "") -> list[dict]:
        """只有 browser_agent 可以使用搜索工具。

        原实现中 GithubToolkit 检查 GITHUB_ACCESS_TOKEN 是否存在。
        """
        if agent_name == "browser_agent":
            instance = cls(api_task_id, agent_name)
            return instance.get_tools()
        return []  # 其他 Agent 不可用

    @listen_toolkit(
        inputs=lambda self, query: query,
        return_msg=lambda res: f"Results: {res}",
    )
    def search_google(self, query: str) -> str:
        return f"[simulated] Found 5 results for '{query}'"

    def get_tools(self) -> list[dict]:
        return [{"name": "search_google", "func": self.search_google,
                 "toolkit": self.toolkit_name()}]


class HumanToolkit(AbstractToolkit):
    """人机交互工具 — 部分暴露示例。"""

    @listen_toolkit()
    def ask_human_via_gui(self, question: str) -> str:
        """向用户提问（模拟）"""
        return f"[simulated] User replied: Yes"

    def send_message_to_user(self, message: str) -> str:
        """向用户发送消息（不通过 get_can_use_tools 暴露）"""
        return f"[simulated] Sent: {message}"

    @classmethod
    def get_can_use_tools(cls, api_task_id: str = "", agent_name: str = "") -> list[dict]:
        """只暴露 ask_human，不暴露 send_message。

        原实现中 send_message_to_user 通过 ToolkitMessageIntegration 注入，
        不直接暴露给 LLM。
        """
        instance = cls(api_task_id, agent_name)
        return [{"name": "ask_human_via_gui", "func": instance.ask_human_via_gui,
                 "toolkit": cls.toolkit_name()}]


class SkillToolkit(AbstractToolkit):
    """用户自定义技能 — 多层配置示例。

    原实现: backend/app/agent/toolkit/skill_toolkit.py
    配置层级: 项目级 > 用户全局 > 默认
    """

    def __init__(self, api_task_id: str = "", agent_name: str = "",
                 allowed_skills: list[str] | None = None) -> None:
        super().__init__(api_task_id, agent_name)
        self.allowed_skills = allowed_skills or ["data-analyzer", "pdf-reader"]

    @listen_toolkit()
    def list_skills(self) -> str:
        return json.dumps(self.allowed_skills)

    @listen_toolkit(inputs=lambda self, name: name)
    def load_skill(self, name: str) -> str:
        if name in self.allowed_skills:
            return f"[loaded skill: {name}] Follow these instructions..."
        return f"Skill '{name}' not found"

    def get_tools(self) -> list[dict]:
        return [
            {"name": "list_skills", "func": self.list_skills, "toolkit": self.toolkit_name()},
            {"name": "load_skill", "func": self.load_skill, "toolkit": self.toolkit_name()},
        ]


# ─── Toolkit 收集器 ──────────────────────────────────────────

# 全局 Toolkit 注册表（原实现: tools.py get_toolkits）
TOOLKIT_REGISTRY: dict[str, type[AbstractToolkit]] = {
    "terminal_toolkit": TerminalToolkit,
    "search_toolkit": SearchToolkit,
    "human_toolkit": HumanToolkit,
    "skill_toolkit": SkillToolkit,
}


def get_toolkits(
    tool_names: list[str],
    agent_name: str = "",
    api_task_id: str = "",
) -> list[dict]:
    """收集指定 Toolkit 的所有工具 — 核心收集器。

    原实现: backend/app/agent/tools.py get_toolkits()

    流程:
    1. 按名称从注册表查找 Toolkit 类
    2. 调用 get_can_use_tools() 获取可用工具（条件过滤）
    3. 合并所有工具列表
    """
    all_tools = []
    for name in tool_names:
        toolkit_cls = TOOLKIT_REGISTRY.get(name)
        if toolkit_cls is None:
            print(f"  ⚠️  Toolkit '{name}' not found in registry")
            continue

        # 调用条件过滤（不同 Toolkit 可能有不同的过滤逻辑）
        tools = toolkit_cls.get_can_use_tools(api_task_id, agent_name=agent_name)
        print(f"  📦 {name}: {len(tools)} tools available"
              f"{' (filtered)' if not tools else ''}")
        all_tools.extend(tools)

    return all_tools


# ─── Demo ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Eigent Toolkit 分发 Demo")
    print("=" * 60)

    # 1. Developer Agent 的 Toolkit 收集
    print("\n🔧 Developer Agent 的 Toolkit 收集:")
    dev_tools = get_toolkits(
        ["terminal_toolkit", "search_toolkit", "human_toolkit", "skill_toolkit"],
        agent_name="developer_agent",
    )
    print(f"  → 共获得 {len(dev_tools)} 个工具")
    for t in dev_tools:
        print(f"     - {t['name']} ({t['toolkit']})")

    # 2. Browser Agent 的 Toolkit 收集（search_toolkit 可用）
    print("\n🔍 Browser Agent 的 Toolkit 收集:")
    browser_tools = get_toolkits(
        ["terminal_toolkit", "search_toolkit", "human_toolkit"],
        agent_name="browser_agent",
    )
    print(f"  → 共获得 {len(browser_tools)} 个工具")
    for t in browser_tools:
        print(f"     - {t['name']} ({t['toolkit']})")

    # 3. 演示 @listen_toolkit 装饰器效果
    print(f"\n{'─' * 40}")
    print("🎭 @listen_toolkit 装饰器效果:")
    print("─" * 40)

    terminal = TerminalToolkit("task-001")
    terminal.shell_exec("ls -la")
    terminal.shell_exec("python script.py")

    search = SearchToolkit("task-001", "browser_agent")
    search.search_google("Python 3.12 release date")

    skill = SkillToolkit("task-001", "developer_agent")
    skill.list_skills()
    skill.load_skill("data-analyzer")
    skill.load_skill("unknown-skill")

    # 4. 检查 __listen_toolkit__ 标记
    print(f"\n{'─' * 40}")
    print("🏷️  __listen_toolkit__ 标记检查:")
    print("─" * 40)
    print(f"  terminal.shell_exec.__listen_toolkit__ = "
          f"{getattr(terminal.shell_exec, '__listen_toolkit__', False)}")
    print(f"  human.send_message_to_user.__listen_toolkit__ = "
          f"{getattr(HumanToolkit().send_message_to_user, '__listen_toolkit__', False)}")

    print("\n✅ Demo 完成")


if __name__ == "__main__":
    main()
