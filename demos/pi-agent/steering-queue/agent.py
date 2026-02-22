"""
Steering Queue — 双消息队列 + 双层循环

复现 pi-agent 最核心的创新：Steering / Follow-up 双消息队列

核心设计：
  - Steering 队列：中断当前 tool 执行，立即影响 Agent 行为
  - Follow-up 队列：等 Agent 完成后再处理，适合追加需求
  - 两种 dequeue 模式：all（批量）/ one-at-a-time（逐条）
  - 双层循环：外层处理 follow-up，内层处理 steering

Agent Loop 结构：
  外层 while: follow-up 消息
   └─ 内层 while: LLM → tool calls → 检查 steering
       ├─ 有 tool call → 执行 tools → 检查 steering → 继续
       └─ 无 tool call → 退出内层
   └─ 检查 follow-up → 有 → 继续外层；无 → 退出

原实现: packages/agent/src/agent.ts + agent-loop.ts
"""

import asyncio
from dataclasses import dataclass, field


@dataclass
class Message:
    """简化的消息"""
    role: str   # "user" | "assistant" | "tool_result"
    content: str


@dataclass
class ToolCall:
    """模拟的 tool call"""
    name: str
    args: str
    duration: float = 0.5  # 模拟执行耗时


class Agent:
    """简化的 Agent，保留双队列 + 双层循环核心结构

    对应原实现: packages/agent/src/agent.ts
    """

    def __init__(self):
        self.steering_queue: list[Message] = []
        self.followup_queue: list[Message] = []
        self.steering_mode: str = "one-at-a-time"  # "all" | "one-at-a-time"
        self.followup_mode: str = "one-at-a-time"
        self.messages: list[Message] = []
        self._log: list[str] = []

    def steer(self, content: str) -> None:
        """用户发送 steering 消息（中断当前执行）"""
        self.steering_queue.append(Message("user", content))

    def follow_up(self, content: str) -> None:
        """用户发送 follow-up 消息（等 Agent 完成后处理）"""
        self.followup_queue.append(Message("user", content))

    def _dequeue_steering(self) -> list[Message]:
        """按模式取 steering 消息"""
        if not self.steering_queue:
            return []
        if self.steering_mode == "one-at-a-time":
            return [self.steering_queue.pop(0)]
        else:
            msgs = self.steering_queue[:]
            self.steering_queue.clear()
            return msgs

    def _dequeue_followup(self) -> list[Message]:
        """按模式取 follow-up 消息"""
        if not self.followup_queue:
            return []
        if self.followup_mode == "one-at-a-time":
            return [self.followup_queue.pop(0)]
        else:
            msgs = self.followup_queue[:]
            self.followup_queue.clear()
            return msgs

    def _log_event(self, msg: str) -> None:
        self._log.append(msg)
        print(f"    {msg}")

    async def _mock_llm(self, messages: list[Message]) -> tuple[str, list[ToolCall]]:
        """模拟 LLM 调用，根据最新消息返回预设响应"""
        await asyncio.sleep(0.1)
        last = messages[-1].content if messages else ""

        # 预设响应逻辑
        if "排序" in last or "sort" in last.lower():
            return "好的，我来实现排序函数。", [
                ToolCall("read", "src/utils.py", 0.5),
                ToolCall("edit", "src/utils.py — 添加 quick_sort", 0.8),
                ToolCall("bash", "python -m pytest tests/", 0.6),
            ]
        elif "停" in last or "stop" in last.lower() or "改" in last:
            return "好的，我已停止之前的操作，按新要求执行。", []
        elif "测试" in last or "test" in last.lower():
            return "我来运行测试。", [
                ToolCall("bash", "python -m pytest tests/ -v", 0.4),
            ]
        elif "文档" in last or "doc" in last.lower():
            return "我来生成文档。", [
                ToolCall("read", "src/utils.py", 0.3),
                ToolCall("write", "docs/api.md", 0.4),
            ]
        else:
            return f"已完成: {last}", []

    async def run(self, initial_message: str) -> list[str]:
        """Agent 主循环：双层循环 + 双队列

        对应原实现: packages/agent/src/agent-loop.ts — runLoop()
        """
        self._log.clear()
        self.messages.append(Message("user", initial_message))
        pending: list[Message] = []

        # ── 外层循环：处理 follow-up 消息 ──
        while True:
            # 注入 pending 消息
            if pending:
                for msg in pending:
                    self._log_event(f"📨 注入消息: \"{msg.content}\"")
                    self.messages.append(msg)
                pending = []

            # ── 内层循环：LLM → tool calls → steering 检查 ──
            while True:
                # 1. 调用 LLM
                self._log_event("🤖 调用 LLM...")
                text, tool_calls = await self._mock_llm(self.messages)
                self.messages.append(Message("assistant", text))
                self._log_event(f"💬 LLM: \"{text}\"")

                # 2. 无 tool call → 退出内层循环
                if not tool_calls:
                    self._log_event("⏹  无 tool call，Agent 完成当前任务")
                    break

                # 3. 执行 tool calls（逐个，每个后检查 steering）
                steering_interrupt = False
                for i, tc in enumerate(tool_calls):
                    self._log_event(f"🔧 执行 tool [{i+1}/{len(tool_calls)}]: {tc.name}({tc.args})")
                    await asyncio.sleep(tc.duration)  # 模拟执行耗时
                    self.messages.append(Message("tool_result", f"{tc.name} 完成"))
                    self._log_event(f"✅ {tc.name} 完成")

                    # ── 关键：每个 tool 执行后检查 steering ──
                    steering = self._dequeue_steering()
                    if steering:
                        self._log_event(f"⚡ Steering 中断! 跳过剩余 {len(tool_calls)-i-1} 个 tool")
                        # 跳过剩余 tool calls
                        for skipped in tool_calls[i+1:]:
                            self.messages.append(
                                Message("tool_result", f"{skipped.name} 被跳过（steering 中断）")
                            )
                            self._log_event(f"⏭  跳过: {skipped.name}")
                        pending = steering
                        steering_interrupt = True
                        break

                if steering_interrupt:
                    continue  # 回到内层循环顶部处理 steering 消息

                # 无 steering，检查是否有新的 steering
                steering = self._dequeue_steering()
                if steering:
                    pending = steering
                    continue

                # 继续内层循环（LLM 看到 tool 结果后决定下一步）

            # ── 内层循环结束，检查 follow-up ──
            followup = self._dequeue_followup()
            if followup:
                self._log_event(f"📋 处理 follow-up ({len(followup)} 条消息)")
                pending = followup
                continue

            # 无更多消息，退出
            self._log_event("🏁 Agent 完全结束")
            break

        return self._log
