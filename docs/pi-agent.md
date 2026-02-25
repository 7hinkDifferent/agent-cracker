# pi-agent — Deep Dive Analysis

> Auto-generated from template on 2026-02-23
> Repo: https://github.com/badlogic/pi-mono
> Analyzed at commit: [`316c2af`](https://github.com/badlogic/pi-mono/tree/316c2afe38d34a352474b852b95195be266709cb) (2026-02-23)

## 1. Overview & Architecture

### 项目定位

Pi 是一个**模块化的 AI Agent 工具包**，核心是一个终端交互式 Coding Agent（`pi` 命令），同时提供统一 LLM API、Agent 运行时、TUI 库、Web UI 组件和 Slack Bot 等配套设施。项目采用 TypeScript monorepo 架构，7 个 package 各司其职，通过分层设计实现高度可扩展性。

### 技术栈

- **语言**: TypeScript 5.7+
- **运行时**: Node.js 20+（支持编译为 Bun 二进制）
- **包管理**: npm workspaces（lockstep 版本）
- **构建**: tsgo（自定义 TypeScript 编译器）
- **格式/检查**: Biome
- **测试**: Vitest

| 类别 | 关键依赖 |
|------|----------|
| LLM 集成 | openai, @anthropic-ai/sdk, @google/genai, @aws-sdk/client-bedrock-runtime, @mistralai/mistralai |
| Schema 校验 | @sinclair/typebox, ajv |
| 终端 UI | chalk, cli-highlight, marked, koffi (FFI) |
| 文件处理 | glob, ignore, diff, file-type |
| Web UI | lit, tailwindcss, pdfjs-dist, xlsx |
| Slack | @slack/socket-mode, @slack/web-api |

### 核心架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户入口层                                │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│   │ pi CLI       │  │ mom          │  │ web-ui       │          │
│   │ (coding-     │  │ (Slack Bot)  │  │ (Web 组件)   │          │
│   │  agent)      │  │              │  │              │          │
│   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└──────────┼─────────────────┼─────────────────┼──────────────────┘
           │                 │                 │
           ▼                 ▼                 ▼
┌──────────────────────────────────────────────────────────────────┐
│              AgentSession (coding-agent/core)                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Session 管理 │ 扩展系统 │ Prompt 模板 │ Compaction │ 导出  │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Agent (agent-core)                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Agent Loop │ 消息队列 │ Tool 执行 │ 事件流 │ 状态管理     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    pi-ai (统一 LLM API)                          │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐ ┌──────────┐  │
│  │ OpenAI  │ │Anthropic │ │ Gemini │ │ Bedrock │ │ Mistral  │  │
│  └─────────┘ └──────────┘ └────────┘ └─────────┘ └──────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 关键文件/目录

| 文件/目录 | 作用 |
|-----------|------|
| `packages/ai/src/` | 统一 LLM API：多 provider 流式调用、模型发现、tool calling 转换 |
| `packages/agent/src/agent-loop.ts` | Agent 核心循环：双层循环（steering + follow-up） |
| `packages/agent/src/agent.ts` | Agent 状态管理：消息队列、事件订阅、abort 控制 |
| `packages/coding-agent/src/main.ts` | CLI 入口：参数解析、模型选择、模式分发 |
| `packages/coding-agent/src/core/agent-session.ts` | 高层 Session 封装：prompt 处理、扩展集成、auto-compact |
| `packages/coding-agent/src/core/sdk.ts` | SDK 工厂：`createAgentSession()` 一站式初始化 |
| `packages/coding-agent/src/core/tools/` | 内置工具：read、write、edit、bash、grep、find、ls |
| `packages/coding-agent/src/core/system-prompt.ts` | System Prompt 动态构建 |
| `packages/coding-agent/src/core/compaction/` | 上下文压缩：LLM 摘要 + 结构化格式 |
| `packages/coding-agent/src/core/extensions/` | 扩展系统：加载、运行、生命周期钩子 |
| `packages/coding-agent/src/core/session-manager.ts` | Session 持久化：JSONL 格式、分支管理 |
| `packages/tui/src/` | 终端 UI 库：差分渲染、富文本、编辑器 |
| `packages/mom/src/` | Slack Bot：消息委派、沙箱执行、定时任务 |

---

## 2. Agent Loop（主循环机制）

### 循环流程

Pi 采用**双层循环 + 消息队列**架构，支持用户在 Agent 执行过程中实时干预：

```
外层循环：处理 follow-up 消息（等 Agent 空闲后执行）
 └─ 内层循环：处理 steering 消息（立即中断当前 tool 执行）
    ├─ 1. transformContext() — 扩展可修改消息上下文
    ├─ 2. convertToLlm() — AgentMessage[] → LLM Message[]
    ├─ 3. streamAssistantResponse() — 流式调用 LLM
    ├─ 4. 检查 tool calls
    │   └─ executeToolCalls() — 并行执行所有 tool
    │       ├─ 校验参数（TypeBox schema）
    │       ├─ 调用 tool.execute()
    │       ├─ 发射 tool_execution_start/update/end 事件
    │       └─ 生成 ToolResultMessage
    ├─ 5. 检查 steering 消息（用户中途输入）
    │   └─ 有 steering → 跳过剩余 tool，注入用户消息
    └─ 6. 有 tool call → 继续内层循环；无 → 退出
```

**消息队列双模式**：
- **Steering（方向盘）**：中断当前执行，立即影响 Agent 行为。适合"停下来"或"改方向"
- **Follow-up（排队）**：等 Agent 完成当前任务后再处理。适合追加需求

两种队列都支持 `"all"`（批量发送）和 `"one-at-a-time"`（逐条处理）模式。

### 终止条件

1. **LLM 未返回 tool call**：Agent 认为任务完成，退出内层循环
2. **AbortSignal 触发**：用户按 Ctrl+C 或代码调用 `agent.abort()`
3. **无更多 follow-up 消息**：外层循环结束
4. **不可恢复错误**：API key 缺失、模型不可用等

### 关键代码

```typescript
// packages/agent/src/agent-loop.ts — 核心循环
async function* runLoop(context, config, signal, streamFn) {
  while (true) {
    // 1. 上下文转换（扩展可修改）
    const transformedMessages = config.transformContext
      ? await config.transformContext(context.messages)
      : context.messages;

    // 2. 消息格式转换
    const llmMessages = config.convertToLlm(transformedMessages);

    // 3. 流式 LLM 调用
    const response = await streamAssistantResponse(llmMessages, config, signal, streamFn);
    context.messages.push(response.message);
    yield { type: "message_end", message: response.message };

    // 4. 无 tool call → 退出
    if (!response.message.toolCalls?.length) break;

    // 5. 并行执行 tool calls
    const toolResults = await executeToolCalls(
      response.message.toolCalls,
      config.tools,
      signal,
      (event) => { /* emit tool events */ },
    );

    // 6. 检查 steering 消息
    const steeringMessages = config.dequeueSteeringMessages?.() ?? [];
    if (steeringMessages.length > 0) {
      context.messages.push(...steeringMessages);
      // 跳过剩余 tool results
    }

    context.messages.push(...toolResults);
    // 继续循环 → LLM 看到 tool 结果后决定下一步
  }
}
```

---

## 3. Tool/Action 系统

### Tool 注册机制

Pi 使用 **TypeBox Schema** 定义 tool 参数，通过 `AgentTool` 接口统一注册：

```typescript
// 每个 tool 实现 AgentTool 接口
interface AgentTool<TParameters extends TSchema> {
  name: string;
  label: string;                // UI 显示名
  description: string;          // LLM 看到的描述
  parameters: TParameters;      // TypeBox schema → JSON Schema
  execute: (
    toolCallId: string,
    params: Static<TParameters>,
    signal?: AbortSignal,
    onUpdate?: AgentToolUpdateCallback,  // 流式进度回调
  ) => Promise<AgentToolResult>;
}

// Tool 结果分为两部分
interface AgentToolResult<T> {
  content: (TextContent | ImageContent)[];  // LLM 看到的内容
  details: T;                                // UI 上下文（如截断信息）
}
```

**插拔式操作层（Pluggable Operations）**：每个 tool 的底层操作可替换，实现 SSH/Docker 等远程执行：

```typescript
// 以 read tool 为例
interface ReadOperations {
  readFile: (path: string) => Promise<Buffer>;
  access: (path: string) => Promise<void>;
  detectImageMimeType?: (path: string) => Promise<string | null>;
}

// 默认使用本地 fs，也可注入远程实现
const tool = createReadTool(cwd, { operations: sshOperations });
```

### Tool 列表

| Tool | 功能 | 关键特性 |
|------|------|----------|
| `read` | 读取文件/图片 | 支持 offset/limit 分块读取，图片自动缩放至 2000x2000，文本截断至 10000 行或 512KB |
| `bash` | 执行 shell 命令 | spawn 子进程，超时控制，输出截断至 50000 行或 512KB，支持进程树 kill |
| `edit` | 精确文本替换 | 模糊匹配（空白容忍 + Unicode 标准化），保留行尾符（LF/CRLF），返回 unified diff |
| `write` | 创建/覆写文件 | 自动创建父目录 |
| `grep` | 正则搜索 | 底层使用 ripgrep，支持 .gitignore，上下文行数，行截断 200 字符 |
| `find` | glob 文件查找 | globSync 实现，尊重 .gitignore，默认 1000 结果上限 |
| `ls` | 列出目录 | 支持详细模式（权限/大小/日期） |

扩展可通过 Extension API 注册自定义 tool。

### Tool 调用流程

```
LLM 返回 tool_calls: [{id, name, args}]
    │
    ▼
executeToolCalls()
    │
    ├─ 对每个 tool call（并行执行）：
    │   ├─ 从注册表查找 tool（by name）
    │   ├─ TypeBox 校验参数
    │   ├─ 发射 tool_execution_start 事件
    │   ├─ 调用 tool.execute(id, params, signal, onUpdate)
    │   │   └─ onUpdate 回调 → 发射 tool_execution_update（bash 实时输出等）
    │   ├─ 发射 tool_execution_end 事件
    │   └─ 返回 ToolResultMessage { toolCallId, content }
    │
    ├─ 检查 steering 消息队列
    │   └─ 有 → 中断剩余 tool，注入 steering 消息
    │
    └─ 返回 ToolResultMessage[] → 加入消息上下文 → 继续循环
```

---

## 4. Prompt 工程

### System Prompt 结构

`buildSystemPrompt()` 动态构建 system prompt，由以下部分组成：

1. **角色定义**：`You are an expert coding assistant operating inside pi, a coding agent harness.`
2. **可用工具说明**：根据当前激活的 tool 列表动态生成
3. **使用指南**（自适应）：根据 tool 组合调整建议
4. **Pi 文档链接**：`~/.pi/docs/` 目录下的文档（仅当用户询问 pi 本身时使用）
5. **项目上下文**：从 `.pi/context/` 目录或 `--context` 参数加载
6. **Skills 定义**：从 `~/.pi/skills/` 或 `--skill` 参数加载
7. **时间和工作目录**：`Current date and time: <ISO string>` + `Current working directory: <cwd>`

### 动态 Prompt 组装

**自适应指南**——根据 tool 可用性调整建议：

```typescript
// 有 bash 但没 grep/find → 建议用 bash 搜索
if (hasBash && !hasGrep && !hasFind) {
  guidelinesList.push("Use bash for file operations like ls, rg, find");
}

// 有 bash 和 grep/find → 建议优先用专用工具
if (hasBash && (hasGrep || hasFind)) {
  guidelinesList.push("Prefer grep/find/ls tools over bash for file exploration");
}

// 有 read 和 edit → 建议先读再改
if (hasRead && hasEdit) {
  guidelinesList.push("Use read to examine files before editing");
}
```

**多层上下文注入**：

```
System Prompt（静态基础）
    ├─ + 项目上下文文件（.pi/context/*.md）
    ├─ + Skills 定义
    ├─ + 扩展修改（每轮 beforeAgentStart hook 可改写）
    └─ + 扩展注入的 custom messages（混入用户消息流）
```

### Prompt 模板位置

| 文件 | 用途 |
|------|------|
| `packages/coding-agent/src/core/system-prompt.ts` | System prompt 构建器 |
| `packages/coding-agent/src/core/compaction/compaction.ts` | Compaction 摘要 prompt（结构化格式） |
| `.pi/context/*.md` | 项目级上下文文件（用户自定义） |
| `~/.pi/skills/` | 全局 skill 定义 |

---

## 5. 上下文管理

### 上下文窗口策略

Pi 采用**阈值触发 + LLM 摘要**的 compaction 策略：

- **Token 估算**：`chars / 4` 启发式（保守高估，不依赖 provider 特定 tokenizer）
- **图片固定计算**：每张图片计为 1200 tokens（4800 chars）
- **触发条件**：`contextTokens > contextWindow - reserveTokens`（默认 reserve = 16384）
- **保留策略**：保留最近 `keepRecentTokens`（默认 20000）的消息不压缩

### 文件/代码的 context 策略

Pi **没有** Aider 那样的 RepoMap/AST 分析。它的策略更简单直接：

1. **Tool 驱动**：Agent 通过 `grep`、`find`、`ls`、`read` 工具主动探索文件
2. **项目上下文文件**：用户在 `.pi/context/` 目录放置说明文件，注入 system prompt
3. **截断保护**：每个 tool 返回结果都有大小限制
   - read：10000 行 / 512KB
   - bash：50000 行 / 512KB
   - grep：行截断 200 字符

### 对话历史管理

**Compaction 算法**（三步）：

1. **找切割点**：从最新消息向前累积 token，直到达到 `keepRecentTokens`，在 user/assistant 消息边界切割（不在 tool result 处切）

2. **LLM 摘要**：将被切掉的旧消息发给 LLM，要求生成**结构化摘要**：

```markdown
## Goal
[用户要完成什么？]

## Constraints & Preferences
- [用户的约束和偏好]

## Progress
### Done
- [x] [已完成的任务]
### In Progress
- [ ] [进行中的任务]
### Blocked
- [阻塞项]

## Key Decisions
- **[决策]**: [理由]

## Next Steps
1. [下一步]

## Critical Context
- [需要保留的关键数据]
```

3. **Split Turn 处理**：如果切割点落在一个 turn 中间（assistant 响应中途），额外生成一个 **turn prefix summary** 解释前半部分的上下文

**增量更新**：后续 compaction 不从头生成，而是将之前的 summary 作为上下文，让 LLM 执行 UPDATE 操作合并增量进度。

**两种触发方式**：
- **阈值触发**：auto-compact 定期检查，超限自动压缩
- **溢出触发**：LLM 返回 context overflow 错误时立即压缩并重试

---

## 6. 错误处理与恢复

### LLM 输出解析错误

Pi 使用 LLM 原生 tool calling（不是自定义文本格式），因此不存在 Aider 那样的 SEARCH/REPLACE 解析问题。Tool call 参数由 **TypeBox/AJV** 校验：

```typescript
// agent-loop.ts — tool 参数校验
const validationResult = validate(tool.parameters, params);
if (!validationResult.valid) {
  // 返回错误信息给 LLM，让它修正
  return {
    content: [{ type: "text", text: `Invalid parameters: ${validationResult.errors}` }],
    details: { error: true },
  };
}
```

### Tool 执行失败

**Edit Tool 模糊匹配**：

```typescript
// 两阶段匹配
// 1. 精确匹配
let index = content.indexOf(oldText);

// 2. 模糊匹配（标准化后比较）
if (index === -1) {
  const normalizedContent = normalizeForFuzzyMatch(content);
  const normalizedOldText = normalizeForFuzzyMatch(oldText);
  // 标准化处理：
  // - 去除行尾空白
  // - 智能引号 → ASCII 引号
  // - Unicode 破折号 → 标准连字符
  // - 特殊空格 → 普通空格
}

// 匹配失败 → 返回详细错误让 LLM 重试
// 多处匹配 → 拒绝（要求更精确的文本）
```

**Bash Tool 超时**：spawn 进程树 kill，返回截断的输出和超时说明。

### 重试机制

**多层重试策略**：

| 层级 | 错误类型 | 策略 |
|------|---------|------|
| LLM Provider 层 | 速率限制、服务过载 | 指数退避（base 1s，最多 3 次），尊重服务器 Retry-After 头（上限可配，默认 60s） |
| Agent Session 层 | 可重试错误 | `_isRetryableError()` 检测，自动 `agent.continue()` |
| Agent Session 层 | Context overflow | 触发 auto-compaction → 压缩后自动重试 |

**Context Overflow 检测**（多 provider 适配）：

```typescript
// packages/ai/src/utils/overflow.ts
// 通过错误消息模式匹配检测各 provider 的溢出：
// Anthropic: "prompt is too long: X tokens > Y maximum"
// OpenAI: "Your input exceeds the context window"
// Google: "The input token count (X) exceeds the maximum"
// xAI: "This model's maximum prompt length is X"
// Cerebras/Mistral: HTTP 400/413 无 body

// 静默溢出检测（部分 provider 不报错但实际溢出）：
if (usage.input > contextWindow) return true;
```

**重试延迟提取**：从 HTTP 头（`Retry-After`、`x-ratelimit-reset`）和错误消息（`"Please retry in Xs"`、`"retryDelay": "34.074824224s"`）中提取服务器要求的等待时间。

---

## 7. 关键创新点

### 独特设计

#### 1. Steering / Follow-up 双消息队列

Pi 最独特的创新。用户在 Agent 执行工具时仍可输入：
- **Steering**（立即生效）：中断当前 tool 执行，将用户消息注入上下文，Agent 立即响应
- **Follow-up**（排队等待）：等 Agent 完成当前任务后再处理

这让交互体验从"等待 Agent 完成"变为"与 Agent 实时对话"。两种模式都支持 `"all"`（批量）和 `"one-at-a-time"`（逐条）配置。

#### 2. Pluggable Operations 模式

每个工具的底层操作（文件读写、命令执行等）通过接口注入，不硬编码本地文件系统：

```typescript
// 只需替换 operations 即可实现 SSH 远程执行
const readTool = createReadTool(cwd, { operations: sshReadOps });
const bashTool = createBashTool(cwd, { operations: sshBashOps });
```

这让同一套 tool 可以透明地在本地、Docker、SSH 远程等环境中运行。

#### 3. 结构化 Compaction 摘要

不同于简单的"总结对话历史"，Pi 要求 LLM 按固定结构（Goal / Progress / Decisions / Next Steps）生成摘要。后续 compaction 不从头写，而是 **UPDATE** 已有摘要，增量合并新进度。

#### 4. 深度扩展系统

扩展可以介入 Agent 生命周期的每个阶段：

| Hook | 介入点 |
|------|--------|
| `input` | 用户输入前（可拦截/转换） |
| `beforeAgentStart` | Agent 思考前（可注入 messages、改写 system prompt） |
| `context` | 上下文变换（可裁剪/富化消息） |
| `toolCall` / `toolResult` | Tool 执行前后 |
| `turnStart` / `turnEnd` | 每轮开始/结束 |
| `resourcesDiscover` | 资源发现（注册 provider、tool、command） |

扩展还可以注册自定义 tool、命令、键盘快捷键、CLI 参数，甚至覆盖 UI 组件。

#### 5. 多 Provider Overflow 检测

统一处理 10+ 个 LLM provider 的 context overflow 错误，包括：
- 标准错误消息模式匹配
- HTTP 状态码检测（400/413 无 body）
- 静默溢出检测（usage.input > contextWindow）

#### 6. Session 分支与持久化

- **JSONL 追加写入**：每条消息独立一行，崩溃安全
- **Session 分支**：支持从任意点 fork 出新会话，通过 `parentSession` 引用形成会话树
- **HTML 导出**：完整会话可导出为可视化 HTML 文件
- **自定义条目**：扩展可在 Session 中持久化自己的状态（CustomEntry），跨会话恢复

### 值得借鉴的模式

1. **Steering / Follow-up 队列**：解决了"用户必须等 Agent 完成才能继续输入"的体验问题
2. **Pluggable Operations**：通过依赖注入实现 tool 的环境无关性，无需修改 tool 代码即可切换执行环境
3. **结构化 Compaction**：固定格式的摘要比自由文本摘要更可靠，增量 UPDATE 模式避免信息丢失
4. **EventStream 模式**：自定义 async iterator + event queue，实现了流式事件的优雅传递
5. **Tool 结果双通道**：`content`（LLM 看到的）和 `details`（UI 看到的）分离，避免 UI 信息污染 LLM 上下文
6. **Tool Call ID 标准化**：跨 provider 统一 tool call ID 格式（OpenAI 450+ 字符 → Anthropic 64 字符限制）
7. **chars/4 Token 估算**：简单启发式替代 provider 特定 tokenizer，保守但实用

---

## 7.5 MVP 组件清单

基于以上分析，构建最小可运行版本需要以下组件：

| 组件 | 对应维度 | 核心文件 | 建议语言 | 语言理由 |
|------|----------|----------|----------|----------|
| 会话主循环 (agent-session-loop) | D2 | `packages/agent/src/agent.ts` (run / processMessages) | TypeScript | async/await + EventStream async iterator 是核心抽象 |
| 可插拔操作 (pluggable-ops) | D3 | `packages/agent/src/ops/` (OpsInterface) | Python | 依赖注入模式可用 Python 复现 |
| Prompt 构建器 (prompt-builder) | D4 | `packages/agent/src/prompts/`, `packages/agent/src/agent.ts` (buildMessages) | Python | 字符串模板拼接 |
| 多 Provider LLM 调用 (llm-multi-provider) | D2/D6 | `packages/agent/src/llm/` (LlmClient, providers/) | Python | 统一接口适配可用 Python + litellm 复现 |

**说明**: pi-agent 的主循环深度依赖 TypeScript async iterator 模式（EventStream），MVP 中主循环组件建议用 TypeScript。其余组件用 Python 即可。

---

## 8. 跨 Agent 对比

### vs Aider / Codex-CLI / OpenClaw / NanoClaw

| 维度 | pi-agent | aider | codex-cli | openclaw | nanoclaw |
|------|----------|-------|-----------|----------|----------|
| **定位** | 模块化 agent 工具包 | 终端编码助手 | CLI 编码 agent | 多通道 AI 助手平台 | 极简个人 AI 助手 |
| **语言** | TypeScript（Node.js） | Python | Rust + TypeScript | TypeScript | TypeScript |
| **Agent Loop** | 双层循环 + steering/follow-up 队列，支持实时干预 | 三层嵌套（外层切换 + REPL + 反思循环） | tokio::select! 多路复用 + turn 循环 | 内嵌 pi-agent + 编排层（model fallback） | 双层：Host 消息轮询 + Container SDK query 循环 |
| **Tool 系统** | 原生 LLM tool calling + TypeBox schema 校验 + pluggable operations | 双轨制：用户命令（cmd_* 约定）+ LLM 文本格式（SEARCH/REPLACE） | 原生 function calling + 审批门 | 47 tool + 4 档 profile + policy pipeline | Claude SDK 内置 + MCP 自定义（6 tool） |
| **Context 策略** | 阈值触发 + LLM 结构化摘要压缩，无代码分析 | tree-sitter AST + PageRank 仓库地图，二分搜索 token 约束 | bytes/4 估算 + 首尾保留截断 + auto-compact | pi-agent 摘要 + tool result 截断 + DM 限制 | 全委托 Claude Agent SDK |
| **编辑方式** | edit tool（精确文本替换 + 模糊匹配） | 12+ 种编辑格式多态切换 | apply_patch（unified diff） | 继承 pi-agent edit tool | Claude SDK 内置 edit |
| **安全模型** | 无内建沙箱 | Git 集成（自动 commit + undo） | 三级审批 + 平台沙箱 + 网络代理 | Docker 沙箱 + Owner 信任分级 | Docker 容器隔离 + 外部 allowlist |
| **错误处理** | 多 provider overflow 检测 + 指数退避 + auto-compact 重试 | 多级容错解析 + 反思循环 + 指数退避 | 可重试性分类 + 指数退避 | Failover 分类器 + Auth 轮转 + session 修复 | 指数退避 + 游标回滚 + 哨兵标记解析 |
| **扩展性** | 深度扩展系统（hook 每个生命周期阶段） | 无正式扩展系统 | Hooks + MCP + Skills + Custom Prompts | Plugin SDK + 31 extension + 51 skills | Claude Code Skills（代码变换） |
| **LLM 支持** | 原生多 provider SDK（OpenAI, Anthropic, Gemini, Bedrock, Mistral） | 通过 litellm 统一适配 | OpenAI 为主（可配置） | 继承 pi-agent + auth profile 轮转 | 仅 Claude（SDK 绑定） |
| **Session** | JSONL 持久化 + 分支 + HTML 导出 | Git 集成（自动 commit + undo） | 无明显持久化 | JSONL + SQLite 语义记忆 + 混合检索 | CLAUDE.md 文件 + SQLite session |
| **通道** | CLI + Slack Bot | 仅 CLI | 仅 CLI | 13+ 消息平台 + Gateway RPC | WhatsApp + skill 扩展 |

### 总结

Pi-agent 是一个**架构精良、高度模块化的 AI Agent 工具包**。其核心优势在于三点：

1. **实时交互**：通过 Steering/Follow-up 双消息队列，用户可以在 Agent 执行期间随时干预或追加需求，体验远优于传统"提交-等待"模式
2. **环境无关性**：Pluggable Operations 模式让工具代码与执行环境解耦，同一套 tool 可透明运行在本地、SSH、Docker 等环境
3. **深度可扩展**：扩展系统覆盖 Agent 生命周期每个阶段，从输入拦截到 UI 覆盖，扩展能力远超同类 Agent

与 Aider 相比，Pi 更重**架构抽象和运行时灵活性**（分层设计、扩展系统、多 provider 原生支持），而 Aider 更重**代码理解智能**（RepoMap、多编辑格式、Git 深度集成）。与 Codex CLI 相比，Pi 有更灵活的环境抽象（Pluggable Ops）和实时交互（Steering Queue），Codex CLI 有硬件级沙箱和网络代理。与 OpenClaw 相比，Pi 是 OpenClaw 的**内嵌核心引擎**——OpenClaw 直接以库方式调用 pi-agent（`@mariozechner/pi-coding-agent` v0.54.1），在其之上构建了 Gateway 控制面、13+ 通道路由、语义记忆、Docker 沙箱、Cron 调度、47 tool profile 体系和 Plugin SDK 生态。与 NanoClaw 相比，两者代表了完全不同的 agent 构建理念——Pi 自研了完整的 Agent Session 循环、Pluggable Ops、EventStream 和多 Provider SDK，而 NanoClaw 将 agent 核心全部委托给 Claude Agent SDK（黑盒），只自研容器编排和 IPC 通信；Pi 的模块化设计使其可被 OpenClaw 内嵌复用，NanoClaw 的"代码即配置"哲学则鼓励直接修改源码而非模块化集成。Pi 的模块化设计和扩展接口使得"内嵌 + 平台包装"模式成为可能，验证了 pi-agent 作为可嵌入 Agent 工具包的架构定位。
