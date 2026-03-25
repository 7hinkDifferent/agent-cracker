# gemini-cli — Deep Dive Analysis

> Auto-generated from template on 2026-03-25
> Repo: https://github.com/google-gemini/gemini-cli
> Analyzed at commit: [`0c91985`](https://github.com/google-gemini/gemini-cli/tree/0c919857fa5770ad06bd5d67913249cd0f3c4f06) (2026-03-25)

## 1. Overview & Architecture

### 项目定位
Gemini CLI 是 Google Gemini 官方开源的 AI agent，通过终端提供 Gemini 直接访问。它是一个纯编码 agent，为开发人员设计，支持内置工具（Google Search、文件操作、Shell 命令、Web 获取）并通过 MCP（Model Context Protocol）提供可扩展性。

### 技术栈
- **语言**：TypeScript/JavaScript（Node.js ≥20）
- **框架**：React with Ink（TUI 框架）
- **LLM**：Google Gemini（原生 SDK）
- **工具系统**：MCP + 本地工具注册
- **事件系统**：Event-driven architecture
- **打包**：ESBuild、npm workspaces（monorepo）

### 核心架构图

```
┌─────────────────────────────────────────────────────────┐
│                    Interactive CLI（Ink UI）            │
│              Or Non-Interactive Command Mode            │
└────────────────┬──────────────────────────────┬────────┘
                 │                              │
        ┌────────▼──────────┐        ┌─────────▼─────────┐
        │  CLI Entry Point  │        │ Config & Auth     │
        │  (packages/cli)   │        │ (OAuth, Settings) │
        └────────┬──────────┘        └──────────────────┘
                 │
        ┌────────▼────────────────────┐
        │  AgentSession Wrapper       │
        │  (Event Stream Protocol)    │
        └────────┬────────────────────┘
                 │
    ┌────────────▼────────────────┐
    │  Legacy Agent Loop          │
    │  (Main Reasoning Loop)      │
    └────┬─────────────────────┬──┘
         │                     │
    ┌────▼──────────┐  ┌──────▼────────┐
    │  LLM Client   │  │  Tool Scheduler│
    │  (Gemini API) │  │  (MCP + Local) │
    └───────────────┘  └────────────────┘
```

### 关键文件/目录
| 文件/目录 | 作用 |
|-----------|------|
| packages/cli | CLI 入口、配置解析、UI 管理（Ink） |
| packages/core | 核心 agent 逻辑、工具系统、提示管理 |
| packages/core/src/agent | AgentSession、LegacyAgentSession、主循环 |
| packages/core/src/tools | 工具注册、MCP 集成、工具调用 |
| packages/core/src/prompts | 提示注册、动态提示组装 |
| packages/sdk | 公开 SDK（用于第三方集成） |
| packages/vscode-ide-companion | VSCode IDE 伴侣应用 |

---

## 2. Agent Loop（主循环机制）

### 循环流程
Gemini CLI 的主循环在 `legacy-agent-session.ts` 中的 `_runLoop()` 方法：

```
1. [初始化] 接收用户输入的 Part[]（text/file/tool response）
2. [增强] 计数器检查（防止无限循环，maxTurns 限制）
3. [思考] 调用 LLM：sendMessageStream(currentParts)
4. [流式处理] 迭代 LLM 事件流：
   - ToolCallRequest → 收集到 toolCallRequests[]
   - Finished → 检查是否有待执行工具
   - Error/ContextWindowWillOverflow → 终止
5. [行动] 如有工具调用，交给 Scheduler 并发执行
6. [观察] 收集工具响应，构建 toolResponseParts[]
7. [反馈] 将工具响应回流到  LLM
8. [重复] 继续步骤 2 直到终止
```

### 终止条件
- **成功完成**：LLM 返回 Finished 且无工具调用（`finish_reason: STOP`）
- **用户中断**：`UserCancelled` 事件
- **工具终止信号**：工具返回 `STOP_EXECUTION` 错误
- **致命错误**：工具返回致命错误（`isFatalToolError()`）
- **超出轮数限制**：`turnCount > maxTurns`
- **LLM 错误**：Error、InvalidStream、ContextWindowWillOverflow
- **中止信号**：`abortController.signal.aborted` 被设置

### 关键代码
```typescript
// packages/core/src/agent/legacy-agent-session.ts (L144-230)
private async _runLoop(initialParts: Part[]): Promise<void> {
  let currentParts: Part[] = initialParts;
  let turnCount = 0;
  const maxTurns = this._config.getMaxSessionTurns();

  while (true) {
    turnCount++;
    if (maxTurns >= 0 && turnCount > maxTurns) {
      this._finishStream('max_turns', {...});
      return;
    }

    const toolCallRequests: ToolCallRequestInfo[] = [];
    const responseStream = this._client.sendMessageStream(
      currentParts,
      this._abortController.signal,
      this._promptId,
    );

    for await (const event of responseStream) {
      if (event.type === GeminiEventType.ToolCallRequest) {
        toolCallRequests.push(event.value);
      }
      this._emit(translateEvent(event, this._translationState));
      
      switch (event.type) {
        case GeminiEventType.Finished:
          if (toolCallRequests.length === 0) {
            this._finishStream(mapFinishReason(event.value.reason));
            return;
          }
          break;
        case GeminiEventType.Error:
        case GeminiEventType.ContextWindowWillOverflow:
          this._finishStream('failed');
          return;
        // ... 其他终止条件
      }
    }

    // 工具执行环节
    if (toolCallRequests.length === 0) {
      this._finishStream('completed');
      return;
    }

    const completedToolCalls = await this._scheduler.schedule(
      toolCallRequests,
      this._abortController.signal,
    );

    // 收集工具响应并准备下一轮 LLM 输入
    const toolResponseParts: Part[] = [];
    for (const tc of completedToolCalls) {
      const content = buildToolResponseContent(tc.response);
      toolResponseParts.push(...content);
    }

    currentParts = toolResponseParts;
  }
}
```

**事件流特性**：
- 使用 Genai SDK 的流式接口 `sendMessageStream()` 获取实时事件
- 每个事件（Text、ToolCallRequest、Finished 等）立即被转译并发送给订阅者
- 支持中途 abort（通过 AbortController）

---

## 3. Tool/Action 系统

### Tool 注册机制
Gemini CLI 采用**多源工具注册**机制，支持内置工具、本地工具和 MCP 工具：

1. **内置工具**：在 `tools.ts` 中定义的本地工具类（`EditTool`, `WriteTool`, `ShellTool`, `GlobTool`, `ReadManyFilesTool` 等）
2. **MCP 工具**：通过 `DiscoveredToolInvocation` 和 `mcp-client-manager.ts` 从 MCP 服务器动态发现
3. **工具注册流程**：
   ```
   ToolRegistry (维护工具列表)
        ↓
   各工具类 extends BaseDeclarativeTool
        ↓
   buildAndExecute(params, signal) → ToolResult
   ```

### Tool 列表（MVP 核心工具）
| Tool | 功能 | 类型 | 调用方式 |
|------|------|------|----------|
| `edit` | 使用 diff 格式修改代码文件 | 内置 | `EditTool.buildAndExecute({file, diffs})` |
| `write-file` | 创建或覆盖文件 | 内置 | `WriteFileTool.buildAndExecute({file, content})` |
| `read-file` | 读取单个文件 | 内置 | `ReadFileTool.buildAndExecute({file})` |
| `read-many-files` | 批量读取文件 | 内置 | `ReadManyFilesTool.buildAndExecute({files})` |
| `shell` | 执行 Shell 命令 | 内置 | `ShellTool.buildAndExecute({command})` |
| `glob` | 文件模式匹配 | 内置 | `GlobTool.buildAndExecute({pattern})` |
| `grep` | 文本搜索 | 内置 | `GrepTool.buildAndExecute({query, files})` |
| `web-search` | Google Search（需 API Key） | 内置 | `WebSearchTool.buildAndExecute({query})` |
| `web-fetch` | 获取网页内容 | 内置 | `WebFetchTool.buildAndExecute({url})` |
| `memory` | 持久化笔记存储（用户内存） | 内置 | `MemoryTool.buildAndExecute({action, content})` |
| `ask-user` | 交互确认 | 内置 | `AskUserTool.buildAndExecute({question})` |
| `*` (MCP tools) | 来自 MCP 服务器的动态工具 | MCP | `MCPClientManager.invokeTool()` |

### Tool 调用流程

代码路径：`packages/core/src/agent/legacy-agent-session.ts` → `scheduler.schedule()`

```
1. [LLM 输出] LLM 返回 ToolCallRequest
   {
     callId: string,
     name: string,     // 工具名
     input: {          // 工具参数（通过 Genai SDK 验证）
       file?: string,
       content?: string,
       ...
     }
   }

2. [调度] this._scheduler.schedule(toolCallRequests, signal)
   - 并发执行多个工具（如果支持）
   - 每个工具调用获得 AbortSignal（支持中断）

3. [执行] 根据工具类型调用相应的 buildAndExecute()
   
   if (tool is MCP) {
     // MCP 工具：序列化参数 → 发送给 MCP 服务器 → 反序列化结果
     const result = await mcpClient.invoke(toolName, params);
   } else {
     // 内置工具：直接调用（可能跨进程沙箱）
     const tool = new ToolClass(messageBus, config);
     const invocation = tool.buildInvocation(params);
     const result = await invocation.execute(signal);
   }

4. [响应] 构建 ToolResult
   {
     responseParts: Part[],     // 文本/数据响应
     resultDisplay?: Display,   // UI 显示优化
     error?: ToolError,         // 错误（如有）
     errorType: ToolErrorType,  // 错误分类
   }

5. [反馈] 将响应转换为 Part[]，作为下一轮 LLM 输入
```

**关键特性**：
- **参数验证**：Genai SDK 在发送前验证参数符合 FunctionDeclaration schema
- **沙箱执行**：可选的 Docker/Podman 沙箱隔离（通过 `sandboxManager`)
- **权限校验**：MessageBus 支持交互确认流程（`ask_user` 工具）
- **MCP 支持**：通过 `mcp-tool.ts` 和 `mcp-client-manager.ts` 无缝集成任意 MCP 服务器
- **流式响应**：某些工具（如 Shell）支持流式输出

---

## 4. Prompt 工程

### System Prompt 结构
Gemini CLI 的 system prompt 通过 **PromptRegistry** 和 **MCP 集成**组织：

**核心层次结构**：
```
├─ Base System Context（模型选择题和通用指令）
├─ Tool Usage Guidelines（如何调用可用工具）
├─ MCP Server Prompts（来自 MCP 的动态提示）
├─ User Memory Context（用户持久化笔记）
├─ File Context（相关代码文件）
└─ Conversation History（截断的对话历史）
```

### 动态 Prompt 组装
1. **PromptRegistry** (`packages/core/src/prompts/prompt-registry.ts`)：
   - 注册来自 MCP 服务器的动态提示
   - 支持提示名冲突解决（重命名为 `{serverName}_{promptName}`）

2. **工具声明注入**：
   - Genai SDK 自动从已注册工具生成 `FunctionDeclaration`
   - 包括参数 schema 和工具描述

3. **上下文注入时机**：
   - 在 `sendMessageStream()` 调用时动态构造
   - 支持逐轮调整（如根据用户反馈调整提示权重）

### Prompt 模板位置
- `packages/core/src/prompts/` - 提示管理核心模块
  - `prompt-registry.ts` - 提示注册与查询
  - `prompt-registry.test.ts` - 单元测试
- `packages/core/GEMINI.md` - 用户可读的提示文档
- MCP 集成提示：支持来自 MCP 服务器的 `resources://` 和 `prompts://` 协议

**示例**：当 MCP 服务器 "code_server" 提供提示 "refactor"，会被注册为：
```json
{
  "name": "code_server_refactor",
  "description": "Refactor code using AI",
  "arguments": [
    {"name": "language", "description": "Programming language"}
  ]
}
```

---

## 5. 上下文管理

### 上下文窗口策略
Gemini CLI 利用 Gemini 的大上下文窗口（1M token），但仍需管理：

1. **动态上下文窗口检测**：
   - LLM 发出 `GeminiEventType.ContextWindowWillOverflow` 事件时终止
   - 防止超限导致请求失败

2. **增量式上下文构建**：
   - 初始化：用户查询 → 工具调用 → 获取文件内容
   - 逐轮增加：每次 LLM 响应都包含在下一轮的上下文中
   - 无显式截断：依赖 LLM 的上下文长度和计费

3. **对话历史管理**：
   - 所有事件记录在 `AgentSession.events[]` 中
   - 支持会话恢复：通过 `eventId` 或 `streamId` 重新开始对话
   - 参考实现：`agent-session.ts` 的 `stream()` 方法

### 文件/代码的 context 策略
- **JIT Context**（Just-In-Time）：`jit-context.ts` 动态获取相关文件
- **Smart File Selection**：
  - 用户明确指定的文件（`read-file`、`read-many-files` 工具）
  - LLM 通过 `glob`、`grep` 自动化搜索
  - 编辑过的文件自动添加到编辑响应中

### 对话历史管理
```typescript
// packages/core/src/agent/agent-session.ts
async *stream(options: {
  eventId?: string;  // 从特定事件恢复
  streamId?: string; // 从特定流恢复
}) {
  // 重放历史事件 → 实时订阅新事件
  const currentEvents = this._protocol.events;
  const replayStartIndex = findReplayIndex(currentEvents, options);
  
  for (let i = replayStartIndex; i < currentEvents.length; i++) {
    yield currentEvents[i];
  }
  
  // 订阅并等待新事件
  while (!done) {
    await next;
    yield eventQueue.pop();
  }
}
```

**历史特性**：
- **持久化**：会话数据可通过 `ResumedSessionData` 恢复
- **游标支持**：支持非线性导航（从中途恢复、分支）
- **事件索引**：通过唯一 `eventId` 精确定位

---

## 6. 错误处理与恢复

### LLM 输出解析错误
- **Genai SDK 集成**：SDK 自动验证 FunctionDeclaration 参数，发送前即可检测参数错误
- **流式错误事件**：LLM 返回错误时立即作为流事件发出
  ```typescript
  // 在 _runLoop 中处理
  case GeminiEventType.Error:
  case GeminiEventType.InvalidStream:
    this._finishStream('failed');
    return;
  ```
- **恢复策略**：会话终止，用户可通过会话恢复功能重新开始

### Tool 执行失败
工具错误分类（`ToolErrorType` enum）：
| 错误类型 | 含义 | 处理 |
|----------|-------|------|
| `STOP_EXECUTION` | 用户或工具发起停止信号 | 停止循环，返回成功 |
| `FATAL_ERROR` | 工具执行失败（致命） | 停止循环，返回失败 |
| `TOOL_NOT_FOUND` | 工具不存在 | LLM 响应错误，继续循环 |
| `INVALID_PARAMS` | 参数不合法 | LLM 响应错误，继续循环 |

**错误处理流程**：
```typescript
const completedToolCalls = await this._scheduler.schedule(toolCallRequests);

const stopTool = completedToolCalls.find(
  tc => tc.response.errorType === ToolErrorType.STOP_EXECUTION
);
if (stopTool) {
  this._finishStream('completed');  // 正常结束
  return;
}

const fatalTool = completedToolCalls.find(
  tc => isFatalToolError(tc.response.errorType)
);
if (fatalTool) {
  this._finishStream('failed');     // 异常结束
  return;
}
```

### 重试机制
- **自动重试**：暂未在 legacy-agent-session 中实现显式重试逻辑
- **隐式重试**：LLM 可靠地重新生成工具调用
- **用户重试**：通过会话恢复 + `ask-user` 工具与用户协商重试策略
- **沙箱重试**：Docker/Podman 执行失败时报错，不自动重新执行

---

## 7. 关键创新点

### 独特设计

#### 1. **流式事件驱动架构**
- 不同于传统轮次制（回轮询 LLM 然后等待完整响应），Gemini CLI 使用完全流式化的事件模型
- 每个 LLM 事件（Text、ToolCallRequest、Finished）立即发送给订阅者
- 支持实时 UI 更新和中途中断，改善用户体验

#### 2. **AgentSession 包装器模式**
- 将原始 `AgentProtocol` 包装，提供 `AsyncIterable<AgentEvent>` 接口
- 支持**会话恢复**：通过 `eventId` 或 `streamId` 精确重放历史
  ```typescript
  const session = new AgentSession(protocol);
  for await (const event of session.stream({ eventId: 'last-error-point' })) {
    // 从错误点恢复，重新开始
  }
  ```
- 自动处理早期事件订阅竞态（`earlyEvents` 队列）

#### 3. **MCP 原生集成**
- 无缝支持任意 MCP 服务器的工具和提示
- Tool：通过 `mcp-client-manager.ts` 动态发现和调用
- Prompt：通过 `PromptRegistry` 注册并动态注入到 system prompt
- 降低扩展成本：无需修改核心代码即可添加新功能

#### 4. **权限沙箱 + 交互确认**
- **沙箱执行**：可选的 Docker/Podman 隔离危险工具（Shell、文件操作）
- **MessageBus + 确认策略**：在执行前请求用户确认
- **权限管理**：基于 `ApprovalMode` 的灵活策略（自动、交互、拒绝）

#### 5. **多模态工具集**
- 支持文本、文件、Shell、Web（搜索+获取）、用户交互
- 统一的 `ToolResult` 接口支持文本、二进制、结构化数据响应
- `resultDisplay` 字段支持 TUI 优化渲染

### 值得借鉴的模式

| 模式 | 位置 | 可复用性 |
|------|------|----------|
| **流式事件协议** | `agent-session.ts` | ⭐⭐⭐⭐⭐ 高度通用，任何 agent 都能采用 |
| **Replay + Resume** | `stream()` 方法 | ⭐⭐⭐⭐ Agent framework 必备特性 |
| **MCP Plugin 架构** | `mcp-client-manager.ts` | ⭐⭐⭐⭐⭐ 定义了标准的可扩展性 |
| **权限 + 沙箱分离** | `confirmation-bus/` + `sandbox/` | ⭐⭐⭐⭐ 企业级产品必需 |
| **Tool 元数据 + 验证** | `FunctionDeclaration` 集成 | ⭐⭐⭐⭐⭐ Type Safety 保证 |
| **Monorepo + Workspace** | `packages/` 结构 | ⭐⭐⭐⭐ 多role 分离（CLI/SDK/Core） |

---

## 7.5 MVP 组件清单

基于以上分析，构建最小可运行版本需要以下组件：

| 组件 | 对应维度 | 核心文件 | 建议语言 | 语言理由 |
|------|----------|----------|----------|----------|
| **事件驱动主循环** | D2 | `agent/legacy-agent-session.ts`（241 行） | Python* | 简化异步模型；Gemini CLI 复杂的流处理可用 `asyncio.Queue()` 实现 |
| **LLM 通信（Gemini）** | D2 | `agent-session.ts`、`core/gemini-client.ts` | Python | LLM SDK 天然支持（`google.generativeai`） |
| **工具注册与调度** | D3 | `tools/tool-registry.ts`、`tools/tools.ts`（基类） | Python | Tool Builder 模式通用，不依赖 TypeScript 类型系统 |
| **内置工具集** | D3 | `tools/{edit,write-file,read-file,shell,glob,grep}.ts` | Python | 5-6 个 MVP 工具足够；系统 API 无差异 |
| **Prompt 注册与组装** | D4 | `prompts/prompt-registry.ts`（30 行） | Python | 工具声明动态注入；无特殊 TS 需求 |
| **上下文管理** | D5 | `agent-session.ts` 的 `stream()`（180 行） | Python | 会话恢复逻辑通用；无语言依赖 |
| **错误处理 & 恢复** | D6 | `tools/tool-error.ts`、主循环的 switch 块 | Python | ToolErrorType 枚举 + isFatalToolError() 检查即可 |

**语言决策说明**：

1. **为何推荐 Python**：
   - Gemini CLI 的复杂度主要来自 TypeScript 的类型系统和 React UI（Ink）
   - 核心 agent 逻辑（事件循环、工具分发、上下文恢复）与语言无关
   - Python 的 `asyncio` + `dataclass` 可更简洁地表达这些机制

2. **原生 TypeScript 仅需在以下情况**：
   - 集成 VSCode IDE（vscode-ide-companion）
   - 支持浏览器 WebUI（需客户端/服务器分离）
   - 与现有 Node.js 工具链紧密耦合

### MVP 一句话描述
最小的可运行 Gemini CLI agent：事件驱动的主循环 + 8 个内置工具 + 会话恢复 = 100-150 行 Python 核心代码 + 200 行工具实现。

---

## 8. 跨 Agent 对比

| 维度 | gemini-cli | aider | pi-agent | openclaw |
|------|-----------|-------|----------|----------|
| **主循环** | 事件驱动流式 | 响应轮询式 | 异步队列式 | 继承 pi-agent 的队列 + 网关路由 |
| **LLM 支持** | Gemini 原生（可扩展） | Claude（多 provider via litellm） | 多 provider 原生 SDK | 多 provider + auth 轮转 |
| **工具系统** | MCP 原生集成 | 基于 Genai API 的工具 | 可插拔工具模块 | Skill center + 工具注入 |
| **上下文** | 1M token 大窗口 + JIT | 4K-8K token + Repomap | 可配置，无显式管理 | Hybrid memory 混合存储 |
| **会话恢复** | 原生支持（eventId） | 无内置支持 | 轻量支持（单线程） | 持久化 worktree 恢复 |
| **权限模型** | MessageBus + 沙箱 | 用户确认（交互） | 权限菜单选择 | Auth profile + 角色管理 |
| **工具隔离** | Docker/Podman 可选 | 本地执行 | 本地执行 + 权限检查 | Docker 强制隔离 |
| **可扩展性** | ⭐⭐⭐⭐⭐ (MCP) | ⭐⭐⭐ (API) | ⭐⭐⭐⭐ (插件) | ⭐⭐⭐⭐⭐ (平台模式) |
| **代码行数** | ~10K (TS monorepo) | ~5K (Python) | ~8K (TypeScript) | ~20K (多渠道) |

### 总结
**Gemini CLI** 的核心竞争优势：
1. **第一个原生 MCP 支持的 agent**：通过插件机制实现无限扩展
2. **流式事件架构**：实时反馈、支持中途中止、无延迟
3. **会话恢复机制**：首个支持精确 eventId 恢复的 agent（对标 Cursor 的 undo/redo）
4. **Google 官方背书**：Gemini 官方产品，获得一级支援

**适用场景**：
- 快速原型与实验（MCP 易集成）
- 长期任务（1M token 窗口）
- 需要中断/恢复的工作流（会话恢复）
- Google 生态用户（Gemini API 免费额度较高）

---

---

## 9-12. 平台维度分析

**不适用**。Gemini CLI 是纯编码 agent，不涉及多渠道、网关路由、跨会话持久化等平台级机制。

---

## 分析元数据

| 字段 | 值 |
|------|-----|
| 分析完成 | 2026-03-25 |
| 分析过程 | 8+4 维度深度审视 |
| MVP 覆盖 | 核心 7 个组件，约 350 行代码 |
| 下一步 | 创建 Python demo（`demos/gemini-cli/`） |

### 通道架构
<!-- 用户输入如何从外部渠道（CLI、Web、IM、语音）路由到 Agent？ -->
<!-- 有无 Gateway / Message Bus / WebSocket 控制面？ -->

### 支持的通道
| 通道 | 协议/集成方式 | 特点 |
|------|--------------|------|
| | | |

### 消息标准化
<!-- 不同渠道的消息格式如何统一？ -->

### 多模态支持
<!-- 语音输入/输出、Canvas/可视化、图片/文件处理 -->

---

## 10. 记忆与持久化 _(平台维度 · 可选)_

<!-- 仅适用于具有跨 session 记忆能力的 agent -->
<!-- 注意与 D5（session 内 context window 管理）的区别：D5 关注单次会话内的 token 约束，D10 关注跨会话的知识持久化 -->

### 持久化架构
<!-- Session 如何存储？格式（JSONL、SQLite、向量数据库等）？ -->

### 长期记忆
<!-- 跨 session 的知识如何积累、检索、更新？ -->
<!-- 向量检索 / 关键词搜索 / 混合策略？ -->

### 状态恢复
<!-- 崩溃恢复、session 分支、session 导出 -->

---

## 11. 安全模型与自治 _(平台维度 · 可选)_

<!-- 仅适用于有信任分级、沙箱或自主调度的 agent -->

### 信任分级
<!-- 不同来源的用户/通道有不同权限吗？ -->
<!-- operator session vs user session？ -->

### 沙箱策略
<!-- Docker 隔离、文件系统限制、网络策略 -->

### 自主调度
<!-- Cron / 定时任务 / Heartbeat / 无用户触发的自主执行？ -->

### 多 Agent 协作
<!-- Agent 间通信、任务委派、会话发现 -->

---

## 12. 其他特色机制 _(平台维度 · 可选)_

<!-- 不属于 D9-D11 但值得分析的独特机制 -->
<!-- 例如：Skills 市场/生态、Companion Apps、特殊 UI 模式、独特的部署架构 -->

### 机制列表
| 机制 | 简述 | 关键代码 |
|------|------|----------|
| | | |

### 详细分析
<!-- 逐个展开每个特色机制 -->
