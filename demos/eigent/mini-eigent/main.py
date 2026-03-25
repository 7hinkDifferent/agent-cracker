"""
Mini-Eigent — 最小完整 Agent

串联所有 MVP 组件 + 平台机制的最简可运行 agent。
复现 eigent 的完整消息流路径：通道接入 → 复杂度路由 → Workforce 编排 → 响应返回。

import 兄弟 demo 的模块，不重写代码。
"""

from __future__ import annotations

import asyncio
import json
import sys
import os
from pathlib import Path

# ─── 从兄弟 demo 导入核心模块（用 importlib 避免命名冲突）──
_demos_dir = Path(__file__).resolve().parent.parent

def _load_sibling(subdir: str):
    """加载兄弟 demo 的 main.py 模块（mock litellm 避免依赖）"""
    import importlib.util
    import types
    # Mock litellm so queue-event-loop can import without the dep installed
    if "litellm" not in sys.modules:
        sys.modules["litellm"] = types.ModuleType("litellm")
    mod_name = f"demo_{subdir.replace('-','_')}"
    mod_path = _demos_dir / subdir / "main.py"
    spec = importlib.util.spec_from_file_location(mod_name, mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod  # Register so dataclasses can resolve module
    spec.loader.exec_module(mod)
    return mod

# queue-event-loop: 队列事件循环
_qel = _load_sibling("queue-event-loop")
Action = _qel.Action
ActionData = _qel.ActionData
TaskLock = _qel.TaskLock
sse_json = _qel.sse_json

# prompt-assembly: Prompt 组装
_pa = _load_sibling("prompt-assembly")
PromptAgentType = _pa.AgentType
PromptContext = _pa.PromptContext
assemble_prompt = _pa.assemble_prompt
build_conversation_context = _pa.build_conversation_context

# toolkit-dispatch: Toolkit 分发
_td = _load_sibling("toolkit-dispatch")
TerminalToolkit = _td.TerminalToolkit
SearchToolkit = _td.SearchToolkit
HumanToolkit = _td.HumanToolkit
get_toolkits = _td.get_toolkits


# ─── Mini-Eigent Core ───────────────────────────────────────

class MiniEigent:
    """最小完整 Agent — 串联 eigent 的核心机制。

    完整消息流路径:
    1. 通道接入（Webhook/CLI 触发）
    2. 复杂度路由（简单→直接回答 / 复杂→Workforce）
    3. Agent 工厂创建 Worker
    4. Workforce 编排（分解→分配→执行）
    5. SSE 流式响应
    """

    def __init__(self) -> None:
        self.task_lock = TaskLock("mini-eigent-001")
        self.prompt_context = PromptContext(working_directory="/tmp/mini-eigent")
        self.events: list[str] = []
        self.notes: dict[str, str] = {}  # 笔记协作存储

    def _check_complexity(self, question: str) -> bool:
        """复杂度路由 — 来自 complexity-router demo 的逻辑"""
        complex_keywords = ["创建", "写代码", "build", "create", "deploy",
                           "调研", "research", "分析", "analyze", "scraper",
                           "implement", "develop", "write code"]
        q = question.lower()
        score = sum(0.2 for kw in complex_keywords if kw in q or kw in question)
        return score >= 0.2

    def _collect_tools(self, agent_type: str) -> list[dict]:
        """Toolkit 分发 — 从 toolkit-dispatch 导入"""
        toolkit_map = {
            "developer": ["terminal_toolkit", "human_toolkit", "skill_toolkit"],
            "browser": ["search_toolkit", "human_toolkit"],
            "document": ["human_toolkit"],
        }
        tool_names = toolkit_map.get(agent_type, [])
        return get_toolkits(tool_names, agent_name=f"{agent_type}_agent")

    def _assemble_prompt(self, agent_type: str) -> str:
        """Prompt 组装 — 从 prompt-assembly 导入"""
        type_map = {
            "developer": PromptAgentType.developer,
            "browser": PromptAgentType.browser,
            "document": PromptAgentType.document,
        }
        pt = type_map.get(agent_type, PromptAgentType.developer)
        return assemble_prompt(pt, self.prompt_context)

    def _emit_sse(self, event_type: str, data: dict) -> None:
        """SSE 事件发送 — 来自 sse-streaming"""
        sse = sse_json(event_type, data)
        self.events.append(sse)

    def _simulate_agent_work(self, agent_type: str, task: str) -> str:
        """模拟 Agent 执行"""
        prompt = self._assemble_prompt(agent_type)
        tools = self._collect_tools(agent_type)
        tool_names = [t["name"] for t in tools] if tools else []

        # 激活事件
        self._emit_sse("activate_agent", {
            "agent_name": f"{agent_type}_agent",
            "task": task,
            "tools": tool_names,
        })

        # 模拟工具执行
        result = f"[{agent_type}_agent] Completed: {task}"
        if tools:
            first_tool = tools[0]
            toolkit_name = first_tool.get("toolkit", "unknown")
            method_name = first_tool["name"]
            self._emit_sse("activate_toolkit", {
                "toolkit_name": toolkit_name,
                "method_name": method_name,
            })
            # 调用工具（传入模拟参数）
            try:
                func = first_tool.get("func")
                if callable(func):
                    # 工具方法需要 self + 参数，使用简单默认值
                    import inspect
                    sig = inspect.signature(func)
                    params = list(sig.parameters.keys())
                    if len(params) == 0:
                        tool_result = func()
                    else:
                        tool_result = func(task[:30])
                else:
                    tool_result = "ok"
            except Exception:
                tool_result = f"[simulated] {method_name} executed"
            self._emit_sse("deactivate_toolkit", {
                "toolkit_name": toolkit_name,
                "result": str(tool_result)[:100],
            })
            result += f" (used {method_name})"

        # 笔记协作 — 记录结果
        note_key = f"{agent_type}_findings"
        self.notes[note_key] = result

        # 停用事件
        self._emit_sse("deactivate_agent", {
            "agent_name": f"{agent_type}_agent",
            "result": result[:100],
        })
        return result

    async def handle_message(self, question: str, source: str = "cli") -> None:
        """处理消息 — 完整流路径。

        通道接入 → 复杂度路由 → 执行 → SSE 响应
        """
        print(f"\n{'=' * 50}")
        print(f"📩 消息到达 (来源: {source})")
        print(f"   内容: {question}")
        print(f"{'=' * 50}")

        # 1. 记录对话历史
        self.task_lock.add_conversation("user", question)

        # 2. 复杂度路由
        is_complex = self._check_complexity(question)
        print(f"\n  🧠 复杂度判断: {'复杂 → Workforce' if is_complex else '简单 → 直接回答'}")

        if not is_complex:
            # 简单回答
            answer = f"[Direct Answer] {question} — 这是一个简单问题的直接回答。"
            self._emit_sse("wait_confirm", {"content": answer})
            self.task_lock.add_conversation("assistant", answer)
            print(f"  ✅ 回答: {answer[:60]}...")
            return

        # 3. 确认并启动 Workforce
        self._emit_sse("confirmed", {"question": question})
        print(f"\n  🏭 Workforce 编排:")

        # 4. 任务分解（模拟 Coordinator）
        subtasks = [
            {"task": f"Research: {question}", "agent": "browser"},
            {"task": f"Implement: {question}", "agent": "developer"},
            {"task": f"Document: {question}", "agent": "document"},
        ]
        print(f"  📋 分解为 {len(subtasks)} 个子任务:")
        for st in subtasks:
            print(f"     [{st['agent']}] {st['task'][:50]}")

        # 5. 并行执行
        print(f"\n  🚀 并行执行:")
        results = []
        for st in subtasks:
            r = self._simulate_agent_work(st["agent"], st["task"])
            results.append(r)
            # 子任务状态事件
            self._emit_sse("task_state", {
                "task_id": f"sub-{subtasks.index(st)+1}",
                "state": "done",
            })

        # 6. 笔记汇总
        print(f"\n  📝 笔记协作:")
        for key, value in self.notes.items():
            print(f"     [{key}] {value[:60]}...")

        # 7. 完成
        final_result = "\n".join(results)
        self._emit_sse("end", {"result": final_result[:200]})
        self.task_lock.add_conversation("task_result", final_result)
        self.task_lock.status = "done"
        print(f"\n  🏁 任务完成")


async def main():
    print("=" * 60)
    print("Mini-Eigent — 最小完整 Agent")
    print("=" * 60)
    print("串联: 队列事件循环 + Prompt 组装 + Toolkit 分发")
    print("     + SSE 流式 + 笔记协作 + 复杂度路由")

    agent = MiniEigent()

    # ─── 场景 1: 简单问题（直接回答）─────────────────────
    await agent.handle_message("What is Python?", source="cli")

    # ─── 场景 2: 复杂任务（Workforce 编排）────────────────
    await agent.handle_message(
        "创建一个 Python web scraper 来抓取新闻标题",
        source="webhook",
    )

    # ─── 场景 3: 追问（多轮对话）─────────────────────────
    await agent.handle_message("What time is it?", source="cli")

    # ─── 汇总 ─────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("📊 运行汇总")
    print("=" * 60)

    print(f"\n  SSE 事件: {len(agent.events)} 个")
    for i, event in enumerate(agent.events, 1):
        event_type = event.split("\n")[0].replace("event: ", "")
        print(f"    {i}. {event_type}")

    print(f"\n  对话历史: {len(agent.task_lock.conversation_history)} 条")
    for entry in agent.task_lock.conversation_history:
        role = entry["role"]
        content = entry["content"][:50] + "..." if len(entry["content"]) > 50 else entry["content"]
        print(f"    [{role}] {content}")

    print(f"\n  笔记: {len(agent.notes)} 条")
    for key in agent.notes:
        print(f"    - {key}")

    print("\n✅ Mini-Eigent Demo 完成")


if __name__ == "__main__":
    asyncio.run(main())
