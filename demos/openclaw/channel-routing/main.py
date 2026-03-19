"""
OpenClaw — Channel Routing 机制复现

复现 OpenClaw 的 Binding 匹配路由引擎：
- 8 级优先级匹配（binding.peer → default）
- 复合 Session Key 构建（{agentId}:{channel}:{peerKind}:{peerId}）
- DM scope 策略（main / per-peer / per-channel-peer）

对应源码: src/routing/resolve-route.ts, src/routing/session-key.ts
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── 数据模型 ──────────────────────────────────────────────────────

class ChatType(str, Enum):
    DIRECT = "direct"
    GROUP = "group"
    CHANNEL = "channel"


class DmScope(str, Enum):
    """DM 消息的 session 分配策略"""
    MAIN = "main"                         # 所有 DM 汇入主 session
    PER_PEER = "per-peer"                 # 按联系人分 session
    PER_CHANNEL_PEER = "per-channel-peer" # 按通道+联系人分 session


class MatchedBy(str, Enum):
    """路由匹配级别（优先级从高到低）"""
    BINDING_PEER = "binding.peer"
    BINDING_PEER_PARENT = "binding.peer.parent"
    BINDING_GUILD_ROLES = "binding.guild+roles"
    BINDING_GUILD = "binding.guild"
    BINDING_TEAM = "binding.team"
    BINDING_ACCOUNT = "binding.account"
    BINDING_CHANNEL = "binding.channel"
    DEFAULT = "default"


@dataclass
class BindingMatch:
    """路由绑定的匹配条件"""
    channel: str
    account_id: str = "*"            # "*" 表示匹配任何账号
    peer_kind: Optional[ChatType] = None
    peer_id: Optional[str] = None
    guild_id: Optional[str] = None   # Discord 服务器 ID
    team_id: Optional[str] = None    # Slack Team ID
    roles: list[str] = field(default_factory=list)


@dataclass
class AgentBinding:
    """路由绑定：将消息匹配条件映射到 Agent"""
    agent_id: str
    match: BindingMatch


@dataclass
class InboundMessage:
    """入站消息上下文"""
    channel: str
    account_id: str = "default"
    peer_kind: ChatType = ChatType.DIRECT
    peer_id: str = ""
    parent_peer_id: Optional[str] = None  # 线程的父消息 peer
    guild_id: Optional[str] = None
    team_id: Optional[str] = None
    member_role_ids: list[str] = field(default_factory=list)


@dataclass
class ResolvedRoute:
    """路由结果"""
    agent_id: str
    channel: str
    account_id: str
    session_key: str
    main_session_key: str
    matched_by: MatchedBy


# ── 辅助函数 ──────────────────────────────────────────────────────

def normalize_agent_id(raw: str) -> str:
    """规范化 agent ID：小写，去除无效字符"""
    cleaned = re.sub(r"[^a-z0-9_-]", "", raw.lower().strip())
    return cleaned or "main"


def build_session_key(
    agent_id: str,
    channel: str,
    peer_kind: ChatType,
    peer_id: str,
    dm_scope: DmScope = DmScope.MAIN,
) -> str:
    """
    构建复合 Session Key

    DM 消息根据 dm_scope 策略分配：
    - main:             agent:{agentId}:main
    - per-peer:         agent:{agentId}:direct:{peerId}
    - per-channel-peer: agent:{agentId}:{channel}:direct:{peerId}

    Group/Channel 消息始终按通道+对象分配：
    - agent:{agentId}:{channel}:{peerKind}:{peerId}
    """
    if peer_kind == ChatType.DIRECT:
        if dm_scope == DmScope.PER_CHANNEL_PEER:
            return f"agent:{agent_id}:{channel}:direct:{peer_id}"
        if dm_scope == DmScope.PER_PEER:
            return f"agent:{agent_id}:direct:{peer_id}"
        return f"agent:{agent_id}:main"

    return f"agent:{agent_id}:{channel}:{peer_kind.value}:{peer_id}"


# ── 路由引擎 ──────────────────────────────────────────────────────

class RoutingEngine:
    """
    OpenClaw 路由引擎复现

    8 级优先级匹配（从高到低）:
    1. binding.peer         — 精确 peer 匹配
    2. binding.peer.parent  — 线程父 peer 匹配
    3. binding.guild+roles  — Discord guild + 角色匹配
    4. binding.guild        — Discord guild 匹配
    5. binding.team         — Slack team 匹配
    6. binding.account      — 指定账号匹配
    7. binding.channel      — 通道级通配匹配
    8. default              — 全局默认 agent
    """

    def __init__(
        self,
        bindings: list[AgentBinding],
        default_agent_id: str = "main",
        dm_scope: DmScope = DmScope.MAIN,
    ):
        self.bindings = bindings
        self.default_agent_id = normalize_agent_id(default_agent_id)
        self.dm_scope = dm_scope

    def _filter_bindings(self, channel: str, account_id: str) -> list[AgentBinding]:
        """第一步：按 channel + accountId 预过滤"""
        result = []
        for b in self.bindings:
            if b.match.channel != channel:
                continue
            pat = b.match.account_id
            if pat == "*" or pat == account_id:
                result.append(b)
        return result

    def resolve(self, msg: InboundMessage) -> ResolvedRoute:
        """执行路由匹配，返回 ResolvedRoute"""
        candidates = self._filter_bindings(msg.channel, msg.account_id)

        # ── Tier 1: binding.peer（精确 peer 匹配）────────
        for b in candidates:
            if (
                b.match.peer_kind is not None
                and b.match.peer_id is not None
                and b.match.peer_kind == msg.peer_kind
                and b.match.peer_id == msg.peer_id
            ):
                return self._build_route(b.agent_id, msg, MatchedBy.BINDING_PEER)

        # ── Tier 2: binding.peer.parent（线程继承）────────
        if msg.parent_peer_id:
            for b in candidates:
                if (
                    b.match.peer_id is not None
                    and b.match.peer_id == msg.parent_peer_id
                ):
                    return self._build_route(b.agent_id, msg, MatchedBy.BINDING_PEER_PARENT)

        # ── Tier 3: binding.guild+roles ────────
        if msg.guild_id and msg.member_role_ids:
            for b in candidates:
                if (
                    b.match.guild_id is not None
                    and b.match.guild_id == msg.guild_id
                    and b.match.roles
                    and any(r in msg.member_role_ids for r in b.match.roles)
                ):
                    return self._build_route(b.agent_id, msg, MatchedBy.BINDING_GUILD_ROLES)

        # ── Tier 4: binding.guild ────────
        if msg.guild_id:
            for b in candidates:
                if (
                    b.match.guild_id is not None
                    and b.match.guild_id == msg.guild_id
                    and not b.match.roles  # guild-only（无角色约束）
                ):
                    return self._build_route(b.agent_id, msg, MatchedBy.BINDING_GUILD)

        # ── Tier 5: binding.team ────────
        if msg.team_id:
            for b in candidates:
                if b.match.team_id is not None and b.match.team_id == msg.team_id:
                    return self._build_route(b.agent_id, msg, MatchedBy.BINDING_TEAM)

        # ── Tier 6: binding.account（指定账号）────────
        for b in candidates:
            if b.match.account_id != "*" and b.match.peer_id is None and b.match.guild_id is None:
                return self._build_route(b.agent_id, msg, MatchedBy.BINDING_ACCOUNT)

        # ── Tier 7: binding.channel（通道通配）────────
        for b in candidates:
            if b.match.account_id == "*" and b.match.peer_id is None and b.match.guild_id is None:
                return self._build_route(b.agent_id, msg, MatchedBy.BINDING_CHANNEL)

        # ── Tier 8: default ────────
        return self._build_route(self.default_agent_id, msg, MatchedBy.DEFAULT)

    def _build_route(
        self, agent_id: str, msg: InboundMessage, matched_by: MatchedBy
    ) -> ResolvedRoute:
        aid = normalize_agent_id(agent_id)
        return ResolvedRoute(
            agent_id=aid,
            channel=msg.channel,
            account_id=msg.account_id,
            session_key=build_session_key(
                aid, msg.channel, msg.peer_kind, msg.peer_id, self.dm_scope
            ),
            main_session_key=f"agent:{aid}:main",
            matched_by=matched_by,
        )


# ── Demo ──────────────────────────────────────────────────────────

def main():
    # 配置绑定规则
    bindings = [
        # 精确 peer 绑定：Alice 的 DM 由 coder-agent 处理
        AgentBinding("coder-agent", BindingMatch(
            channel="telegram", peer_kind=ChatType.DIRECT, peer_id="alice_123"
        )),
        # Discord guild + admin 角色 → admin-agent
        AgentBinding("admin-agent", BindingMatch(
            channel="discord", guild_id="guild_001", roles=["admin", "mod"]
        )),
        # Discord guild 通配 → helper-agent
        AgentBinding("helper-agent", BindingMatch(
            channel="discord", guild_id="guild_001"
        )),
        # Slack team → team-agent
        AgentBinding("team-agent", BindingMatch(
            channel="slack", team_id="T12345"
        )),
        # Telegram 通道通配 → general-agent
        AgentBinding("general-agent", BindingMatch(
            channel="telegram", account_id="*"
        )),
    ]

    engine = RoutingEngine(bindings, default_agent_id="fallback", dm_scope=DmScope.PER_PEER)

    # 测试用例
    cases = [
        ("Tier 1: 精确 peer 匹配", InboundMessage(
            channel="telegram", peer_kind=ChatType.DIRECT, peer_id="alice_123"
        )),
        ("Tier 2: 线程父 peer 继承", InboundMessage(
            channel="telegram", peer_kind=ChatType.DIRECT,
            peer_id="thread_456", parent_peer_id="alice_123"
        )),
        ("Tier 3: guild + roles 匹配", InboundMessage(
            channel="discord", peer_kind=ChatType.GROUP, peer_id="ch_general",
            guild_id="guild_001", member_role_ids=["admin"]
        )),
        ("Tier 4: guild 通配匹配", InboundMessage(
            channel="discord", peer_kind=ChatType.GROUP, peer_id="ch_random",
            guild_id="guild_001", member_role_ids=["member"]
        )),
        ("Tier 5: Slack team 匹配", InboundMessage(
            channel="slack", peer_kind=ChatType.CHANNEL, peer_id="C_dev",
            team_id="T12345"
        )),
        ("Tier 7: 通道通配匹配", InboundMessage(
            channel="telegram", peer_kind=ChatType.DIRECT, peer_id="bob_789"
        )),
        ("Tier 8: 全局默认", InboundMessage(
            channel="whatsapp", peer_kind=ChatType.DIRECT, peer_id="user_999"
        )),
    ]

    print("=" * 72)
    print("OpenClaw Channel Routing Demo")
    print("=" * 72)

    for label, msg in cases:
        route = engine.resolve(msg)
        print(f"\n── {label} ──")
        print(f"  入站: channel={msg.channel}, peer={msg.peer_kind.value}:{msg.peer_id}")
        if msg.guild_id:
            print(f"         guild={msg.guild_id}, roles={msg.member_role_ids}")
        if msg.parent_peer_id:
            print(f"         parent_peer={msg.parent_peer_id}")
        print(f"  路由: agent={route.agent_id}, matched_by={route.matched_by.value}")
        print(f"  Key:  {route.session_key}")

    # 演示 DM Scope 策略对比
    print("\n" + "=" * 72)
    print("DM Scope 策略对比")
    print("=" * 72)

    dm_msg = InboundMessage(channel="telegram", peer_kind=ChatType.DIRECT, peer_id="alice_123")

    for scope in DmScope:
        key = build_session_key("coder-agent", "telegram", ChatType.DIRECT, "alice_123", scope)
        print(f"  {scope.value:20s} → {key}")


if __name__ == "__main__":
    main()
