# OpenClaw — Channel Routing

复现 OpenClaw 的 Binding 匹配路由引擎（Dimension 9: 通道层与网关）。

## 机制说明

OpenClaw 通过 **8 级优先级绑定匹配** 将入站消息路由到正确的 Agent Session：

```
外部消息 → 按 channel + accountId 预过滤绑定列表
  → Tier 1: binding.peer         (精确联系人匹配)
  → Tier 2: binding.peer.parent  (线程父消息继承)
  → Tier 3: binding.guild+roles  (Discord 服务器 + 角色)
  → Tier 4: binding.guild        (Discord 服务器)
  → Tier 5: binding.team         (Slack Team)
  → Tier 6: binding.account      (指定账号)
  → Tier 7: binding.channel      (通道通配)
  → Tier 8: default              (全局默认 Agent)
```

路由结果包含复合 **Session Key**，支持 3 种 DM Scope 策略：

| DM Scope | Session Key 格式 | 效果 |
|----------|-----------------|------|
| `main` | `agent:{id}:main` | 所有 DM 汇入一个主 session |
| `per-peer` | `agent:{id}:direct:{peerId}` | 每个联系人独立 session |
| `per-channel-peer` | `agent:{id}:{channel}:direct:{peerId}` | 按通道+联系人独立 session |

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/routing/resolve-route.ts` | 路由引擎主逻辑 |
| `src/routing/session-key.ts` | Session Key 构建 |
| `src/routing/bindings.ts` | 绑定配置处理 |

## 运行

```bash
uv run python main.py
```

## 示例输出

```
========================================================================
OpenClaw Channel Routing Demo
========================================================================

── Tier 1: 精确 peer 匹配 ──
  入站: channel=telegram, peer=direct:alice_123
  路由: agent=coder-agent, matched_by=binding.peer
  Key:  agent:coder-agent:direct:alice_123

── Tier 3: guild + roles 匹配 ──
  入站: channel=discord, peer=group:ch_general
         guild=guild_001, roles=['admin']
  路由: agent=admin-agent, matched_by=binding.guild+roles
  Key:  agent:admin-agent:discord:group:ch_general

── Tier 8: 全局默认 ──
  入站: channel=whatsapp, peer=direct:user_999
  路由: agent=fallback, matched_by=default
  Key:  agent:fallback:direct:user_999
```

## 关键简化

| 原始实现 | Demo 简化 |
|---------|----------|
| TypeBox schema 校验绑定 | dataclass 静态结构 |
| normalizeAgentId 复杂清理 | 简化正则 |
| 支持 identity-linked IDs | 省略身份桥接 |
| per-account-channel-peer scope | 省略此 scope 变体 |
