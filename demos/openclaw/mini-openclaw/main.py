"""
OpenClaw — Mini-OpenClaw 串联 Demo

组合 MVP + 平台机制 的最小完整 agent 平台：
1. Channel Routing  → 消息路由到 Agent
2. Gateway RPC      → 通道接入控制面
3. Tool Profile     → 场景化工具选择
4. System Prompt    → 动态 prompt 组装
5. Embedded Engine  → Model fallback 调用
6. Hybrid Memory    → 长期记忆检索
7. Cron Scheduler   → 定时任务触发
8. Subagent         → 子 Agent 派生

全流程: 消息到达 → 路由 → 构建 prompt → 选工具 → 调用 LLM → 返回响应
"""

from __future__ import annotations

import sys
import os
import time
import importlib.util

# ── 导入兄弟 MVP demo 模块（目录名含连字符，需用 importlib） ─────

_PARENT = os.path.join(os.path.dirname(__file__), "..")


def _import_sibling(dir_name: str):
    """从兄弟目录的 main.py 导入模块（支持连字符目录名）"""
    mod_name = dir_name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(
        mod_name,
        os.path.join(_PARENT, dir_name, "main.py"),
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    sys.modules[mod_name] = mod  # 注册到 sys.modules，dataclass 等依赖此查找
    spec.loader.exec_module(mod)  # type: ignore
    return mod


_routing   = _import_sibling("channel-routing")
_gateway   = _import_sibling("gateway-rpc")
_tool      = _import_sibling("tool-profile")
_prompt    = _import_sibling("system-prompt-builder")
_engine    = _import_sibling("embedded-engine")
_memory    = _import_sibling("hybrid-memory")
_cron      = _import_sibling("cron-scheduler")
_subagent  = _import_sibling("subagent-orchestration")

# 重新绑定到顶层名字，方便后续引用
RoutingEngine   = _routing.RoutingEngine
AgentBinding    = _routing.AgentBinding
BindingMatch    = _routing.BindingMatch
InboundMessage  = _routing.InboundMessage
ChatType        = _routing.ChatType
DmScope         = _routing.DmScope

GatewayServer   = _gateway.GatewayServer
GatewayClient   = _gateway.GatewayClient
ResponseFrame   = _gateway.ResponseFrame

ToolPolicyPipeline = _tool.ToolPolicyPipeline
ToolPolicyConfig   = _tool.ToolPolicyConfig
ToolProfileId      = _tool.ToolProfileId
TrustLevel         = _tool.TrustLevel
CORE_TOOLS         = _tool.CORE_TOOLS

SystemPromptBuilder = _prompt.SystemPromptBuilder
PromptParams        = _prompt.PromptParams
PromptMode          = _prompt.PromptMode
ToolInfo            = _prompt.ToolInfo
SkillMatch          = _prompt.SkillMatch

EmbeddedEngine  = _engine.EmbeddedEngine
AuthProfile     = _engine.AuthProfile
MockLLM         = _engine.MockLLM
FailoverReason  = _engine.FailoverReason

HybridMemorySearch = _memory.HybridMemorySearch
MemoryChunk        = _memory.MemoryChunk

CronScheduler  = _cron.CronScheduler
Schedule       = _cron.Schedule
ScheduleKind   = _cron.ScheduleKind

SubagentOrchestrator = _subagent.SubagentOrchestrator
SpawnMode            = _subagent.SpawnMode


# ── Mini-OpenClaw 平台 ───────────────────────────────────────────

class MiniOpenClaw:
    """
    最小完整 OpenClaw 平台

    组合所有 MVP + 平台机制：
    消息 → 路由 → prompt 构建 → 工具选择 → LLM 调用 → 响应
    """

    def __init__(self):
        # 路由引擎
        self.router = RoutingEngine(
            bindings=[
                AgentBinding("coder", BindingMatch(channel="telegram", peer_kind=ChatType.DIRECT, peer_id="alice")),
                AgentBinding("helper", BindingMatch(channel="discord", account_id="*")),
            ],
            default_agent_id="main",
            dm_scope=DmScope.PER_PEER,
        )

        # 工具策略
        self.tool_pipeline = ToolPolicyPipeline(CORE_TOOLS)

        # Prompt 构建器
        self.prompt_builder = SystemPromptBuilder()

        # 内嵌引擎（正常运行）
        self.engine = EmbeddedEngine(
            profiles=[
                AuthProfile("claude-main", "anthropic", "sk-ant", "claude-sonnet-4-20250514", priority=0),
                AuthProfile("gpt-backup", "openai", "sk-oai", "gpt-4o", priority=1),
            ],
            llm=MockLLM(),
        )

        # 记忆系统
        self.memory = HybridMemorySearch()
        self._init_memory()

        # 调度器
        self.scheduler = CronScheduler()

        # 子 Agent 编排
        self.orchestrator = SubagentOrchestrator()

        # 处理日志
        self.log: list[str] = []

    def _init_memory(self):
        now = time.time()
        memories = [
            ("m1", "MEMORY.md", "用户偏好 Python 和 TypeScript", now - 86400 * 30),
            ("m2", "memory/prefs.md", "用户使用 Vim 和深色主题", now - 86400 * 7),
            ("m3", "memory/work.md", "项目使用 pnpm + vitest", now - 86400 * 1),
        ]
        for mid, path, text, created in memories:
            self.memory.add_chunk(MemoryChunk(id=mid, file_path=path, text=text, created_at=created))

    def process_message(
        self,
        channel: str,
        peer_id: str,
        text: str,
        peer_kind: ChatType = ChatType.DIRECT,
        is_owner: bool = True,
    ) -> str:
        """处理一条入站消息的完整流程"""
        self.log = []

        # ── Step 1: 路由 ──
        msg = InboundMessage(channel=channel, peer_kind=peer_kind, peer_id=peer_id)
        route = self.router.resolve(msg)
        self.log.append(f"[路由] agent={route.agent_id}, matched_by={route.matched_by.value}")
        self.log.append(f"       session_key={route.session_key}")

        # ── Step 2: 记忆检索 ──
        memory_results = self.memory.search(text, top_k=2, min_score=0.05)
        if memory_results:
            self.log.append(f"[记忆] 找到 {len(memory_results)} 条相关记忆")
            for r in memory_results:
                self.log.append(f"       → {r.chunk.text[:40]}... (score={r.decayed_score:.3f})")
        else:
            self.log.append(f"[记忆] 无相关记忆")

        # ── Step 3: 工具选择 ──
        trust = TrustLevel.OWNER if is_owner else TrustLevel.ALLOWED
        profile = ToolProfileId.CODING  # 根据路由的 agent 决定
        config = ToolPolicyConfig(profile=profile, trust_level=trust)
        tools = self.tool_pipeline.resolve(config)
        tool_infos = [ToolInfo(id=t.id, description=t.description) for t in tools[:6]]
        self.log.append(f"[工具] profile={profile.value}, trust={trust.value}, 可用={len(tools)}")

        # ── Step 4: Prompt 构建 ──
        prompt = self.prompt_builder.build(PromptParams(
            mode=PromptMode.FULL,
            agent_id=route.agent_id,
            agent_name="MiniClaw",
            model="claude-sonnet-4-20250514",
            channel=channel,
            tools=tool_infos,
            memory_enabled=True,
        ))
        self.log.append(f"[Prompt] {len(prompt)} chars, 13 sections")

        # ── Step 5: LLM 调用 ──
        result = self.engine.run(text)
        self.log.append(f"[引擎] success={result.success}, attempts={result.attempts}")
        self.log.append(f"       profile={result.final_profile}, model={result.final_model}")

        return result.response

    def schedule_task(self, name: str, interval_seconds: float, agent_id: str, task: str):
        """注册定时任务"""
        schedule = Schedule(ScheduleKind.EVERY, every_seconds=interval_seconds)
        job = self.scheduler.add_job(name, schedule, agent_id, task)
        self.log.append(f"[调度] 注册: {name} (every {interval_seconds}s)")
        return job

    def spawn_subagent(self, task: str) -> str:
        """派生子 Agent"""
        agent, msg = self.orchestrator.spawn("main", task, SpawnMode.RUN)
        self.log.append(f"[子Agent] {msg}")
        if agent:
            self.orchestrator.complete(agent.agent_id, f"完成: {task}")
            self.log.append(f"[子Agent] {agent.agent_id} 已完成")
        return msg


# ── Demo ──────────────────────────────────────────────────────────

def main():
    import asyncio

    print("=" * 72)
    print("Mini-OpenClaw — 最小完整 Agent 平台")
    print("=" * 72)

    platform = MiniOpenClaw()

    # ── 场景 1: Telegram DM（精确路由） ──
    print("\n── 场景 1: Telegram DM → coder agent ──")
    response = platform.process_message("telegram", "alice", "帮我重构 TypeScript 模块")
    for line in platform.log:
        print(f"  {line}")
    print(f"  响应: {response}")

    # ── 场景 2: Discord（通道通配路由） ──
    print("\n── 场景 2: Discord → helper agent ──")
    response = platform.process_message("discord", "bob", "查找 Python 编程资料", ChatType.GROUP)
    for line in platform.log:
        print(f"  {line}")
    print(f"  响应: {response}")

    # ── 场景 3: 未知通道（默认路由） ──
    print("\n── 场景 3: WhatsApp → default agent ──")
    response = platform.process_message("whatsapp", "charlie", "你好")
    for line in platform.log:
        print(f"  {line}")
    print(f"  响应: {response}")

    # ── 场景 4: 定时任务 + 子 Agent ──
    print("\n── 场景 4: 定时任务 + 子 Agent 派生 ──")
    platform.schedule_task("健康检查", 300, "monitor", "检查服务状态")
    platform.spawn_subagent("分析最近的错误日志")
    for line in platform.log:
        print(f"  {line}")

    # ── 架构图 ──
    print("\n── Mini-OpenClaw 架构 ──")
    print("""
    ┌─────────────────────────────────────────────────┐
    │              Mini-OpenClaw Platform              │
    │                                                  │
    │  Telegram ──┐                                    │
    │  Discord  ──┼─→ [路由引擎] → [Session Key]        │
    │  WhatsApp ──┘       │                            │
    │                     ▼                            │
    │  [记忆检索] ──→ [Prompt 构建] ←── [工具选择]       │
    │                     │                            │
    │                     ▼                            │
    │              [内嵌引擎 + Fallback]                │
    │                     │                            │
    │              ┌──────┼──────┐                     │
    │              ▼      ▼      ▼                     │
    │           Claude  GPT-4o  Gemini                 │
    │                                                  │
    │  [Cron 调度] ──→ [Heartbeat]                     │
    │  [子Agent] ──→ [spawn/steer/kill]                │
    └─────────────────────────────────────────────────┘
    """)


if __name__ == "__main__":
    main()
