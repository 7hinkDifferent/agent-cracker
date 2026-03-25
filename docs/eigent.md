# eigent — Deep Dive Analysis

> Repo: https://github.com/eigent-ai/eigent
> Analyzed at commit: [`38f8f2b`](https://github.com/eigent-ai/eigent/tree/38f8f2b292d7d1f64dbd211312ca335202565c83) (2026-03-25)

## 1. Overview & Architecture

### 项目定位

Eigent 是一款开源桌面应用（Electron），用于构建和管理 **多 Agent AI 团队**（Workforce），让非技术用户也能通过自然语言驱动多个专业 Agent 并行协作完成复杂任务。核心引擎基于 [CAMEL-AI](https://github.com/camel-ai/camel) 框架，支持本地私有化部署。

### 技术栈

| 层 | 技术 | 备注 |
|----|------|------|
| 桌面壳 | Electron 33 | 管理窗口、IPC、后台进程 |
| 前端 | React 18 + TypeScript 5 + Vite | Radix UI、Tailwind、React Flow、xterm.js |
| 状态管理 | Zustand | 轻量级前端 store |
| 后端（Agent 引擎） | FastAPI + Python 3.11 | `backend/` 目录 |
| 多 Agent 框架 | CAMEL-AI 0.2.90a6 | Workforce、ChatAgent、FunctionTool |
| 后端（用户/数据） | FastAPI + SQLModel + PostgreSQL | `server/` 目录（可选） |
| 任务队列 | Celery + Redis | 定时触发、后台任务 |
| 向量数据库 | Qdrant | RAG 检索 |
| LLM 集成 | OpenAI SDK | 多平台适配（OpenAI/Azure/LiteLLM/OpenRouter） |

### 核心架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    ELECTRON DESKTOP APP                      │
│   main process ─── IPC ─── renderer (React)                 │
├─────────────────────────────────────────────────────────────┤
│ FRONTEND (src/)                                             │
│  Pages: Home | Agents | Browser | Channels | Connectors     │
│  Components: ChatBox | WorkFlow(React Flow) | Terminal(xterm)│
│  Hooks: useExecutionSubscription(SSE) | useBackgroundTask   │
│  Store: Zustand (auth, task, chat state)                    │
├───────────────── HTTP / SSE ────────────────────────────────┤
│ BACKEND — Agent Engine (backend/)                           │
│  Controller: chat / tool / model / task / health            │
│  Service: chat_service.step_solve() ← 主循环               │
│  Agent: ListenChatAgent(CAMEL ChatAgent)                    │
│  Factory: developer | browser | document | multi_modal      │
│          | mcp | question_confirm | social_media | summary  │
│  Workforce: 任务分解 → 并行执行 → 结果汇总                   │
│  Toolkit: 30+ (terminal, browser, file, excel, github ...)  │
├───────────────── HTTP / DB ─────────────────────────────────┤
│ SERVER — User & Data Layer (server/, 可选)                   │
│  User: 注册/登录/OAuth  │  Provider: LLM 凭证管理           │
│  Chat: 聊天历史持久化    │  MCP: MCP 服务器安装/管理          │
│  Trigger: Webhook/Slack/定时触发  │  Config: 密钥/参数存储   │
│  PostgreSQL + Redis + Celery                                │
└─────────────────────────────────────────────────────────────┘
```

### 关键文件/目录

| 文件/目录 | 作用 |
|-----------|------|
| `backend/app/service/chat_service.py` | 主循环 `step_solve()`，队列驱动的事件循环 |
| `backend/app/agent/listen_chat_agent.py` | ListenChatAgent — 扩展 CAMEL ChatAgent，注入 UI 事件 |
| `backend/app/agent/agent_model.py` | Agent 工厂函数，模型创建 + Agent 实例化 |
| `backend/app/agent/prompt.py` | 8 种 Agent 的 system prompt（~700 行） |
| `backend/app/agent/tools.py` | Toolkit 收集器 + MCP 工具加载 |
| `backend/app/agent/factory/` | 8 个 Agent 专用工厂（developer, browser, ...） |
| `backend/app/agent/toolkit/` | 30+ 专用 Toolkit（browser, terminal, file, ...） |
| `backend/app/utils/workforce.py` | Workforce 扩展 — 任务分解、并行执行、失败重试 |
| `backend/app/controller/chat_controller.py` | Chat HTTP 入口，SSE 流式响应 |
| `server/app/controller/trigger/` | Webhook/Slack 触发器管理 |
| `server/app/controller/mcp/mcp_controller.py` | MCP 服务器安装与管理 |
| `electron/main/index.ts` | Electron 主进程，窗口/IPC/后端启动 |
| `src/hooks/useExecutionSubscription` | SSE 事件订阅，驱动前端 UI 更新 |

---

## 2. Agent Loop（主循环机制）

### 循环流程

Eigent 的主循环是一个 **异步队列驱动的事件循环**，位于 `chat_service.step_solve()`。不同于传统的 `while True: think → act → observe` 简单循环，Eigent 通过 `TaskLock.queue` 实现解耦的事件分发：

```
用户消息 → POST /chat → step_solve()
                          │
                    while True:
                      item = await task_lock.get_queue()
                          │
          ┌───────────────┼───────────────────────────┐
          │               │                           │
    Action.improve   Action.start              Action.stop
    (新问题到达)      (开始执行)               (用户停止)
          │               │                           │
    ┌─────┴─────┐   workforce.eigent_start()     break
    │ 简单问题？ │   ├─ 并行执行子任务
    │           │   ├─ agent.step() → tool() 循环
    │  Y → 直接回答  └─ 完成后 → Action.end
    │  N → 创建 Workforce
    │     → 任务分解
    │     → 流式推送分解结果
    └───────────────────────────────────────────────┘
```

核心特点：
1. **复杂度判断**：收到用户问题后，先由 `question_confirm_agent` 判断复杂度。简单问题直接回答，复杂任务创建 Workforce
2. **任务分解**：Workforce 的 `eigent_make_sub_tasks()` 调用 CAMEL 的任务分解 prompt，将大任务拆分为可并行的子任务
3. **并行执行**：子任务分配给不同类型的 Worker Agent（developer、browser 等），通过 CAMEL 的 TaskChannel 并行执行
4. **多轮对话**：任务完成后循环不退出，等待下一个 `Action.improve`（用户追问）

### 终止条件

| 条件 | 触发方式 |
|------|----------|
| 用户点击停止 | `Action.stop` → `workforce.stop()` → `break` |
| 客户端断开 | `request.is_disconnected()` → cleanup → `break` |
| SSE 超时 | 60 分钟无数据 → timeout_stream_wrapper 关闭连接 |
| 对话历史过长 | 总长度 > 200000 字符 → 提示创建新项目 |

### 关键代码

```python
# chat_service.py — 主循环骨架
@sync_step
async def step_solve(options: Chat, request: Request, task_lock: TaskLock):
    while True:
        if await request.is_disconnected():
            break
        item = await task_lock.get_queue()

        if item.action == Action.improve or start_event_loop:
            # 判断复杂度
            is_complex_task = await question_confirm(question_agent, question, task_lock)
            if not is_complex_task:
                # 简单回答
                simple_resp = question_agent.step(simple_answer_prompt)
                yield sse_json("wait_confirm", {"content": answer_content})
            else:
                # 创建 Workforce → 任务分解 → 流式推送
                (workforce, mcp) = await construct_workforce(options)
                camel_task = Task(content=question + options.summary_prompt)
                bg_task = asyncio.create_task(run_decomposition())
        elif item.action == Action.start:
            await workforce.eigent_start(sub_tasks)
        elif item.action == Action.end:
            # 提取结果，记入对话历史
            task_lock.add_conversation("task_result", {...})
            yield sse_json("end", {...})
        elif item.action == Action.stop:
            workforce.stop()
            break
```

---

## 3. Tool/Action 系统

### Tool 注册机制

Eigent 采用 **三层 Toolkit 体系**，基于 CAMEL 的 `FunctionTool` 抽象：

1. **AbstractToolkit**（`toolkit/abstract_toolkit.py`）：所有 Toolkit 的基类，提供 `get_can_use_tools(api_task_id)` 模板方法，支持按条件过滤可用工具
2. **具体 Toolkit**：分为三类
   - **标准 Toolkit**（继承 CAMEL BaseToolkit）：Terminal、CodeExecution、File、Excel 等
   - **MCP Toolkit**（继承 CAMEL MCPToolkit）：Notion、Google Drive、Gmail
   - **自定义 Toolkit**：Human（人机交互）、Skill（用户自定义技能）、Search
3. **Factory 组装**：每个 Agent 工厂函数（如 `developer_agent()`）负责收集该类型 Agent 所需的所有 Toolkit

注册关键：
- `@auto_listen_toolkit(BaseToolkit)` 装饰器自动为所有方法注入 UI 事件
- `@listen_toolkit` 装饰器手动标记需要事件的方法
- `ToolkitMessageIntegration` 将 `HumanToolkit.send_message_to_user` 注入其他 Toolkit

### Tool 列表

| Toolkit | 功能 | Agent 类型 |
|---------|------|-----------|
| TerminalToolkit | Shell 命令执行 | Developer |
| CodeExecutionToolkit | Python/Jupyter 执行 | Developer |
| FileWriteToolkit | 文件读写 | Developer, Document |
| HybridBrowserToolkit | Selenium+Playwright 浏览器 | Browser |
| SearchToolkit | Web 搜索（Google） | Browser |
| ScreenshotToolkit | 屏幕截图 | Developer, Browser |
| ExcelToolkit | Excel 读写 | Document |
| PowerPointToolkit | PPT 创建 | Document |
| RAGToolkit | 向量检索增强 | Browser |
| HumanToolkit | 向用户提问/发消息 | 所有 |
| SkillToolkit | 用户自定义技能加载 | 所有 |
| NoteTakingToolkit | Agent 间笔记共享 | 所有 |
| NotionMCPToolkit | Notion API (via MCP) | Document |
| GoogleCalendarToolkit | 日历管理 | Social Media |
| SlackToolkit | Slack 消息 | Social Media |
| LinkedInToolkit | LinkedIn 发帖 | Social Media |
| RedditToolkit | Reddit 数据 | Social Media |
| ImageGenerationToolkit | DALL-E 图像生成 | Multi-Modal |
| AudioAnalysisToolkit | 音频转文字 | Multi-Modal |

### Tool 调用流程

```
LLM 返回 tool_call → ChatAgent._execute_tool()
                        ↓
              ListenChatAgent._execute_tool() 拦截
                        │
          ┌─────────────┼──────────────┐
          │             │              │
     同步工具       异步工具       MCP 工具
     tool(**args)  await tool.    await tool.func.
                   async_call()   async_call()
          │             │              │
          └─────────────┼──────────────┘
                        ↓
              with set_process_task():  # ContextVar 保持
                结果截断（>500 字符）
                        ↓
              前端事件: activate_toolkit → deactivate_toolkit
```

---

## 4. Prompt 工程

### System Prompt 结构

Eigent 为 8 种 Agent 各定义了独立的 system prompt（`backend/app/agent/prompt.py`），采用 **XML 标签结构化**：

```xml
<role>你是一个 Lead Software Engineer ...</role>
<team_structure>你与以下 Agent 协作：Browser、Document、Multi-Modal</team_structure>
<operating_environment>
  系统: {platform_system} ({platform_machine})
  工作目录: {working_directory}
  当前日期: {now_str}
</operating_environment>
<mandatory_instructions>
  - 必须使用 list_note() 发现其他 Agent 的笔记
  - 创建文件后必须注册到 shared_files
  - 完成时必须生成综合总结
</mandatory_instructions>
<capabilities>技能系统（最高优先级）、终端、文件系统 ...</capabilities>
<philosophy>偏向行动、完成全流程、拥抱挑战 ...</philosophy>
```

### 动态 Prompt 组装

| 动态部分 | 来源 | 示例 |
|----------|------|------|
| `{platform_system}` | `platform.system()` | `Darwin` |
| `{platform_machine}` | `platform.machine()` | `arm64` |
| `{working_directory}` | 项目工作目录 | `/tmp/eigent/project_123` |
| `{now_str}` | 当前日期时间 | `2026-03-25 14:00` |
| `{external_browser_notice}` | 外部浏览器提示 | Browser Agent 专用 |
| Conversation history | `build_conversation_context()` | 前几轮任务结果 |
| Coordinator context | 任务分解时注入 | `=== CONVERSATION HISTORY ===` |

### Prompt 模板位置

| 文件 | 内容 |
|------|------|
| `backend/app/agent/prompt.py` | 全部 8 种 Agent 的 system prompt + DEFAULT_SUMMARY_PROMPT |
| CAMEL `TASK_DECOMPOSE_PROMPT` | 任务分解 prompt（从 camel 框架导入） |

---

## 5. 上下文管理

### 上下文窗口策略

Eigent **主要依赖 CAMEL-AI 的 AgentMemory 管理 context window**，自身额外实现了会话级的对话历史管理：

- `ListenChatAgent` 接受 `message_window_size` 和 `token_limit` 参数（传递给 CAMEL ChatAgent）
- `prune_tool_calls_from_memory`：可选删除历史中的 tool call 消息以节省 token
- `enable_snapshot_clean`：启用内存快照清理

### 对话历史管理

多轮对话跨 Workforce 的上下文通过 `TaskLock.conversation_history` 维护：

```python
def check_conversation_history_length(task_lock, max_length=200000):
    """超过 200k 字符时提示用户创建新项目"""
    total_length = sum(len(entry.get("content", "")) for entry in task_lock.conversation_history)
    return total_length > max_length, total_length

def build_conversation_context(task_lock):
    """拼接历史任务结果 + 生成文件列表，作为新任务的上下文"""
    for entry in task_lock.conversation_history:
        if entry["role"] == "task_result":
            context += format_task_context(entry["content"], skip_files=True)
        elif entry["role"] == "assistant":
            context += f"Assistant: {entry['content']}"
    # 最后统一列出所有工作目录的文件
    for wd in working_directories:
        files = list_files(wd, skip_dirs={"node_modules", "__pycache__", "venv"})
```

### 文件/代码的 context 策略

- **工作目录文件列表**：`list_files()` 扫描工作目录（跳过 node_modules、__pycache__ 等），附加到上下文中
- **NoteTakingToolkit**：Agent 间通过笔记共享中间结果，避免重复搜索
- **前序任务结果**：`collect_previous_task_context()` 将上一个任务的内容、结果、摘要注入下一个任务

---

## 6. 错误处理与恢复

### LLM 输出解析错误

CAMEL 框架内部处理结构化输出解析。Eigent 在 Workforce 层增加了 `_analyze_task()` 重试：

```python
def _analyze_task(self, task, *, for_failure, error_message=None):
    """分析任务质量，重试 3 次。若分析失败：
    - for_failure=True（任务已失败）：raise RuntimeError
    - for_failure=False（质量评估）：返回默认 score=80 接受结果"""
    for attempt in range(1, _ANALYZE_TASK_MAX_RETRIES + 1):
        result = super()._analyze_task(task, ...)
        if result is not None:
            return result
```

### Tool 执行失败

ListenChatAgent 的 `_execute_tool()` 捕获所有异常，将错误转为字符串结果返回给 LLM：

```python
except Exception as e:
    error_msg = f"Error executing tool '{func_name}': {e!s}"
    result = f"Tool execution failed: {error_msg}"
    # 不 raise，而是作为 tool result 返回，让 LLM 自行判断下一步
```

### 重试机制

| 层级 | 重试策略 | 次数 |
|------|----------|------|
| Workforce 任务分析 | `_analyze_task` 返回 None 时重试 | 3 |
| Workforce 子任务失败 | `FailureHandlingConfig(strategies=["retry", "replan"])` | 3（max_retries） |
| MCP 连接 | Notion MCP toolkit 连接失败重试 | 3，间隔 2s |
| LLM 调用 | 通过 ModelFactory 的 `timeout=600` + `max_retries` | 可配置 |

### 异常体系

```python
# backend/app/exception/exception.py
UserException        # 用户错误（密码错误等）
TokenException       # 认证 token 无效
NoPermissionException  # 权限不足
ProgramException     # 程序内部错误
PathEscapesBaseError # 路径逃逸安全错误

# FastAPI 全局异常处理器（handler.py）
@api.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"code": 500, "message": str(exc)})
```

---

## 7. 关键创新点

### 独特设计

1. **Workforce 多 Agent 编排**：基于 CAMEL 的 Workforce，实现了任务自动分解 → 角色分配 → 并行执行 → 质量评估 → 失败重试的完整编排链。支持动态添加/移除子任务、人工编辑分解结果后再执行
2. **8 类专业 Agent 分工**：Developer（代码）、Browser（研究）、Document（文档）、Multi-Modal（创意）、Social Media（社交）、MCP（自定义工具）、Question Confirm（分流）、Task Summary（摘要），通过 NoteTakingToolkit 实现跨 Agent 协作
3. **@listen_toolkit 事件织入**：通过装饰器自动在 Tool 执行前后注入 UI 事件，前端实时展示每个 Agent 和 Toolkit 的活动状态
4. **Skill 多层配置体系**：项目级 → 用户全局 → 默认，支持按 Agent 类型限制 Skill 可见性
5. **Trigger 系统**：支持 Webhook、Slack、定时触发，将外部事件转化为 Agent 任务

### 值得借鉴的模式

| 模式 | 描述 |
|------|------|
| 队列驱动事件循环 | `step_solve()` 通过 `TaskLock.queue` 解耦所有状态变更，比 while-loop 更灵活 |
| 复杂度分流 | 简单问题直接回答，复杂任务才启动 Workforce，避免资源浪费 |
| ContextVar 工具执行 | `set_process_task()` 确保跨线程/异步的上下文传播 |
| Agent 间笔记协作 | NoteTakingToolkit + shared_files 约定，轻量级跨 Agent 信息共享 |
| 流式任务分解 | `on_stream_text`/`on_stream_batch` 回调实时推送分解进度 |

---

## 7.5 MVP 组件清单

基于以上分析，构建最小可运行版本需要以下组件：

| 组件 | 对应维度 | 核心文件 | 建议语言 | 语言理由 |
|------|----------|----------|----------|----------|
| 队列事件循环 | D2 | `chat_service.py:step_solve()` | Python | FastAPI 异步生态 |
| Workforce 编排 | D2/D7 | `workforce.py:Workforce` | Python | 依赖 CAMEL 框架 |
| Agent 工厂 | D2/D3 | `agent_model.py`, `factory/` | Python | CAMEL ChatAgent |
| Toolkit 分发 | D3 | `tools.py`, `toolkit/` | Python | FunctionTool 体系 |
| Prompt 组装 | D4 | `prompt.py`, `chat_service.py` | Python | 字符串模板 |
| SSE 流式通信 | D9 | `chat_controller.py` | Python | FastAPI StreamingResponse |
| Trigger 触发器 | D9/D11 | `trigger_controller.py`, `webhook_controller.py` | Python | Celery + Redis |
| Skill 配置 | D12 | `skill_toolkit.py` | Python | JSON 配置 |

---

## 8. 跨 Agent 对比

### vs aider / codex-cli / pi-agent / openclaw / nanoclaw

| 维度 | eigent | aider | codex-cli | pi-agent | openclaw | nanoclaw |
|------|--------|-------|-----------|----------|----------|----------|
| **定位** | 桌面多 Agent Workforce 平台 | 终端编码助手 | CLI 编码 agent | 模块化 agent 工具包 | 多通道 AI 助手平台 | 极简个人 AI 助手 |
| **语言** | TypeScript + Python | Python | Rust + TypeScript | TypeScript | TypeScript | TypeScript |
| **Agent Loop** | 队列事件循环 + Workforce 多 Agent 并行编排 | 三层嵌套（外层切换 + REPL + 反思） | tokio::select! 多路复用 + turn 循环 | 双层循环（steering + follow-up） | 内嵌 pi-agent + 编排层 | 双层：Host 轮询 + Container SDK |
| **多 Agent** | 8 类 Agent 并行（Workforce 编排） | 双模式（architect + coder） | 单 Agent | 单 Agent | 单 Agent + 子 Agent spawn | Agent Swarms（SDK Teams） |
| **Tool 系统** | 30+ Toolkit + MCP + Skill 三层体系 | 双轨制：用户命令 + LLM 文本格式 | 原生 function calling + 审批门 | 原生 tool calling + pluggable ops | 47 tool + 4 档 profile + policy | Claude SDK 内置 + MCP 自定义 |
| **框架依赖** | CAMEL-AI（重度） | 自研 | 自研 | 自研 | 内嵌 pi-agent | Claude Agent SDK（黑盒） |
| **安全模型** | JWT + 速率限制（无代码沙箱） | Git 集成（auto-commit + undo） | 三级审批 + 平台沙箱 + 网络代理 | 无内建沙箱 | Docker 沙箱 + Owner 信任分级 | Docker 容器隔离 + 外部 allowlist |
| **错误恢复** | Workforce retry + replan + 质量评估 | 反思循环 + 多级解析容错 | 可重试性分类 + 指数退避 | 多 provider overflow 检测 | Failover 分类器 + Auth 轮转 | 指数退避 + 游标回滚 |
| **通道** | Electron 桌面 + Webhook + Slack 触发 | 仅 CLI | 仅 CLI | CLI + Slack Bot | 13+ 消息平台 + Gateway RPC | WhatsApp + skill 扩展 |
| **记忆** | PostgreSQL + Redis + Qdrant | Git 集成 | 无明显持久化 | JSONL + 分支 | JSONL + SQLite 语义记忆 + 混合检索 | CLAUDE.md + SQLite session |
| **扩展性** | Skill 多层配置 + MCP 服务器管理 | 无正式扩展系统 | Hooks + MCP + Skills | 深度扩展（生命周期钩子） | Plugin SDK + 31 extension + 51 skills | Claude Code Skills（代码变换） |

### 总结

Eigent 的核心特点是 **基于 CAMEL-AI 的多 Agent Workforce 编排**，它是目前分析的 Agent 中唯一实现了真正并行多 Agent 协作的项目。相比 pi-agent 和 openclaw 的单 Agent 架构，Eigent 通过任务自动分解和角色化 Agent 分工，能处理更复杂的跨领域任务（如"调研一个主题 + 写代码 + 生成文档 + 发布社交媒体"）。代价是架构复杂度更高，对 CAMEL 框架有重度依赖。与 NanoClaw 相比，两者代表了"Agent 平台"的两个极端——Eigent 重量级（Electron + CAMEL-AI、30+ Toolkit），NanoClaw 极简（~3,900 行、代码即配置、SDK 黑盒）；Eigent 的 Workforce 通过 CAMEL 实现任务分解和角色化并行，NanoClaw 的 Agent Swarms 通过 Claude SDK Teams 实现。与 Aider/Codex CLI 等纯 coding agent 相比，Eigent 更接近"AI 操作系统"——其 Electron 桌面应用定位和 Trigger 系统将 AI 能力延伸到编码之外的文档、社交媒体、数据分析等领域。

---

## 9. 通道层与网关 _(平台维度)_

### 通道架构

Eigent 采用 **Electron 桌面 + 双 FastAPI 后端** 架构，前端通过 HTTP/SSE 与后端通信：

```
┌──────────────┐    HTTP POST /chat     ┌──────────────────┐
│  Electron    │ ───────────────────────→│ Backend (Agent)  │
│  React UI   │ ←───── SSE Stream ──────│ FastAPI :3001     │
│              │                        │ chat_controller   │
│  ChatBox     │    HTTP REST            │                  │
│  WorkFlow    │ ───────────────────────→│ Server (Data)    │
│  Terminal    │ ←──────────────────────│ FastAPI :8000     │
└──────────────┘                        └──────────────────┘
                                               ↑
                                         Webhook/Slack
                                         Trigger (外部)
```

### 支持的通道

| 通道 | 协议/集成方式 | 特点 |
|------|--------------|------|
| Electron 桌面 | HTTP + SSE | 主交互通道，实时流式响应 |
| Webhook | HTTP POST → trigger_controller | 外部系统触发任务执行 |
| Slack | Slack Events API → slack_controller | Slack 消息触发 Agent |
| 定时触发 | Celery Beat cron | 无用户触发的自主执行 |

### 消息标准化

前端发送 `Chat` 模型（包含 question、model 配置、attachments）→ 后端统一处理。SSE 响应使用 `sse_json(event_type, data)` 格式化，事件类型包括：
- `confirmed` — 任务确认
- `decompose_text` / `decompose_progress` — 任务分解进度
- `activate_agent` / `deactivate_agent` — Agent 激活/停用
- `activate_toolkit` / `deactivate_toolkit` — 工具激活/停用
- `task_state` — 子任务状态变更
- `end` — 任务完成
- `error` — 错误信息
- `wait_confirm` — 简单回答等待追问

### 多模态支持

- **文件附件**：通过 `attaches` 字段传递文件路径
- **图像**：ScreenshotToolkit 截图 + ImageGenerationToolkit (DALL-E)
- **音频**：AudioAnalysisToolkit 转文字
- **浏览器**：HybridBrowserToolkit 支持网页截图和交互

---

## 10. 记忆与持久化 _(平台维度)_

### 持久化架构

| 存储 | 用途 | 技术 |
|------|------|------|
| PostgreSQL | 用户、聊天历史、MCP 服务器、触发器 | SQLModel + Alembic 迁移 |
| Redis | 会话缓存、速率限制、Celery broker | fastapi-limiter |
| Qdrant | 向量检索（RAG） | RAGToolkit |
| 文件系统 | 工作目录文件、笔记、Skill 配置 | 本地文件 |

### 长期记忆

- **聊天历史**：通过 `server/app/controller/chat/` 持久化到 PostgreSQL，支持历史查看和分享
- **会话内记忆**：`TaskLock.conversation_history` 维护多轮对话上下文（内存中）
- **Agent 间共享**：NoteTakingToolkit 的 `create_note()`/`read_note()` 在同一任务的 Agent 间共享中间结果
- **RAG 检索**：RAGToolkit 支持基于向量的知识检索

### 状态恢复

- **Snapshot**：`workforce.save_snapshot()` 在任务分解后保存快照
- **Chat History**：持久化到 PostgreSQL 后可跨 session 恢复
- **无自动崩溃恢复**：当前 Workforce 执行中断后不支持自动恢复，需重新提交任务

---

## 11. 安全模型与自治 _(平台维度)_

### 信任分级

- **用户认证**：JWT token（`Auth.create_access_token()`），支持邮箱密码登录和 StackAuth SSO
- **API 速率限制**：Redis-backed `fastapi-limiter`，Webhook 限制 10 次/分钟
- **Trigger 配额**：每用户最多 25 个活跃触发器，每项目最多 5 个

### 沙箱策略

- **工作目录隔离**：每个任务在独立工作目录执行（`{working_directory}`）
- **路径逃逸检测**：`PathEscapesBaseError` 检查路径是否超出允许的基目录
- **环境变量隔离**：`sanitize_env_path()` 清理环境变量路径
- **无 Docker 沙箱**：当前版本不使用 Docker 隔离代码执行

### 自主调度

- **Celery Beat**：定时触发器通过 `TriggerScheduleService` 管理 cron 任务
- **Webhook 触发**：外部系统通过 webhook URL 触发任务执行
- **Slack 事件**：Slack 消息事件自动触发 Agent 处理

### 多 Agent 协作

- **Workforce 编排**：CAMEL BaseWorkforce 的任务通道（TaskChannel）实现 Agent 间任务分发
- **NoteTakingToolkit**：Agent 间通过共享笔记传递信息（`list_note()` → `read_note()` → `create_note()`）
- **shared_files 约定**：每个 Agent 创建文件后必须注册到 `shared_files` 笔记
- **Agent 间消息**：system prompt 中 `list_available_agents` 和 `send_message` 工具支持 Agent 间直接通信

---

## 12. 其他特色机制 _(平台维度)_

### 机制列表

| 机制 | 简述 | 关键代码 |
|------|------|----------|
| Skill 系统 | 用户自定义技能，多层配置 + 按 Agent 权限控制 | `toolkit/skill_toolkit.py` |
| MCP 服务器管理 | 安装/认证/管理 MCP 服务器，动态加载工具 | `server/controller/mcp/`, `backend/component/mcp_server.py` |
| Workflow 编辑器 | React Flow 可视化工作流编排 | `src/components/WorkFlow/` |
| Trigger 系统 | Webhook + Slack + 定时，外部事件驱动任务 | `server/controller/trigger/` |
| 浏览器代理工作台 | 内置浏览器 Agent UI，支持实时网页交互 | `src/components/BrowserAgentWorkspace/` |
| 终端模拟器 | xterm.js 内嵌终端 | `src/components/Terminal/` |
| Benchmark 框架 | Agent 性能评估 | `backend/benchmark/` |
| i18n 国际化 | 多语言支持 | `src/i18n/` |

### 详细分析

**Skill 系统**：Eigent 的 Skill 系统允许用户定义可复用的任务模板，Agent 在执行时通过 `list_skills()` → `load_skill()` 加载技能定义。配置层级为项目级（`.eigent/skills-config.json`）> 用户全局（`~/.eigent/<user_id>/skills-config.json`）> 默认。每个 Skill 可限制到特定 Agent 类型（如只允许 developer_agent 使用代码技能）。

**MCP 服务器管理**：Server 层提供 MCP 服务器的完整生命周期管理 — 从市场浏览、安装、OAuth 认证到使用。安装后的 MCP 工具自动注入到对应 Agent 的 Toolkit 列表中。`pre_instantiate_mcp_toolkit()` 在安装时预连接验证，确保认证信息持久化到 `~/.mcp-auth`。

**Trigger 系统**：支持三种触发方式：
1. **Webhook**：生成唯一 URL，外部系统 POST 即可触发任务
2. **Slack**：监听 Slack Events API，消息到达自动触发
3. **定时**：Celery Beat 管理 cron 任务
每个触发器关联项目和用户，执行记录持久化到 `TriggerExecution` 表。
