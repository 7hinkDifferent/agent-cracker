"""
Eigent — Agent 工厂 Demo

复现 eigent 的 Agent 创建机制：
- 8 类专业 Agent 的工厂函数
- ListenChatAgent 事件织入（step/tool 执行前后注入 UI 事件）
- 按 Agent 类型选择 Toolkit 和 System Prompt

原实现: backend/app/agent/agent_model.py (agent_model)
       backend/app/agent/listen_chat_agent.py (ListenChatAgent)
       backend/app/agent/factory/ (8 个 Agent 工厂)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import litellm


# ─── Agent 类型枚举 ──────────────────────────────────────────

class AgentType(str, Enum):
    """对应 eigent 的 8 类 Agent。

    原实现: app/service/task.py Agents enum
    """
    developer = "developer_agent"
    browser = "browser_agent"
    document = "document_agent"
    multi_modal = "multi_modal_agent"
    social_media = "social_media_agent"
    mcp = "mcp_agent"
    question_confirm = "question_confirm_agent"
    task_summary = "task_summary_agent"


# ─── Tool 定义 ───────────────────────────────────────────────

@dataclass
class FunctionTool:
    """简化的 CAMEL FunctionTool。

    原实现: camel.toolkits.FunctionTool
    """
    name: str
    description: str
    func: Callable
    toolkit_name: str = ""

    def __call__(self, **kwargs) -> str:
        return self.func(**kwargs)


# ─── 事件回调 ───────────────────────────────────────────────

@dataclass
class AgentEvent:
    """Agent/Toolkit 事件 — 对应 eigent 的 SSE 事件。"""
    event_type: str  # activate_agent, deactivate_agent, activate_toolkit, deactivate_toolkit
    agent_name: str
    data: dict[str, Any] = field(default_factory=dict)


EventCallback = Callable[[AgentEvent], None]


# ─── ListenChatAgent ─────────────────────────────────────────

class ListenChatAgent:
    """扩展 CAMEL ChatAgent — 注入 UI 事件。

    原实现: backend/app/agent/listen_chat_agent.py

    关键扩展:
    1. step() 前后发送 activate/deactivate_agent 事件
    2. _execute_tool() 前后发送 activate/deactivate_toolkit 事件
    3. 流式响应时通过 _stream_chunks() 包装
    """

    def __init__(
        self,
        agent_name: str,
        system_prompt: str,
        tools: list[FunctionTool] | None = None,
        model: str = "",
        on_event: EventCallback | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.tools = {t.name: t for t in (tools or [])}
        self.model = model or os.environ.get("DEMO_MODEL", "gpt-4o-mini")
        self._on_event = on_event
        self._messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]

    def _emit(self, event_type: str, **data) -> None:
        """发送事件到前端（原实现通过 TaskLock.queue）"""
        if self._on_event:
            self._on_event(AgentEvent(
                event_type=event_type,
                agent_name=self.agent_name,
                data=data,
            ))

    def step(self, message: str) -> str:
        """执行一步 — 核心方法。

        原实现: ListenChatAgent.step()
        1. 发送 activate_agent 事件
        2. 调用 super().step() (CAMEL ChatAgent)
        3. 如果 LLM 返回 tool_call，执行工具
        4. 发送 deactivate_agent 事件
        """
        # 1. 激活事件
        self._emit("activate_agent", message=message[:100])

        self._messages.append({"role": "user", "content": message})

        # 2. LLM 调用
        tool_schemas = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            for t in self.tools.values()
        ] if self.tools else None

        try:
            response = litellm.completion(
                model=self.model,
                messages=self._messages,
                tools=tool_schemas if tool_schemas else None,
                max_tokens=300,
            )
        except Exception as e:
            result = f"Error: {e}"
            self._emit("deactivate_agent", message=result, tokens=0)
            return result

        choice = response.choices[0]
        total_tokens = response.usage.total_tokens if response.usage else 0

        # 3. 检查 tool calls
        if choice.message.tool_calls:
            results = []
            for tc in choice.message.tool_calls:
                tool_result = self._execute_tool(
                    tc.function.name,
                    json.loads(tc.function.arguments) if tc.function.arguments else {},
                )
                results.append(f"[{tc.function.name}]: {tool_result}")
            result = "\n".join(results)
        else:
            result = choice.message.content or ""

        self._messages.append({"role": "assistant", "content": result})

        # 4. 停用事件
        self._emit("deactivate_agent", message=result[:200], tokens=total_tokens)
        return result

    def _execute_tool(self, tool_name: str, args: dict) -> str:
        """执行工具 — 注入 Toolkit 事件。

        原实现: ListenChatAgent._execute_tool()
        1. 检查 @listen_toolkit 装饰器标记
        2. 未标记的工具手动发送 activate/deactivate_toolkit
        3. 使用 set_process_task() 保持 ContextVar
        """
        tool = self.tools.get(tool_name)
        if not tool:
            return f"Tool '{tool_name}' not found"

        # Toolkit 激活事件
        self._emit("activate_toolkit",
                    toolkit_name=tool.toolkit_name,
                    method_name=tool_name,
                    message=json.dumps(args, ensure_ascii=False))

        try:
            result = tool(**args)
            # 结果截断（原实现 MAX_RESULT_LENGTH=500）
            if len(str(result)) > 500:
                result_msg = str(result)[:500] + "... (truncated)"
            else:
                result_msg = str(result)
        except Exception as e:
            result_msg = f"Tool execution failed: {e}"

        # Toolkit 停用事件
        self._emit("deactivate_toolkit",
                    toolkit_name=tool.toolkit_name,
                    method_name=tool_name,
                    message=result_msg[:200])

        return result_msg


# ─── Agent 工厂 ──────────────────────────────────────────────

# 简化的 Toolkit（原实现有 30+）
def shell_exec(command: str = "echo hello") -> str:
    """模拟终端执行"""
    return f"[simulated] $ {command} → OK"

def search_google(query: str = "python") -> str:
    """模拟搜索"""
    return f"[simulated] Found 5 results for '{query}'"

def write_to_file(path: str = "output.txt", content: str = "") -> str:
    """模拟文件写入"""
    return f"[simulated] Wrote {len(content)} chars to {path}"


# 每种 Agent 的 Toolkit 映射（原实现: factory/*.py）
AGENT_TOOLKITS: dict[AgentType, list[FunctionTool]] = {
    AgentType.developer: [
        FunctionTool("shell_exec", "Execute shell command", shell_exec, "TerminalToolkit"),
        FunctionTool("write_to_file", "Write content to file", write_to_file, "FileWriteToolkit"),
    ],
    AgentType.browser: [
        FunctionTool("search_google", "Search the web", search_google, "SearchToolkit"),
    ],
    AgentType.document: [
        FunctionTool("write_to_file", "Write content to file", write_to_file, "FileWriteToolkit"),
    ],
    AgentType.question_confirm: [],  # 无工具
    AgentType.task_summary: [],      # 无工具
}

# 每种 Agent 的 System Prompt 片段（原实现: prompt.py）
AGENT_PROMPTS: dict[AgentType, str] = {
    AgentType.developer: "You are a Lead Software Engineer. Write and execute code to solve tasks.",
    AgentType.browser: "You are a Senior Research Analyst. Search the web for information.",
    AgentType.document: "You are a Documentation Specialist. Create well-structured documents.",
    AgentType.multi_modal: "You are a Creative Content Specialist. Process and generate media.",
    AgentType.social_media: "You are a Social Media Manager. Manage social media content.",
    AgentType.mcp: "You are an MCP Server Agent. Manage custom MCP server connections.",
    AgentType.question_confirm: "You are a helpful agent. Analyze requests and determine actions.",
    AgentType.task_summary: "You summarize task results concisely.",
}


def create_agent(
    agent_type: AgentType,
    on_event: EventCallback | None = None,
    working_directory: str = "/tmp/eigent",
) -> ListenChatAgent:
    """Agent 工厂函数 — 模拟 eigent 的 agent_model() + factory/*.py。

    原实现流程:
    1. factory/developer.py 等工厂函数收集 Toolkit
    2. 调用 agent_model() 创建 ListenChatAgent
    3. agent_model() 内部:
       - ModelFactory.create() 创建 LLM 模型
       - ListenChatAgent() 包装为事件化 Agent
       - 发送 ActionCreateAgentData 到前端
    """
    # 获取 system prompt（注入动态变量）
    base_prompt = AGENT_PROMPTS.get(agent_type, "You are a helpful assistant.")
    system_prompt = f"{base_prompt}\nWorking Directory: {working_directory}"

    # 获取 toolkit
    tools = AGENT_TOOLKITS.get(agent_type, [])

    # 创建 Agent（发送 create_agent 事件）
    agent = ListenChatAgent(
        agent_name=agent_type.value,
        system_prompt=system_prompt,
        tools=tools,
        on_event=on_event,
    )

    if on_event:
        on_event(AgentEvent(
            event_type="create_agent",
            agent_name=agent_type.value,
            data={"tools": [t.name for t in tools]},
        ))

    return agent


# ─── Demo ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Eigent Agent 工厂 Demo")
    print("=" * 60)

    # 事件收集器
    events: list[AgentEvent] = []
    def on_event(event: AgentEvent):
        events.append(event)
        icon = {"create_agent": "🆕", "activate_agent": "🟢",
                "deactivate_agent": "🔴", "activate_toolkit": "🔧",
                "deactivate_toolkit": "🔨"}.get(event.event_type, "⚡")
        print(f"  {icon} [{event.event_type}] {event.agent_name}: "
              f"{str(event.data)[:60]}")

    # 创建 3 种 Agent（原实现 construct_workforce 会创建 8 种）
    print("\n📦 创建 Agent 团队:")
    dev = create_agent(AgentType.developer, on_event=on_event)
    browser = create_agent(AgentType.browser, on_event=on_event)
    doc = create_agent(AgentType.document, on_event=on_event)

    # 让每个 Agent 执行一个任务
    print(f"\n{'─' * 40}")
    print("🧪 Developer Agent 执行任务")
    print("─" * 40)
    dev.step("Write a hello world Python script and save it to hello.py")

    print(f"\n{'─' * 40}")
    print("🧪 Browser Agent 执行任务")
    print("─" * 40)
    browser.step("Search for the latest Python release version")

    print(f"\n{'─' * 40}")
    print("🧪 Document Agent 执行任务")
    print("─" * 40)
    doc.step("Write a brief README for a Python web scraper project")

    # 事件汇总
    print(f"\n{'=' * 60}")
    print(f"📊 事件汇总 (共 {len(events)} 个)")
    print("=" * 60)
    for event_type in ["create_agent", "activate_agent", "activate_toolkit",
                        "deactivate_toolkit", "deactivate_agent"]:
        count = sum(1 for e in events if e.event_type == event_type)
        if count:
            print(f"  {event_type}: {count}")

    print("\n✅ Demo 完成")


if __name__ == "__main__":
    main()
