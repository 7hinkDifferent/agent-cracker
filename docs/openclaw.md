# OpenClaw — Deep Dive Analysis

> Auto-generated from template on 2026-02-23
> Repo: https://github.com/openclaw/openclaw
> Analyzed at commit: [`ea47ab2`](https://github.com/openclaw/openclaw/tree/ea47ab29bd6d92394185636a27c3572c19aac8e5) (2026-02-23)

## 1. Overview & Architecture

### 项目定位

OpenClaw 是一个**多通道个人 AI 助手平台**，核心编码引擎基于 pi-agent（已在 [docs/pi-agent.md](pi-agent.md) 中分析），在其之上构建了 Gateway 控制面、13+ 消息通道适配、语义记忆、Docker 沙箱、定时调度、子 Agent 编排、语音/Canvas 多模态、51+ Skills 生态等平台能力。OpenClaw 是典型的"从 Coding Agent 进化为 Agent 平台"的案例。

### 技术栈

- **语言**: TypeScript 5+ (ESM)
- **运行时**: Node.js 22+（兼容 Bun）
- **包管理**: pnpm workspace（monorepo）
- **构建**: tsdown（快速 bundler）
- **格式/检查**: Oxlint + Oxfmt
- **测试**: Vitest（V8 coverage，70% 阈值）
- **核心引擎**: `@mariozechner/pi-coding-agent` v0.54.1（内嵌，非子进程）

| 类别 | 关键依赖 |
|------|----------|
| Agent 核心 | @mariozechner/pi-coding-agent, @mariozechner/pi-agent-core, @mariozechner/pi-ai |
| Schema | @sinclair/typebox |
| 通道 | discord.js, @slack/socket-mode, telegraf, whatsapp-web.js, @whiskeysockets/baileys |
| 记忆 | better-sqlite3, openai (embeddings), croner (cron) |
| 多模态 | elevenlabs (TTS), sharp (图像), puppeteer (浏览器) |
| 原生应用 | Swift/SwiftUI (macOS/iOS), Kotlin (Android) |

### 核心架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                        消息通道层                                │
│  Discord │ Slack │ Telegram │ Signal │ iMessage │ WhatsApp │ ... │
│  + 31 个 extension 通道（Matrix, Teams, Zalo, IRC, Nostr...）     │
└──────────────────────────┬───────────────────────────────────────┘
                           │ webhook / polling / WebSocket
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│              Gateway (WebSocket RPC Server :18789)                │
│  ┌─────────────┐ ┌──────────────┐ ┌───────────────┐             │
│  │ 路由引擎     │ │ Session 管理  │ │ 认证 & 限流    │             │
│  │ resolve-     │ │ JSONL 持久化  │ │ Auth Profiles │             │
│  │ route.ts     │ │ 写锁 + 修复   │ │ Rate Limit    │             │
│  └──────┬──────┘ └──────┬───────┘ └───────────────┘             │
└─────────┼───────────────┼────────────────────────────────────────┘
          │               │
          ▼               ▼
┌──────────────────────────────────────────────────────────────────┐
│           Auto-Reply Dispatcher（编排层）                         │
│  dispatchInboundMessage() → agent-runner-execution.ts            │
│  ┌──────────────┐ ┌────────────────┐ ┌───────────────────┐      │
│  │ Model Fallback│ │ Typing 指示器   │ │ Block-Reply 流式   │      │
│  │ + Cooldown    │ │ + 阶段管理     │ │ 分块回传          │      │
│  └──────────────┘ └────────────────┘ └───────────────────┘      │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│           Pi-Agent (Embedded Library @v0.54.1)                   │
│  runEmbeddedPiAgent() — 同进程内嵌调用                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐      │
│  │ Agent Loop│ │ Session  │ │ Tool 执行 │ │ Compaction     │      │
│  │ (双层循环) │ │ Manager │ │ (47 tools)│ │ (结构化摘要)    │      │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘      │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    LLM Providers                                 │
│  Anthropic │ OpenAI │ Google │ Ollama │ OpenRouter │ Mistral │...│
└──────────────────────────────────────────────────────────────────┘
```

### 关键文件/目录

| 文件/目录 | 作用 |
|-----------|------|
| `openclaw.mjs` | CLI 入口（bin 入口点） |
| `src/gateway/` | Gateway WebSocket RPC 服务器、协议定义 |
| `src/routing/resolve-route.ts` | 通道→Agent 路由引擎（binding 匹配） |
| `src/agents/pi-embedded-runner/run.ts` | Pi-Agent 内嵌运行器（核心调用入口） |
| `src/agents/pi-embedded-runner/run/attempt.ts` | 单次运行尝试（createAgentSession、tool 注入） |
| `src/agents/tool-catalog.ts` | 47 个核心 tool 定义（4 档 profile） |
| `src/agents/tool-policy.ts` | Tool 权限策略（allow/deny + owner-only） |
| `src/agents/system-prompt.ts` | System prompt 构建器（14+ sections, 696 行） |
| `src/memory/` | 语义记忆系统（embedding + hybrid search） |
| `src/agents/sandbox/` | Docker 沙箱隔离 |
| `src/cron/` | 定时调度服务 |
| `src/auto-reply/` | 消息分发与回复编排 |
| `src/channels/` | 通道抽象层（Dock 接口） |
| `extensions/` | 31+ 扩展（通道、记忆后端、语音等） |
| `skills/` | 51+ 内置 Skills（1Password、GitHub、Notion 等） |
| `apps/` | 原生伴侣应用（macOS/iOS/Android） |

---

## 2. Agent Loop（主循环机制）

> **核心引用**: OpenClaw 的 Agent Loop 直接使用 pi-agent 的双层循环 + steering/follow-up 队列，详见 [docs/pi-agent.md D2](pi-agent.md#2-agent-loop主循环机制)。

### OpenClaw 的定制

OpenClaw 在 pi-agent 循环之上包了一层**编排层**（`auto-reply/reply/agent-runner-execution.ts`），增加了：

1. **Model Fallback Chain**: `runWithModelFallback()` 在主 provider 失败时自动切换到备用 provider（含 cooldown 追踪）
2. **Auth Profile 轮转**: 多个 API key profile 按优先级依次尝试，失败后标记 cooldown
3. **Session 写锁**: `acquireSessionWriteLock()` 防止并发写入同一 session
4. **Compaction 超时保护**: 检测 compaction 超时并降级处理
5. **Anthropic 安全字符串清理**: 自动剥离 `ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL` 防止投毒

```typescript
// src/agents/pi-embedded-runner/run.ts — 核心调用链
// 1. 解析 model + auth profile
const apiKeyInfo = await getApiKeyForModel(model, ...);
// 2. 构建 payload（system prompt + tools + session）
const payloads = await buildEmbeddedRunPayloads(params);
// 3. 执行内嵌 Pi-Agent（含 fallback）
const result = await runWithModelFallback({
  run: () => runEmbeddedAttempt(attemptParams),
  onFallback: (reason) => { /* 切换 provider */ },
});
// 4. 返回 EmbeddedPiRunResult（含 usage、transcript 变更）
```

### 终止条件

在 pi-agent 的基础上额外增加：
- **Auth profile 全部耗尽**: 所有 provider 都失败 → FailoverError
- **Context overflow + compaction 超时**: 双重失败 → 降级错误
- **Billing 错误**: 账号额度不足 → 立即停止并提示

---

## 3. Tool/Action 系统

> **核心引用**: Tool 执行基于 pi-agent 的 AgentTool 接口 + TypeBox schema 校验，详见 [docs/pi-agent.md D3](pi-agent.md#3-toolaction-系统)。

### OpenClaw 的 Tool 扩展

OpenClaw 在 pi-agent 的 7 个基础 tool（read/write/edit/bash/grep/find/ls）之上，扩展到 **47 个核心 tool**，组织为 11 个 section：

| Section | Tools | 功能 |
|---------|-------|------|
| Files | read, write, edit, apply_patch | 文件操作（+ OpenAI apply_patch 兼容） |
| Runtime | exec, process | Shell 执行 + 后台进程管理 |
| Web | web_search, web_fetch | 网络搜索与内容获取 |
| Memory | memory_search, memory_get | 语义记忆检索 + 文件读取 |
| Sessions | sessions_list, sessions_history, sessions_send, sessions_spawn | 跨 session 通信 + 子 agent 生成 |
| UI | browser, canvas, nodes | 浏览器自动化、Canvas 可视化、设备节点 |
| Messaging | message, cron, gateway | 消息发送、定时任务、网关控制 |
| Automation | （plugin 扩展） | 自动化工具 |
| Nodes | （设备节点） | macOS/iOS/Android 设备操作 |
| Agents | subagents | 子 agent 管理（list/kill/steer） |
| Media | image, tts | 图像生成、语音合成 |

### Tool Profile 机制

4 档渐进 profile 控制 tool 可用性：

```typescript
// src/agents/tool-catalog.ts
type ToolProfileId = "minimal" | "coding" | "messaging" | "full";

// "minimal" → 只有基础 read/write/exec
// "coding"  → + memory, sessions, web
// "messaging" → + message, cron
// "full"     → 所有 tool
```

### Tool Policy Pipeline

```
Tool 请求 → allow/deny list 过滤 → profile 过滤 → owner-only 检查
  → sandbox 策略覆盖 → plugin tool 扩展 → 最终可用 tool 集
```

owner-only tool（如 `whatsapp_login`、`cron`、`gateway`）只允许认证的 owner 使用。

---

## 4. Prompt 工程

> **核心引用**: Pi-agent 的 prompt 构建基础见 [docs/pi-agent.md D4](pi-agent.md#4-prompt-工程)。

### OpenClaw 的 System Prompt 结构

OpenClaw 完全重写了 system prompt 构建器（`src/agents/system-prompt.ts`, 696 行），支持 3 种模式：

| 模式 | 用途 | 包含的 sections |
|------|------|----------------|
| `full` | 主 agent | 全部 14+ sections |
| `minimal` | 子 agent | 仅 Tooling + Workspace + Runtime |
| `none` | 纯身份 | 一行身份声明 |

**full 模式的 sections（按顺序）**：

1. **Tooling** — 可用 tool 列表及描述（动态生成）
2. **Tool Call Style** — 调用规范（避免低风险操作的冗余叙述）
3. **Safety** — 安全约束（无独立目标、优先监督）
4. **CLI Quick Reference** — openclaw 命令速查
5. **Skills** — 从 `skills/` 加载匹配的 SKILL.md（每轮最多读 1 个）
6. **Memory Recall** — 要求先 `memory_search` 再回答历史相关问题
7. **Authorized Senders** — Owner 身份（SHA256 hash 或明文）
8. **Date & Time** — 用户时区上下文
9. **Workspace** — 工作目录 + 沙箱路径
10. **Documentation** — 本地文档路径 + docs.openclaw.ai
11. **Sandbox** — 容器路径、browser bridge、elevated exec（条件注入）
12. **Messaging** — 通道路由、reply tags（`[[reply_to_current]]`）、inline buttons
13. **Runtime** — `agent=<id>, host=<name>, os=<system>, model=<name>, channel=<ch>, capabilities=<list>`
14. **Project Context** — SOUL.md 人格定义 + 用户自定义上下文文件

### 动态 Prompt 组装

```
基础身份 → + 可用 tool 摘要 → + channel 特定指令
  → + Skills 匹配结果 → + Memory 指令
  → + SOUL.md 人格注入 → + 沙箱环境描述
  → + Plugin hooks (before_prompt_build / before_agent_start)
```

Plugin hooks 可在构建前/后修改 prompt 内容。

### Prompt 模板位置

| 文件 | 用途 |
|------|------|
| `src/agents/system-prompt.ts` | 主 system prompt 构建器 |
| `src/agents/system-prompt-params.ts` | 参数解析 |
| `src/agents/pi-embedded-runner/system-prompt.ts` | 内嵌运行器 prompt 覆盖 |
| `skills/*/SKILL.md` | 按需注入的 Skill 定义 |
| 用户 `SOUL.md` | 人格/语调定义 |

---

## 5. 上下文管理

> **核心引用**: Session 内 compaction 策略直接使用 pi-agent 的结构化摘要机制，详见 [docs/pi-agent.md D5](pi-agent.md#5-上下文管理)。

### OpenClaw 的定制

1. **Compaction Safeguard 扩展**: 限制历史占比（如最多 50% context window），防止 compaction 超时
2. **Context Pruning（cache-TTL）**: 按缓存 TTL 选择性裁剪 tool 结果
3. **Tool Result Truncation**: `truncateOversizedToolResultsInSession()` — 超大 tool 输出自动截断
4. **DM History Limit**: 非主 session（DM 通道）限制历史 turn 数（`getDmHistoryLimitFromSessionKey()`）
5. **Bootstrap Files**: 自动注入 AGENTS.md / TOOLS.md / context 文件，带大小限制（`resolveBootstrapMaxChars()`）

---

## 6. 错误处理与恢复

> **核心引用**: 基础重试策略来自 pi-agent，详见 [docs/pi-agent.md D6](pi-agent.md#6-错误处理与恢复)。

### OpenClaw 的增强

**多层 Failover 系统**：

| 错误类型 | 检测方式 | 恢复策略 |
|---------|---------|---------|
| Auth 失败 | `isAuthAssistantError()` | 切换 Auth Profile → 重试 |
| Rate Limit | `isRateLimitAssistantError()` | 标记 cooldown → 切换 provider |
| Billing 超限 | `isBillingAssistantError()` | 停止 + 格式化错误信息 |
| Context Overflow | `isLikelyContextOverflowError()` | 触发 compaction → 重试 |
| Compaction 失败 | `isCompactionFailureError()` | 降级到截断模式 |
| 超时 | `isTimeoutErrorMessage()` | 记录 + 返回部分结果 |
| 图片尺寸 | `parseImageSizeError()` | 调整图片大小 → 重试 |

**Failover 分类器**（`classifyFailoverReason()`）：
```typescript
type FailoverReason =
  | "auth" | "billing" | "rate-limit" | "timeout"
  | "context-overflow" | "compaction-failure"
  | "image-size" | "image-dimension" | "unknown";
```

**Session 修复**:
- `repairSessionFileIfNeeded()`: JSONL 文件损坏自动修复
- `sanitizeToolUseResultPairing()`: Tool call/result 配对修复
- `guardSessionManager()`: Session 写入保护包装

---

## 7. 关键创新点

### 独特设计

#### 1. 内嵌引擎 + 平台编排分层

OpenClaw 不重造 Agent 核心，而是将 pi-agent 作为**库**内嵌（`runEmbeddedPiAgent()`），在其之上构建平台层。这实现了：
- 核心编码能力跟随 pi-agent 升级
- 平台特性（通道、记忆、调度）与核心解耦
- 同进程调用，零 RPC 开销

#### 2. Tool Profile 渐进解锁

4 档 profile（minimal → coding → messaging → full）让同一 Agent 在不同场景下暴露不同能力，而非全部工具平铺。子 agent 用 `minimal`，编码场景用 `coding`，全功能用 `full`。

#### 3. 多 Provider Failover + Auth Profile 轮转

不止在 LLM 层面 failover（pi-agent 已有），还在**身份认证层面**轮转：多个 API key 按优先级尝试，失败后进入 cooldown，自动切换到下一个。

#### 4. 子 Agent 编排（spawn + steer + kill）

完整的子 agent 生命周期管理：
- `sessions_spawn`: 派生独立 agent（one-shot 或 persistent）
- `subagents steer`: 运行中向子 agent 发送方向调整
- `subagents kill`: 终止子 agent
- 深度限制防止无限派生

#### 5. 混合记忆搜索

Vector（70%）+ BM25 文本（30%）加权混合检索，支持 MMR 去重、时间衰减、查询扩展。5 种 embedding provider 可选。

### 值得借鉴的模式

1. **内嵌引擎模式**: 复用成熟的 agent 内核而非重写，聚焦平台差异化
2. **Tool Profile**: 场景化工具集合，避免工具过载
3. **Session Key 路由**: `{agentId}:{channel}:{accountId}:{peerKind}:{peerId}` 复合键实现精细路由
4. **Plugin Hook Pipeline**: `before_prompt_build` / `before_agent_start` 让插件在不修改核心的情况下介入
5. **Failover 分类器**: 按错误类型分类而非统一重试，每种错误有针对性的恢复策略

---

## 7.5 MVP 组件清单

基于以上分析，构建最小可运行版本需要以下组件：

| 组件 | 对应维度 | 核心文件 | 建议语言 | 语言理由 |
|------|----------|----------|----------|----------|
| 通道路由 | D9 | `src/routing/resolve-route.ts` | Python | Binding 匹配逻辑纯算法 |
| Gateway RPC | D9 | `src/gateway/` | Python | WebSocket 服务可用 asyncio |
| 内嵌引擎调用 | D2 | `src/agents/pi-embedded-runner/run.ts` | Python | 模拟调用链，不需要真正内嵌 |
| Tool Profile 策略 | D3 | `src/agents/tool-catalog.ts`, `tool-policy.ts` | Python | 配置驱动逻辑 |
| System Prompt 构建 | D4 | `src/agents/system-prompt.ts` | Python | 字符串拼接 |
| 记忆检索 | D10 | `src/memory/`, `src/agents/memory-search.ts` | Python | 可用 SQLite + sentence-transformers |
| Docker 沙箱 | D11 | `src/agents/sandbox/` | Python | Docker SDK 可用 |
| Cron 调度 | D11 | `src/cron/schedule.ts` | Python | 纯调度算法 |
| 子 Agent 编排 | D11 | `src/agents/tools/subagents-tool.ts` | Python | 进程管理 |

---

## 8. 跨 Agent 对比

### vs aider / codex-cli / pi-agent

| 维度 | openclaw | aider | codex-cli | pi-agent |
|------|----------|-------|-----------|----------|
| **定位** | 多通道 AI 助手平台 | 终端编码助手 | CLI 编码 agent | 模块化 agent 工具包 |
| **语言** | TypeScript | Python | Rust + TS | TypeScript |
| **Agent Loop** | 内嵌 pi-agent + 编排层 | 三层嵌套 | tokio 多路复用 | 双层循环 + steering |
| **Tool 数量** | 47+ 核心 + plugin | 7 文本命令 | 6 function calling | 7 原生 tool calling |
| **Tool 管理** | 4 档 profile + policy | 无分级 | 3 级审批 | 无分级 |
| **通道** | 13+ 消息平台 | 仅 CLI | 仅 CLI | CLI + Slack Bot |
| **记忆** | Vector + BM25 混合检索 | Git 集成 | 无 | 无（session 内 compaction） |
| **安全** | Docker 沙箱 + 信任分级 | Git auto-commit | 平台沙箱 + 网络代理 | 无 |
| **调度** | Cron + Heartbeat | 无 | 无 | 无 |
| **子 Agent** | spawn + steer + kill | 无 | 无 | 无 |
| **扩展** | Plugin SDK + 31 extension + 51 skills | 无 | Hooks + MCP | 深度扩展系统 |

### 总结

OpenClaw 代表了 **Coding Agent 向 Agent 平台进化**的典型路径：不重造 agent 内核（直接内嵌 pi-agent），而是在其之上构建多通道接入、语义记忆、安全隔离、自主调度、子 agent 编排等平台能力。其核心架构决策——**Gateway 作为控制面 + 内嵌引擎 + Plugin 生态**——使得平台能力的扩展不影响编码核心的稳定性。47 个 tool 的 profile 分级机制、多 provider failover + auth 轮转、子 agent 生命周期管理是其最有价值的创新点。与纯 coding agent 相比，OpenClaw 的独特价值在于**连接**——将 AI 编码能力连接到用户已有的通信工具、工作流和设备中。

---

## 9. 通道层与网关 _(平台维度)_

### 通道架构

OpenClaw 采用 **Gateway + Channel Dock** 架构：

```
外部消息 → Channel Adapter（协议适配） → ChannelDock（标准化接口）
  → Gateway RPC → resolve-route.ts（binding 匹配）
  → Agent Session（复合 session key）
```

Gateway 是 WebSocket RPC 服务器（默认端口 18789），所有通道通过 RPC 调用与之通信。

### 支持的通道

| 通道 | 集成方式 | 来源 |
|------|---------|------|
| Discord | Bot API (discord.js) | 内置 |
| Slack | Socket Mode (@slack/socket-mode) | 内置 |
| Telegram | Bot API (telegraf) | 内置 |
| Signal | Signal CLI bridge | 内置 |
| iMessage | AppleScript / BlueBubbles relay | 内置 |
| WhatsApp | WhatsApp Web (baileys) | 内置 |
| LINE | Messaging API | 内置 |
| WebChat | HTTP/WebSocket | 内置 |
| Matrix | matrix-js-sdk | extension |
| Microsoft Teams | Bot Framework | extension |
| Google Chat | Google API | extension |
| Zalo / Zalo Personal | Zalo API | extension |
| IRC, Nostr, Twitch, Feishu, Mattermost, Nextcloud Talk, Synology Chat, Tlon | 各自协议 | extension |

### 消息标准化

Channel Dock 接口统一了不同通道的能力：

```typescript
// src/channels/dock.ts — 通道能力抽象
interface ChannelDock {
  capabilities: { text, media, threading, mentions, ... };
  commands: { parse, validate };
  streaming: { blockReplyCoalescing, chunking };
  groups: { mentionRequired, groupMessageHandling };
  threading: { replyContext };
}
```

### 路由引擎

`resolve-route.ts` 通过 binding 匹配将消息路由到 agent session：

```typescript
type ResolvedAgentRoute = {
  agentId: string;
  sessionKey: string;    // "{agentId}:{mainKey}:{channel}:{accountId}:{peerKind}:{peerId}"
  matchedBy:
    | "binding.peer"          // 精确 peer 匹配
    | "binding.peer.parent"   // 父 peer（线程继承）
    | "binding.guild+roles"   // Discord guild + 角色
    | "binding.guild"         // Discord guild
    | "binding.team"          // Slack team
    | "binding.account"       // 账号级
    | "binding.channel"       // 通道级
    | "default";              // 默认 agent
};
```

### 多模态支持

- **语音**: TTS（ElevenLabs）+ Voice Wake（macOS/iOS/Android）+ Voice Call extension
- **Canvas**: A2UI 声明式 UI 格式，agent 驱动可视化
- **Browser**: Chrome DevTools Protocol 控制，双模式（extension relay + headless）
- **图片**: 自动缩放至 MAX_IMAGE_BYTES，历史消息图片注入

---

## 10. 记忆与持久化 _(平台维度)_

### 持久化架构

| 存储类型 | 格式 | 位置 |
|---------|------|------|
| Session 记录 | JSONL（追加写入） | `~/.openclaw/agents/<agentId>/sessions/*.jsonl` |
| Agent 配置 | JSON | `~/.openclaw/agents/<agentId>/` |
| 记忆索引 | SQLite | `~/.openclaw/memory/<agentId>.sqlite` |
| 凭据 | 加密文件 | `~/.openclaw/credentials/` |
| Cron 任务 | JSON | 配置存储 |

Session 持久化直接使用 pi-agent 的 JSONL SessionManager（Parent-ID DAG 链、分支支持、崩溃安全追加写入）。

### 长期记忆

**混合检索架构**：

```
用户查询 → 查询扩展（可选） → 并行执行:
  ├─ Vector 检索（embedding 相似度，权重 0.7）
  └─ BM25 文本检索（关键词匹配，权重 0.3）
→ 归一化分数 → MMR 去重（λ=0.7） → 时间衰减（半衰期 30 天）
→ Top-K 结果（默认 6 条，minScore 0.35）
```

**Embedding Provider 支持**：

| Provider | 模型 | 特点 |
|----------|------|------|
| OpenAI | text-embedding-3-small | 默认选择 |
| Gemini | gemini-embedding-001 | Google 生态 |
| Voyage | voyage-4-large | 高质量 |
| Mistral | mistral-embed | 开源友好 |
| Local | node-llama-cpp | 本地运行 |

**记忆文件结构**：
- `MEMORY.md` — 核心记忆文件
- `memory/*.md` — 分主题记忆文件
- 分块参数：400 tokens/chunk，80 tokens overlap

**同步策略**：
- Session 开始时同步
- 每次搜索时同步
- 文件系统 watch（1500ms debounce）
- 可配置间隔定时同步

### 状态恢复

- **Session 修复**: `repairSessionFileIfNeeded()` 自动修复损坏的 JSONL
- **Tool call 配对修复**: `sanitizeToolUseResultPairing()` 修复不完整的 tool call/result
- **Session 分支**: 继承 pi-agent 的 parentSession 分支机制
- **写锁保护**: `acquireSessionWriteLock()` 防止并发损坏

---

## 11. 安全模型与自治 _(平台维度)_

### 信任分级

OpenClaw 通过 **Owner 认证 + 通道来源** 实现信任分级：

| 信任级别 | 来源 | 能力 |
|---------|------|------|
| Owner（operator） | 本地 CLI / 认证的 allowlist 号码 | 全部 tool + owner-only tool |
| Allowed Sender | 通道 allowlist 配置 | 按 tool policy 受限 |
| Unknown Sender | 非 allowlist | 基础交互，无 tool |

**owner-only tools**：`whatsapp_login`、`cron`、`gateway` — 只有 Owner 能使用。

### 沙箱策略

**Docker 沙箱隔离**：

```
Host Workspace ─── mount ──→ /agent/workspace (容器内)
                              │
Container ───────────────────│── exec tool（沙箱内执行）
                              │── read/write/edit（通过 bridge 访问）
                              │── browser（可选 sandbox-browser 容器）
                              └── elevated exec（需审批）
```

| 沙箱配置项 | 说明 |
|-----------|------|
| SandboxScope | agent 级 / workspace 级 |
| WorkspaceAccess | none / read / write / admin |
| Elevated Exec | ask（需确认）/ auto-approve |
| Browser Bridge | 沙箱内浏览器 + NoVNC 观察 |

**安全校验**（`validate-sandbox-security.ts`）：
- 防止特权提升
- 校验挂载路径（禁止父目录逃逸）
- 限制危险 bind mount

### 自主调度

**Cron 系统**（`src/cron/`）：

3 种调度类型：
```typescript
// src/cron/schedule.ts
type ScheduleKind = "at" | "every" | "cron";
// "at"    → 绝对时间点（ISO 格式）
// "every" → 相对间隔（如 every 30m）
// "cron"  → cron 表达式（使用 Croner 库）
```

**Heartbeat 机制**：
- Gateway 定期发送心跳检测
- Agent 返回 `HEARTBEAT_OK` 表示空闲
- 有待处理工作时正常回复

### 多 Agent 协作

**子 Agent 编排**：

```
Main Agent
  │
  ├─ sessions_spawn(task="分析日志", mode="run")
  │   → Sub-Agent A（独立 session，minimal prompt）
  │   → 完成后自动 announce 回 Main Agent
  │
  ├─ subagents steer(message="优先处理错误日志")
  │   → 中途调整 Sub-Agent 方向
  │
  └─ subagents kill(agentId)
      → 终止子 agent
```

**深度限制**: `MAX_SPAWN_DEPTH` 防止无限递归派生。

**跨 Session 通信**: `sessions_send` tool 允许 agent 向其他 session 发送消息，实现横向协作。

---

## 12. 其他特色机制 _(平台维度)_

### 机制列表

| 机制 | 简述 | 关键代码 |
|------|------|----------|
| Skills 生态 | 51+ 内置 Skill，按需注入 prompt | `skills/*/SKILL.md` |
| Plugin SDK | Extension 开发接口，hook 管道 | `src/plugin-sdk/`, `src/extensionAPI.ts` |
| Companion Apps | macOS/iOS/Android 原生应用 | `apps/` |
| A2UI Canvas | 声明式 agent 驱动 UI | `src/canvas-host/`, `vendor/a2ui/` |
| 设备节点 | Node 工具控制远程设备 | `src/node-host/` |
| Onboarding Wizard | 引导式初始化设置 | `src/wizard/` |
| Media Understanding | 图片/视频/链接自动理解 | `src/media/`, `src/media-understanding/` |
| Reply Tags | `[[reply_to_current]]` 原生回复 | system prompt 注入 |

### 详细分析

#### Skills 生态

51+ 个 Skill 覆盖生产力（1Password、Notion、Obsidian）、开发（GitHub、coding-agent）、通信（Discord、Slack）、媒体（图像生成、语音）、智能家居（OpenHue、Sonos）等场景。每个 Skill 是一个包含 `SKILL.md` 的目录，agent 在对话开始时扫描可用 skills，最多每轮读取 1 个匹配的 SKILL.md。

#### Plugin SDK

开发者通过 `openclaw/plugin-sdk` 构建 extension：
- 注册自定义 tool、通道、hook
- Hook 管道：`before_prompt_build` → `before_agent_start` → `tool_call` → `tool_result`
- 独立 `package.json`，通过 `npm install --omit=dev` 安装

#### Companion Apps

| 平台 | 技术 | 功能 |
|------|------|------|
| macOS | Swift/SwiftUI | 菜单栏 Gateway、Voice Wake |
| iOS | Swift/SwiftUI | 语音交互、设备节点 |
| Android | Kotlin/Gradle | 设备节点、消息推送 |

Apps 通过 WebSocket 连接本地 Gateway，提供原生 UI 和设备能力（摄像头、屏幕录制等）。

#### A2UI Canvas

声明式 UI 格式（非可执行代码）——agent 从预定义组件目录中选择 UI 元素组合，客户端渲染。跨 macOS、iOS、Android 一致显示。
