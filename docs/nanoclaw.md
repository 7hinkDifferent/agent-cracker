# nanoclaw — Deep Dive Analysis

> Auto-generated from template on 2026-02-25
> Repo: https://github.com/qwibitai/nanoclaw
> Analyzed at commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147) (2026-02-25)

## 1. Overview & Architecture

### 项目定位

NanoClaw 是一个**极简个人 AI 助手**，核心理念是"小到能读完全部代码"。它将 Claude Agent SDK（即 Claude Code 运行时）放进 Docker/Apple Container 中运行，通过 WhatsApp 等消息通道接收用户指令，实现了**容器级隔离的多群组 AI 助手**。与 OpenClaw 的"大而全"路线相反，NanoClaw 追求极致的代码精简（~3,900 行 / 17% context window），鼓励用户直接 fork 并让 Claude Code 修改源码来定制功能。

### 技术栈

- **语言**: TypeScript 5.7+ (ESM)
- **运行时**: Node.js 22+
- **包管理**: npm（单 package，非 monorepo）
- **构建**: tsc（标准 TypeScript 编译）
- **测试**: Vitest
- **Agent 引擎**: `@anthropic-ai/claude-agent-sdk`（Claude Code 的编程接口）

| 类别 | 关键依赖 |
|------|----------|
| Agent 核心 | @anthropic-ai/claude-agent-sdk（容器内使用） |
| 消息通道 | @whiskeysockets/baileys（WhatsApp），技能扩展支持 Telegram/Discord/Slack/Signal |
| 数据库 | better-sqlite3（消息、任务、会话、组群注册） |
| 定时任务 | cron-parser（cron/interval/once 三种调度） |
| MCP | @modelcontextprotocol/sdk（容器内 IPC MCP 服务器） |
| 校验 | zod（MCP 工具参数校验） |
| 日志 | pino + pino-pretty |
| 容器 | Docker / Apple Container（可通过 skill 切换） |

### 核心架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                      消息通道层                                    │
│  WhatsApp (baileys) │ Telegram (skill) │ Discord (skill) │ ...   │
└───────────────┬──────────────────────────────────────────────────┘
                │ Channel 接口 (onMessage / sendMessage)
                ▼
┌──────────────────────────────────────────────────────────────────┐
│                  单进程 Host Orchestrator                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │
│  │ 消息轮询  │ │ 组群队列  │ │ IPC 监听  │ │ 任务调度器        │    │
│  │ index.ts  │ │ group-   │ │ ipc.ts   │ │ task-scheduler.ts│    │
│  │ (2s poll) │ │ queue.ts │ │ (1s poll)│ │ (60s poll)       │    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────────────┘    │
│       │           │            │              │                   │
│       ▼           ▼            ▼              ▼                   │
│  ┌─────���────────────────────────────────────────────────────┐    │
│  │           SQLite (messages.db)                            │    │
│  │  messages │ chats │ sessions │ tasks │ registered_groups  │    │
│  └──────────────────────────────────────────────────────────┘    │
│       │                                                          │
│       ▼ container-runner.ts (spawn + stdin JSON + mount config)  │
└───────┼──────────────────────────────────────────────────────────┘
        │
        ▼  Docker/Apple Container (--rm, ephemeral)
┌──────────────────────────────────────────────────────────────────┐
│                   Container (Sandboxed Agent)                     │
│  ┌──────────────────────┐  ┌──────────────────────────────┐     │
│  │ agent-runner/index.ts │  │ ipc-mcp-stdio.ts (MCP Server)│     │
│  │ • Claude Agent SDK    │  │ • send_message               │     │
│  │ • query() 多轮循环     │  │ • schedule_task              │     │
│  │ • MessageStream IPC   │  │ • list/pause/resume/cancel   │     │
│  │ • PreCompact hook     │  │ • register_group             │     │
│  └──────────┬───────────┘  └──────────────────────────────┘     │
│             │ stdout: ---NANOCLAW_OUTPUT_START/END--- markers     │
│  ┌──────────┴───────────┐                                        │
│  │ /workspace/group (rw) │  ← 每组隔离的文件系统                    │
│  │ /workspace/ipc   (rw) │  ← IPC 文件（消息/任务/输入）             │
│  │ /workspace/global(ro) │  ← 全局 CLAUDE.md 共享                  │
│  └──────────────────────┘                                        │
└──────────────────────────────────────────────────────────────────┘
```

### 关键文件/目录

| 文件/目录 | 作用 |
|-----------|------|
| `src/index.ts` (498 行) | 主编排器：消息轮询 → 组群路由 → 容器调用 |
| `src/container-runner.ts` (649 行) | 容器生命周期：构建 mount → spawn docker → 流式解析输出 |
| `src/db.ts` (663 行) | SQLite 全部操作（messages/chats/sessions/tasks/groups） |
| `src/group-queue.ts` (339 行) | 每组消息队列 + 全局并发控制 + 指数退避重试 |
| `src/ipc.ts` (387 行) | IPC 文件监听：处理容器写出的消息/任务/组群注册 |
| `src/mount-security.ts` (419 行) | 挂载安全：外部 allowlist + 阻止列表 + 路径校验 |
| `src/task-scheduler.ts` (249 行) | Cron/interval/once 三种定时任务调度 |
| `src/channels/whatsapp.ts` (337 行) | WhatsApp Baileys 集成：连接/认证/收发消息/群组同步 |
| `src/router.ts` (44 行) | 消息格式化（XML 格式）+ 通道路由 |
| `src/config.ts` (69 行) | 全局配置：触发词、轮询间隔、容器参数 |
| `src/types.ts` (104 行) | 核心类型定义（Channel/RegisteredGroup/ScheduledTask） |
| `container/agent-runner/src/index.ts` (588 行) | 容器内 agent 编排：Claude SDK query() 循环 + IPC 消息流 |
| `container/agent-runner/src/ipc-mcp-stdio.ts` (285 行) | 容器内 MCP 服务器：6 个 tool（send_message 等） |
| `container/Dockerfile` (68 行) | Agent 容器镜像：Node 22 + Chromium + Claude Code |
| `skills-engine/` (2,927 行核心) | Skills 引擎：skill 安装/卸载/更新/rebase/冲突检测 |
| `groups/*/CLAUDE.md` | 每组隔离的记忆文件 |

---

## 2. Agent Loop（主循环机制）

NanoClaw 采用**双层循环**架构：Host 层消息轮询 + Container 层 SDK query 循环。

### 循环流程

**Host 层（`src/index.ts:startMessageLoop`）**:

```
while (true) {
  1. 从 SQLite 拉取注册组群的新消息（getNewMessages）
  2. 按 chat_jid 去重分组
  3. 对每个组群：
     a. 检查触发词（非 main 群需要 @Andy 触发）
     b. 拉取从上次 agent 处理后的全部累积消息
     c. 若容器已活跃 → 通过 IPC 文件管道消息（sendMessage → group-queue）
     d. 若无活跃容器 → 入队等待（enqueueMessageCheck → GroupQueue）
  4. sleep(POLL_INTERVAL=2s)
}
```

**Container 层（`container/agent-runner/src/index.ts:main`）**:

```
while (true) {
  1. 构建 prompt（用户消息 + 累积 IPC 消息）
  2. 调用 runQuery → Claude Agent SDK query()
     a. 使用 MessageStream（AsyncIterable）保持 session 活跃
     b. 并行轮询 IPC 输入目录，实时管道后续消息到 SDK
     c. 每个 result 通过 OUTPUT_START/END marker 写入 stdout
  3. query 结束后：
     a. 若收到 _close sentinel → 退出
     b. 否则等待下一个 IPC 消息 → 继续循环
}
```

### 终止条件

- **Container 层**: `_close` sentinel 文件出现在 `/workspace/ipc/input/`（由 GroupQueue 的 idle timeout 写入）
- **Host 层容器超时**: `CONTAINER_TIMEOUT`（默认 30 分钟）+ `IDLE_TIMEOUT`（默认 30 分钟，最后一个 result 后的空闲时间）
- **Host 层进程退出**: SIGTERM/SIGINT → `queue.shutdown()` → 通道断开

### 关键代码

Host 消息轮询（`src/index.ts:309-397`）：

```typescript
async function startMessageLoop(): Promise<void> {
  while (true) {
    const jids = Object.keys(registeredGroups);
    const { messages, newTimestamp } = getNewMessages(jids, lastTimestamp, ASSISTANT_NAME);
    if (messages.length > 0) {
      lastTimestamp = newTimestamp;
      saveState();
      const messagesByGroup = new Map<string, NewMessage[]>();
      for (const msg of messages) { /* 按组群分桶 */ }
      for (const [chatJid, groupMessages] of messagesByGroup) {
        // 触发词检查 → IPC 管道或入队
        if (queue.sendMessage(chatJid, formatted)) {
          /* 管道到活跃容器 */
        } else {
          queue.enqueueMessageCheck(chatJid);  // 排队启新容器
        }
      }
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL));
  }
}
```

Container SDK 查询循环（`container/agent-runner/src/index.ts:541-574`）：

```typescript
while (true) {
  const queryResult = await runQuery(prompt, sessionId, mcpServerPath, ...);
  if (queryResult.closedDuringQuery) break;  // _close 信号
  writeOutput({ status: 'success', result: null, newSessionId: sessionId });
  const nextMessage = await waitForIpcMessage();  // 阻塞等待
  if (nextMessage === null) break;  // _close 信号
  prompt = nextMessage;
}
```

---

## 3. Tool/Action 系统

NanoClaw 的 Tool 系统分两层：**Claude SDK 内置 Tool**（由 SDK 提供）和**自定义 MCP Tool**（通过 IPC MCP 服务器提供）。

### Tool 注册机制

Agent 在容器内运行时通过 `query()` 的 `allowedTools` + `mcpServers` 配置注册可用 Tool：

```typescript
allowedTools: [
  'Bash', 'Read', 'Write', 'Edit', 'Glob', 'Grep',
  'WebSearch', 'WebFetch',
  'Task', 'TaskOutput', 'TaskStop',
  'TeamCreate', 'TeamDelete', 'SendMessage',  // Agent Swarms
  'TodoWrite', 'ToolSearch', 'Skill',
  'NotebookEdit',
  'mcp__nanoclaw__*'  // 自定义 MCP 工具（通配）
],
mcpServers: {
  nanoclaw: {
    command: 'node',
    args: [mcpServerPath],
    env: { NANOCLAW_CHAT_JID, NANOCLAW_GROUP_FOLDER, NANOCLAW_IS_MAIN },
  },
},
```

自定义 MCP 工具通过 `@modelcontextprotocol/sdk` 注册（`ipc-mcp-stdio.ts`），使用 `zod` 做参数校验，通过文件 IPC 与 host 通信。

### Tool 列表

| Tool | 来源 | 功能 | 实现方式 |
|------|------|------|----------|
| Bash | Claude SDK | 执行 shell 命令 | 容器内沙箱执行（PreToolUse hook 剥离 API 密钥） |
| Read/Write/Edit/Glob/Grep | Claude SDK | 文件操作 | 限于容器 mount 的路径 |
| WebSearch/WebFetch | Claude SDK | 网页访问 | 容器内网络不受限 |
| Task/TaskOutput/TaskStop | Claude SDK | 子 agent 管理 | SDK 内置 |
| TeamCreate/TeamDelete/SendMessage | Claude SDK | Agent Swarms | 多 agent 协作（实验性） |
| `mcp__nanoclaw__send_message` | MCP | 向用户/群组发送即时消息 | IPC 文件 → host → WhatsApp |
| `mcp__nanoclaw__schedule_task` | MCP | 创建定时/定期任务 | IPC 文件 → host → SQLite |
| `mcp__nanoclaw__list_tasks` | MCP | 列出计划任务 | 读取 IPC 目录下的快照文件 |
| `mcp__nanoclaw__pause_task` | MCP | 暂停定时任务 | IPC 文件 → host |
| `mcp__nanoclaw__resume_task` | MCP | 恢复定时任务 | IPC 文件 → host |
| `mcp__nanoclaw__cancel_task` | MCP | 取消并删除任务 | IPC 文件 → host |
| `mcp__nanoclaw__register_group` | MCP | 注册新群组（仅 main） | IPC 文件 → host → SQLite |

### Tool 调用流程

```
Claude Agent (容器内)
  │ 选择 tool（如 send_message）
  ▼
Claude SDK query() 调用 MCP 工具
  │
  ▼
ipc-mcp-stdio.ts (StdioServerTransport)
  │ 校验参数 (zod) + 权限检查 (isMain)
  │ 写入 IPC JSON 文件到 /workspace/ipc/messages/ 或 /workspace/ipc/tasks/
  ▼
Host: ipc.ts (IPC Watcher, 1s poll)
  │ 读取 JSON 文件 → 验证来源组群权限
  │ 执行操作（发消息/创建任务/注册群组）
  ▼
WhatsApp / SQLite / 群组注册
```

---

## 4. Prompt 工程

### System Prompt 结构

NanoClaw **完全委托 Claude Agent SDK** 处理 system prompt，不做自定义 prompt 组装：

```typescript
systemPrompt: globalClaudeMd
  ? { type: 'preset', preset: 'claude_code', append: globalClaudeMd }
  : undefined,
```

- **基础 prompt**: `claude_code` 预设（Claude Code 的标准 system prompt）
- **追加内容**: 全局 `CLAUDE.md`（`/workspace/global/CLAUDE.md`，非 main 组群只读）
- **组群记忆**: 每个组群的 `groups/{name}/CLAUDE.md` 由 SDK 自动加载

### 动态 Prompt 组装

1. **用户消息格式化**（`router.ts:formatMessages`）— 将多条消息封装为 XML 格式：

```xml
<messages>
<message sender="Alice" time="2026-02-25T10:00:00Z">@Andy 帮我查天气</message>
<message sender="Bob" time="2026-02-25T10:01:00Z">我也想知道</message>
</messages>
```

2. **定时任务前缀**（`agent-runner/index.ts`）— 自动任务带标记：

```
[SCHEDULED TASK - The following message was sent automatically and is not coming directly from the user or group.]
```

3. **额外目录**（`/workspace/extra/*`）— 通过 `additionalDirectories` 让 SDK 自动加载外挂目录的 CLAUDE.md

### Prompt 模板位置

NanoClaw 没有独立的 prompt 模板文件。提示词来源：
- Claude Agent SDK 内置的 `claude_code` 预设
- `groups/global/CLAUDE.md` — 全局共享记忆
- `groups/{name}/CLAUDE.md` — 每组隔离记忆
- `container/skills/` — 容器内可用的 skills（如 agent-browser）

---

## 5. 上下文管理

### 上下文窗口策略

NanoClaw **完全依赖 Claude Agent SDK 的内置上下文管理**，自身不做 token 计数或截断：

- **SDK compaction**: 当 context 接近窗口限制时，SDK 自动触发 compaction
- **PreCompact hook**: NanoClaw 注册了 `createPreCompactHook`，在 compaction 前将完整对话归档到 `conversations/` 目录（Markdown 格式，截断到 2000 字符/条）
- **Session resume**: 通过 `sessionId` + `resumeAt`（lastAssistantUuid）实现跨查询的 session 续接

### 文件/代码的 context 策略

- 容器挂载决定可见范围：每组只能看到自己的 `/workspace/group`
- main 组群额外获得 `/workspace/project`（只读）
- 全局记忆通过 `/workspace/global/CLAUDE.md` 共享
- 额外挂载通过 `mount-allowlist.json` 控制（外部存储，容器不可修改）

### 对话历史管理

- **SQLite 存储**: 所有注册组群的消息永久存储在 `messages` 表
- **游标机制**: `lastTimestamp`（全局已读水位）+ `lastAgentTimestamp[chatJid]`（每组 agent 处理水位）
- **累积上下文**: 非触发消息在 DB 中累积，触发时一次性拉取（`getMessagesSince`）
- **Session 持久化**: `data/sessions/{group}/.claude/` 存放 Claude SDK 的 session 文件，跨容器保留

---

## 6. 错误处理与恢复

### LLM 输出解析错误

NanoClaw 使用 **哨兵标记（sentinel marker）** 机制解析容器输出，避免 JSON 被 SDK 日志干扰：

```typescript
const OUTPUT_START_MARKER = '---NANOCLAW_OUTPUT_START---';
const OUTPUT_END_MARKER = '---NANOCLAW_OUTPUT_END---';
```

- 流式解析：`container-runner.ts` 在 stdout chunk 中搜索标记对，提取 JSON
- 回退：若无标记，尝试解析最后一行（向后兼容）
- 解析失败返回 `status: 'error'`，host 记录日志并回滚游标

### Tool 执行失败

- **容器进程错误**: `container.on('close', code !== 0)` → 记录日志 + 回滚消息游标
- **容器启动失败**: `container.on('error')` → 返回 `spawn error`
- **IPC 文件处理错误**: 移入 `ipc/errors/` 目录保存现场
- **消息发送失败**: WhatsApp 通道自动入队（`outgoingQueue`），重连后刷新

### 重试机制

```
GroupQueue 指数退避重试:
  BASE_RETRY_MS = 5000
  MAX_RETRIES = 5
  delay = 5000 * 2^(retryCount - 1)
  即: 5s → 10s → 20s → 40s → 80s
  超过 5 次 → 放弃本轮，等待下一条消息触发
```

**消息游标回滚**: agent 执行失败且尚未发送输出给用户时，`lastAgentTimestamp[chatJid]` 回滚到处理前的值，确保消息不丢失。但如果已发送了部分输出，则不回滚（防止重复发送）。

**启动恢复**: `recoverPendingMessages()` 在进程启动时扫描所有注册组群的未处理消息，自动入队。

---

## 7. 关键创新点

### 独特设计

1. **"代码即配置"哲学**: 拒绝配置文件，鼓励用户直接修改源码。代码足够小（~3,900 行），Claude Code 可以安全地修改。这是与所有其他 agent 的根本差异。

2. **Skills 即代码变换**: 不是运行时插件，而是 Claude Code Skills（`.claude/skills/`），执行后直接修改源码。例如 `/add-telegram` 不是加载 Telegram 适配器，而是让 Claude 重写代码添加 Telegram 支持。

3. **容器级安全而非应用级权限**: 安全边界是 Docker 容器挂载，而非代码中的 permission check。攻击面由挂载决定。

4. **双层 IPC 架构**: 容器通过文件系统 IPC 与 host 通信（JSON 文件 + atomic rename），而非 socket/pipe，确保容器重启不影响 host。

5. **MessageStream + IPC 管道**: 活跃容器通过 `MessageStream`（push-based AsyncIterable）接收后续消息，避免为每条消息重启容器。

6. **外部安全配置**: `~/.config/nanoclaw/mount-allowlist.json` 存放在项目目录外，容器内的 agent 无法修改安全策略。

### 值得借鉴的模式

| 模式 | 描述 | 适用场景 |
|------|------|----------|
| Sentinel Marker 流式解析 | stdout 中用唯一标记包裹 JSON，与日志混合无碍 | 子进程输出解析 |
| 游标 + 回滚 | 消息游标提前推进，失败时回滚（除非已发送输出） | 消息队列的 at-least-once 语义 |
| 每组隔离 session | `data/sessions/{group}/.claude/` 独立 Claude session | 多租户 agent |
| 外部 allowlist | 安全配置存在容器挂载范围之外 | 沙箱安全 |
| Atomic IPC | 先写 `.tmp` 再 `rename`，避免读到半写文件 | 文件系统 IPC |
| Skills Engine | 完整的 skill 安装/卸载/rebase/冲突检测系统 | 代码级扩展 |

---

## 7.5 MVP 组件清单

基于以上分析，构建最小可运行版本需要以下组件：

| 组件 | 对应维度 | 核心文件 | 建议语言 | 语言理由 |
|------|----------|----------|----------|----------|
| 消息轮询与编排 | D2 | `src/index.ts` | Python | 主循环为 poll + dispatch，无需 TS 异步特性 |
| 容器启动与 IPC | D2/D3 | `src/container-runner.ts` | Python | subprocess + JSON 文件 IPC，Python subprocess 足够 |
| MCP 工具服务器 | D3 | `container/agent-runner/src/ipc-mcp-stdio.ts` | TypeScript | MCP SDK 为 TS，且运行在容器内需与 Claude Code 集成 |
| Agent 运行器 | D2/D4 | `container/agent-runner/src/index.ts` | TypeScript | 依赖 @anthropic-ai/claude-agent-sdk，必须 TS |
| 组群队列 | D2/D6 | `src/group-queue.ts` | Python | 并发控制 + 重试逻辑，Python asyncio 足够 |
| 通道路由 | D9 | `src/channels/whatsapp.ts`, `src/router.ts` | Python | 模拟 WhatsApp 消息收发，Python 可用模拟 |
| 持久化层 | D10 | `src/db.ts` | Python | SQLite 操作，Python sqlite3 原生支持 |
| 挂载安全 | D11 | `src/mount-security.ts` | Python | 路径校验 + allowlist 解析 |

---

## 8. 跨 Agent 对比

### vs 其他 agent

| 维度 | nanoclaw | aider | openclaw | codex-cli | pi-agent |
|------|----------|-------|----------|-----------|----------|
| **架构** | 单进程 + 容器隔离 | 三层嵌套 Coder 继承体系 | Gateway + monorepo + 内嵌 pi | Rust 二进制 + TUI | TypeScript monorepo 7 packages |
| **代码规模** | ~3,900 行（含测试 ~26k） | ~30,000 行 Python | ~450,000 行 | ~30,000 行 Rust | ~25,000 行 TS |
| **Agent 引擎** | Claude Agent SDK（黑盒） | 自研 Python 循环 + RepoMap | pi-coding-agent（内嵌） | 自研 Rust 循环 | 自研 Agent Session |
| **Tool 系统** | SDK 内置 + MCP 自定义 | 双轨制（命令 + LLM 文本格式） | pi ops 注册 + gateway ops | Rust trait + patch/shell | Pluggable Ops 注册表 |
| **安全模型** | OS 容器隔离 + 外部 allowlist | Git 集成（auto-commit + undo） | Docker + 应用级 agent fence | 平台沙箱（Seatbelt/Landlock） | 无沙��（信任用户） |
| **通道** | WhatsApp + skill 扩展 | 仅 CLI | 13+ 内置通道 + 31 扩展 | CLI 终端 | CLI + Slack |
| **扩展方式** | Claude Code Skills（代码变换） | 无正式扩展系统 | Skills + Extensions（运行时插件） | Hooks + MCP | Extension Hooks |
| **上下文管理** | 全委托 SDK | tree-sitter AST + PageRank RepoMap | Steering Queue + Compaction | Head-Tail 截断 | Structured Compaction |
| **定时调度** | Cron/Interval/Once | 无 | Cron 调度器 | 无 | 无 |
| **记忆** | CLAUDE.md 文件 + SQLite session | Git 集成 | SQLite + 向量嵌入 + BM25 | 无持久记忆 | 无持久记忆 |

### 总结

NanoClaw 代表了与 OpenClaw 截然相反的设计哲学：**极简而非全能**。它放弃了自研 agent 循环、prompt 工程、上下文管理等"标配"能力，全部委托给 Claude Agent SDK，自身只专注于**容器编排、IPC 通信、安全隔离和多群组管理**这几个 SDK 不提供的能力。这使得它的核心代码仅 ~3,900 行，是所有已分析 agent 中最精简的。与 Aider 相比，Aider 自研了完整的 RepoMap、12+ 编辑格式和反思循环等深度编码能力，NanoClaw 则将编码能力全部委托给 SDK，专注平台层编排。与 Codex CLI 的内核级沙箱（Seatbelt/Landlock）不同，NanoClaw 用容器级沙箱 + 外部 allowlist 实现安全隔离。其"代码即配置 + Skills 代码变换"的扩展模型也是独一无二的——不通过配置或插件系统扩展，而是让 AI 直接重写源码。适合追求完全理解和掌控自己 AI 助手的高级用户。

---

## 9. 通道层与网关 _(平台维度)_

### 通道架构

NanoClaw 使用**Channel 接口**抽象通道，host 进程维护一个 `channels: Channel[]` 数组。消息到达时通过 `findChannel(channels, jid)` 找到归属通道，按 JID 后缀匹配（如 `@g.us` → WhatsApp）。

```typescript
export interface Channel {
  name: string;
  connect(): Promise<void>;
  sendMessage(jid: string, text: string): Promise<void>;
  isConnected(): boolean;
  ownsJid(jid: string): boolean;
  disconnect(): Promise<void>;
  setTyping?(jid: string, isTyping: boolean): Promise<void>;
}
```

没有 Gateway 层——单进程直连。新通道通过 Skills 注入代码实现（如 `/add-telegram` 添加 `src/channels/telegram.ts`）。

### 支持的通道

| 通道 | 协议/集成方式 | 特点 |
|------|--------------|------|
| WhatsApp | @whiskeysockets/baileys (WebSocket 反向协议) | 内置，默认通道，LID 到手机号翻译 |
| Telegram | telegraf (Bot API) | Skill 安装 (`/add-telegram`)，支持 Swarm 子 agent 独立 bot 身份 |
| Discord | discord.js | Skill 安装 (`/add-discord`) |
| Slack | 待实现 | RFS (Request for Skills) |
| Signal | 待实现 | README 提及 |
| Headless | 无 UI | 仅定时任务运行，无消息通道 |

### 消息标准化

所有通道消息统一为 `NewMessage` 接口后存入 SQLite，通过 `router.ts:formatMessages` 转为 XML 格式发给 agent：

```typescript
interface NewMessage {
  id: string;
  chat_jid: string;       // 统一 JID 格式
  sender: string;
  sender_name: string;
  content: string;
  timestamp: string;       // ISO 8601
  is_from_me?: boolean;
  is_bot_message?: boolean;
}
```

通道标识存储在 `chats.channel` 字段（whatsapp/discord/telegram），通过 JID 前缀区分（`dc:` → Discord, `tg:` → Telegram）。

### 多模态支持

- **文本**: 完整支持
- **图片/视频**: 仅提取 caption 文本，不处理媒体本身
- **语音**: 通过 `/add-voice-transcription` skill 添加 Whisper 转写
- **浏览器**: 容器内预装 Chromium + agent-browser，agent 可通过 Bash 执行浏览器自动化

---

## 10. 记忆与持久化 _(平台维度)_

### 持久化架构

```
store/
  messages.db          ← SQLite: 消息、聊天、会话、任务、群组注册、路由状态
  auth/                ← WhatsApp Baileys 认证状态
data/
  sessions/{group}/
    .claude/           ← Claude SDK session 文件（每组隔离）
      settings.json    ← 启用 Agent Swarms + Auto Memory
      skills/          ← 容器内可用 skills（从 container/skills/ 同步）
  ipc/{group}/
    messages/          ← 待处理的 IPC 消息文件
    tasks/             ← 待处理的 IPC 任务文件
    input/             ← 后续消息管道 + _close sentinel
    current_tasks.json ← 当前任务快照（容器只读）
    available_groups.json ← 可用群组快照（仅 main 可见）
groups/
  global/CLAUDE.md     ← 全局共享记忆
  main/CLAUDE.md       ← 主群组记忆
  {name}/CLAUDE.md     ← 各群组隔离记忆
  {name}/conversations/← 对话归档（PreCompact hook 生成）
  {name}/logs/         ← 容器运行日志
```

### 长期记忆

NanoClaw 采用**文件级记忆**而非向量数据库：

1. **CLAUDE.md 文件**: Claude SDK 自动加载工作目录和 additional directories 下的 `CLAUDE.md`，这是主要的跨 session 知识载体
2. **Claude Auto Memory**: 容器 settings 启用 `CLAUDE_CODE_DISABLE_AUTO_MEMORY: '0'`，SDK 自动在 `~/.claude/` 下维护用户偏好记忆
3. **对话归档**: PreCompact hook 在 context compaction 前将完整对话保存为 Markdown 文件到 `conversations/`，供后续 agent 读取
4. **SQLite 消息历史**: 所有注册群组的消息永久存储，但 agent 不直接查询 DB

### 状态恢复

- **Session 续接**: `sessionId` 持久化在 SQLite `sessions` 表，容器重启后传入 SDK 的 `resume` 参数
- **消息游标恢复**: `lastTimestamp` 和 `lastAgentTimestamp` 存在 SQLite `router_state` 表
- **崩溃恢复**: `recoverPendingMessages()` 在启动时扫描所有组群的未处理消息并入队
- **JSON 迁移**: 自动从旧版 JSON 文件迁移到 SQLite（`migrateJsonState`）

---

## 11. 安全模型与自治 _(平台维度)_

### 信任分级

| 实体 | 信任级别 | 权限 |
|------|----------|------|
| Main 群组 (self-chat) | 可信 | 项目只读 + 管理所有群组 + 跨群操作 |
| 非 Main 群组 | 不可信 | 仅自身目录读写 + 全局记忆只读 |
| 容器 Agent | 沙箱化 | 仅挂载目录可见，网络不受限 |
| WhatsApp 消息 | 用户输入 | 需触发词 + 潜在 prompt injection |

### 沙箱策略

**容器隔离（主安全边界）**:
- Docker `--rm` 容器，每次调用创建新容器
- 非 root 用户运行（`node` uid 1000）
- 文件系统仅显式 mount 可见
- Bash 命令在容器内执行（SDK 的 `permissionMode: 'bypassPermissions'`）
- PreToolUse hook 自动剥离 API 密钥：`unset ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN 2>/dev/null; ${command}`

**挂载安全**:
- 外部 allowlist (`~/.config/nanoclaw/mount-allowlist.json`) — 存在项目目录外，容器无法修改
- 默认阻止列表：`.ssh`, `.gnupg`, `.aws`, `.docker`, `credentials`, `.env`, `id_rsa` 等 16 个模式
- Symlink 解析后校验（防穿越攻击）
- `nonMainReadOnly`: 非 main 群组强制只读
- Main 群组的项目根目录也是只读挂载

**IPC 权限控制**:
- 每组独立 IPC 命名空间（`data/ipc/{group}/`）
- 非 main 组群只能操作自身的消息和任务
- 跨组操作被 host 层拦截并记录告警

### 自主调度

```typescript
// task-scheduler.ts — 三种调度类型
schedule_type: 'cron' | 'interval' | 'once'
// cron: 标准 cron 表达式，支持时区
// interval: 毫秒间隔
// once: 一次性定时

// context_mode: 'group' | 'isolated'
// group: 使用群组的 session 续接，有对话历史
// isolated: 每次全新 session，适合独立任务
```

调度循环（60s 轮询）→ 查询 `getDueTasks()` → 通过 `GroupQueue.enqueueTask()` 入队 → 容器执行 → 结果通过 `send_message` MCP 工具发回用户。

### 多 Agent 协作

NanoClaw 是首个支持 **Agent Swarms**（Claude Code Agent Teams）的个人 AI 助手：

- 容器 settings 启用 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: '1'`
- `allowedTools` 包含 `TeamCreate`, `TeamDelete`, `SendMessage`
- Telegram 通道支持 Swarm 子 agent 独立 bot 身份（`/add-telegram-swarm`）
- 每个子 agent 可继承 MCP 服务器（nanoclaw tools）

---

## 12. 其他特色机制 _(平台维度)_

### 机制列表

| 机制 | 简述 | 关键代码 |
|------|------|----------|
| Skills Engine | 完整的 skill 安装/卸载/更新/rebase 系统 | `skills-engine/` (2,927 行) |
| AI-Native 设置 | 无安装向导，Claude Code 引导一切 | `.claude/skills/setup/` |
| 对话归档 | PreCompact hook 保存完整对话为 Markdown | `agent-runner/index.ts:createPreCompactHook` |
| 组群发现 | WhatsApp 群组元数据同步 + 可用群组快照 | `whatsapp.ts:syncGroupMetadata`, `container-runner.ts:writeGroupsSnapshot` |
| 服务化部署 | launchd (macOS) / systemd (Linux) 守护进程 | `setup/service.ts`, `launchd/` |

### 详细分析

**Skills Engine（代码变换引擎）**

这是 NanoClaw 最独特的机制。与传统的运行时插件不同，Skills 是 Claude Code 的 skill 文件（`SKILL.md` + `manifest.yaml` + 代码文件），执行后**直接修改项目源码**：

```yaml
# manifest.yaml 示例
skill: add-telegram
version: "1.0.0"
core_version: ">=1.0.0"
adds: ["src/channels/telegram.ts"]
modifies: ["src/index.ts", "src/types.ts", "package.json"]
conflicts: []
depends: []
```

Skills Engine 提供：
- `applySkill()`: 应用 skill（合并新文件 + 补丁修改文件）
- `uninstallSkill()`: 卸载 skill（撤回代码变更）
- `rebase()`: 当 NanoClaw 更新后，自动 rebase 已安装 skills
- `replaySkills()`: 重新应用所有 skills（基于 manifest 记录）
- `state.ts`: 追踪已安装 skills + 自定义修改 + 文件哈希
- 冲突检测：skill 间的 `conflicts` 和 `depends` 声明

**AI-Native 设置**

NanoClaw 的设置流程完全由 Claude Code 驱动：
1. `git clone` → `cd NanoClaw` → `claude` → `/setup`
2. `/setup` 是一个 Claude Code Skill，引导 Claude 完成：依赖安装、WhatsApp 认证、容器构建、服务注册
3. 调试也通过 `/debug` skill，而非传统的日志/监控工具

**对话归档（PreCompact Hook）**

在 Claude SDK 执行 context compaction 前，hook 自动：
1. 读取完整 transcript（JSONL 格式）
2. 解析 user/assistant 消息
3. 从 sessions-index.json 获取 session 摘要作为文件名
4. 写入 `conversations/{date}-{summary}.md`

这使得 agent 在后续 session 中可以通过文件系统访问历史对话上下文。
