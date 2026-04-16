# hermes-agent — Deep Dive Analysis

> Auto-generated from template on 2026-04-15
> Repo: https://github.com/NousResearch/hermes-agent
> Analyzed at commit: [`722331a`](https://github.com/NousResearch/hermes-agent/tree/722331a57de9e18f134c896d733870b4a493dc84) (2026-04-15)

## 1. Overview & Architecture

### 项目定位

Hermes Agent 是一个 **平台型 autonomous agent**：它不是单纯的本地 coding CLI，而是把 **CLI、消息网关、ACP IDE 接入、cron 调度、持久记忆、skills、子 agent、MCP、浏览器/终端/代码执行后端** 统一到同一个 `AIAgent` 运行时中。它的目标不是“帮你改一两个文件”，而是成为一个可长期运行、跨入口持续工作的个人 AI 系统。

### 技术栈

- **主语言**: Python 3.11+
- **分发**: `pyproject.toml` + setuptools，CLI 脚本 `hermes` / `hermes-acp`
- **核心 LLM SDK**: `openai`, `anthropic`, `httpx`, `tenacity`
- **CLI/TUI**: `prompt_toolkit`, `rich`
- **消息平台**: `python-telegram-bot`, `discord.py`, `slack-bolt`, `aiohttp`, `mautrix`
- **数据与状态**: SQLite + FTS5（`hermes_state.py`）
- **Prompt/Skills**: Markdown context files、`SKILL.md` 技能系统、agentskills.io 兼容
- **多环境执行**: local / docker / ssh / singularity / modal / daytona
- **前端补充**: 根目录 `package.json` 仅用于浏览器自动化依赖（`agent-browser`, `@askjo/camofox-browser`）

### 核心架构图

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         入口层 / Entry Points                       │
│  hermes CLI   |   gateway/run.py   |   acp_adapter/   |   cron      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         AIAgent (run_agent.py)                      │
│  - run_conversation() 主循环                                        │
│  - 3 API modes: chat_completions / codex_responses / anthropic      │
│  - retries / fallback / interrupt / compression                     │
└───────────────┬───────────────────────┬─────────────────────────────┘
                │                       │
                ▼                       ▼
┌────────────────────────────┐  ┌─────────────────────────────────────┐
│ Prompt & Memory Layer      │  │ Tool Runtime                         │
│ prompt_builder.py          │  │ tools/registry.py                    │
│ MEMORY.md / USER.md        │  │ model_tools.py                       │
│ skills index               │  │ file / terminal / browser / MCP      │
│ context files              │  │ execute_code / delegate / cron / ... │
└───────────────┬────────────┘  └───────────────────┬─────────────────┘
                │                                   │
                ▼                                   ▼
┌────────────────────────────┐  ┌─────────────────────────────────────┐
│ Persistence                │  │ Platform Layer                       │
│ hermes_state.py            │  │ gateway/platforms/*                  │
│ SQLite + WAL + FTS5        │  │ SessionStore + build_session_key()   │
│ session lineage            │  │ ACP bridge + cron scheduler          │
└────────────────────────────┘  └─────────────────────────────────────┘
```

### 关键文件/目录

| 文件/目录 | 作用 |
|-----------|------|
| `run_agent.py` | `AIAgent` 核心主循环，负责 API 调用、tool loop、fallback、compression、persistence |
| `agent/prompt_builder.py` | system prompt 分层组装：identity / memory / skills / context files / platform hints |
| `model_tools.py` | tool schema 汇总、toolset 过滤、dispatch 入口 |
| `tools/registry.py` | 自注册工具中心；支持 builtin / MCP / plugin 动态发现 |
| `tools/terminal_tool.py` | 多后端终端执行（local/docker/ssh/modal/daytona/singularity） |
| `tools/memory_tool.py` | MEMORY.md / USER.md 持久记忆工具 |
| `tools/session_search_tool.py` | SQLite FTS5 + LLM summarization 的跨 session 检索 |
| `tools/delegate_tool.py` | 子 agent 委派与并行批处理 |
| `gateway/run.py` | 多消息平台网关主循环，负责授权、会话路由、命令分发 |
| `gateway/session.py` | 统一 session key 构造与网关 session store |
| `hermes_state.py` | SQLite 状态库：sessions / messages / FTS5 / lineage |
| `acp_adapter/` | VS Code / Zed / JetBrains 的 ACP 适配层 |
| `cron/` | 定时任务调度与 jobs.json 存储 |
| `skills/` / `optional-skills/` | 内置技能与可选技能生态 |
| `plugins/` | memory provider / context engine / CLI 扩展 |

---

## 2. Agent Loop（主循环机制）

### 循环流程

Hermes 的主循环在 `run_agent.py` 的 `AIAgent.run_conversation()`。整体是一个“**稳定系统 prompt + 多轮 tool loop + 异常恢复**”的大循环：

1. 初始化 turn 级状态（retry counters、iteration budget、stream callbacks）
2. 恢复或构建 cached system prompt
3. 预估 token，必要时做 preflight compression
4. 将消息转换为目标 provider 所需格式（OpenAI / Codex Responses / Anthropic Messages）
5. 发起可中断 API 请求
6. 解析回复：
   - 若有 `tool_calls`：校验 tool name / JSON args → 执行工具 → 把结果追加回历史 → 回到步骤 4
   - 若无 tool：把文本作为最终响应结束
7. 持久化 session、同步 memory provider、安排后续 memory/skill nudge

Hermes 和普通 coding agent 的区别在于：它把 **fallback provider、interrupt、tool parallelism、context compaction、gateway continuation、subagent budget** 都塞在这一个循环里。

### 终止条件

Hermes 会在以下情况下退出当前 turn：

- 模型返回无 `tool_calls` 的最终文本
- 触发 `max_iterations` / `IterationBudget`
- API 连续失败且 fallback 链耗尽
- 用户中断（CLI `Ctrl+C`、消息平台 `/stop` 或新消息打断）
- 输出被判定为持续无效（空响应、无效 tool 名、损坏 JSON 等多次恢复失败）

### 关键代码

```python
# run_agent.py
if self._cached_system_prompt is None:
    stored_prompt = None
    if conversation_history and self._session_db:
        session_row = self._session_db.get_session(self.session_id)
        if session_row:
            stored_prompt = session_row.get("system_prompt") or None

    if stored_prompt:
        self._cached_system_prompt = stored_prompt
    else:
        self._cached_system_prompt = self._build_system_prompt(system_message)
        if self._session_db:
            self._session_db.update_system_prompt(self.session_id, self._cached_system_prompt)
```

```python
# run_agent.py
if assistant_message.tool_calls:
    for tc in assistant_message.tool_calls:
        if tc.function.name not in self.valid_tool_names:
            repaired = self._repair_tool_call(tc.function.name)
            if repaired:
                tc.function.name = repaired

    assistant_message.tool_calls = self._cap_delegate_task_calls(
        assistant_message.tool_calls
    )
    assistant_message.tool_calls = self._deduplicate_tool_calls(
        assistant_message.tool_calls
    )

    messages.append(self._build_assistant_message(assistant_message, finish_reason))
    self._execute_tool_calls(assistant_message, messages, effective_task_id, api_call_count)
    continue
else:
    final_response = assistant_message.content or ""
```

```python
# run_agent.py
if self.compression_enabled and _compressor.should_compress(_real_tokens):
    self._safe_print("  ⟳ compacting context…")
    messages, active_system_prompt = self._compress_context(
        messages, system_message,
        approx_tokens=self.context_compressor.last_prompt_tokens,
        task_id=effective_task_id,
    )
```

---

## 3. Tool/Action 系统

### Tool 注册机制

Hermes 的工具系统是非常典型的“**自注册 + 统一注册表 + toolset 过滤**”架构。

1. `tools/*.py` 在模块顶层调用 `registry.register(...)`
2. `tools/registry.py` 用 AST 扫描哪些文件真的包含 `registry.register()`
3. `model_tools.py` 在 import 时做 builtin tool discovery，再继续发现 MCP tools 与 plugin tools
4. `get_tool_definitions()` 根据当前启用的 toolsets 过滤可见工具
5. 实际执行时统一走 `registry.dispatch()`；少数需要 agent 内部状态的工具（如 `memory` / `todo` / `session_search` / `delegate_task`）由 agent loop 先拦截

这比手写大字典更适合平台型 agent：builtin、plugin、MCP、不同入口（CLI / gateway / ACP / API）都能走同一套 schema/discovery 逻辑。

### Tool 列表

Hermes 官方架构文档把当前规模概括为 **47 个注册工具 / 19 个 toolsets**。按能力域可分为：

| Toolset / 类别 | 代表工具 | 功能 |
|------|------|----------|
| Web | `web_search`, `web_extract` | 搜索与网页提取 |
| Terminal | `terminal`, `process` | 命令执行、后台进程 |
| File | `read_file`, `write_file`, `patch`, `search_files` | 文件读写、补丁、内容搜索 |
| Browser | `browser_navigate`, `browser_click`, `browser_snapshot`, `browser_vision` 等 10 个 | 浏览器自动化与视觉网页操作 |
| Vision / Media | `vision_analyze`, `image_generate`, `text_to_speech` | 图像分析、图像生成、TTS |
| Planning | `todo`, `clarify` | 任务规划与澄清式交互 |
| Memory & Recall | `memory`, `session_search` | 持久记忆、跨会话回忆 |
| Automation | `cronjob`, `send_message` | 定时任务、跨平台消息发送 |
| Agent Orchestration | `execute_code`, `delegate_task`, `mixture_of_agents` | 代码执行沙箱、子 agent、MoA 推理 |
| Integration | `ha_*`, `mcp-*`, `rl_*` | Home Assistant、MCP、RL 训练环境 |
| Platform Presets | `hermes-cli`, `hermes-telegram`, `hermes-acp` 等 | 按入口封装默认工具集合 |

### Tool 调用流程

```text
LLM tool_call
  → run_agent.py 校验/修复 tool 名与 JSON 参数
  → agent-level tool? (todo/memory/session_search/delegate)
      是：直接在 agent 内处理
      否：进入 model_tools.handle_function_call()
  → registry.dispatch(name, args)
  → sync/async handler 执行
  → 返回 JSON 字符串
  → 追加为 role="tool" 消息
```

### 关键代码

```python
# tools/registry.py
def discover_builtin_tools(tools_dir: Optional[Path] = None) -> List[str]:
    tools_path = Path(tools_dir) if tools_dir is not None else Path(__file__).resolve().parent
    module_names = [
        f"tools.{path.stem}"
        for path in sorted(tools_path.glob("*.py"))
        if path.name not in {"__init__.py", "registry.py", "mcp_tool.py"}
        and _module_registers_tools(path)
    ]
    for mod_name in module_names:
        importlib.import_module(mod_name)
```

```python
# tools/registry.py
def register(self, name: str, toolset: str, schema: dict, handler: Callable, ...):
    with self._lock:
        existing = self._tools.get(name)
        if existing and existing.toolset != toolset:
            logger.error("Tool registration REJECTED: '%s' ...", name)
            return
        self._tools[name] = ToolEntry(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            ...
        )
```

```python
# tools/registry.py
def dispatch(self, name: str, args: dict, **kwargs) -> str:
    entry = self.get_entry(name)
    if not entry:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        if entry.is_async:
            from model_tools import _run_async
            return _run_async(entry.handler(args, **kwargs))
        return entry.handler(args, **kwargs)
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {type(e).__name__}: {e}"})
```

---

## 4. Prompt 工程

### System Prompt 结构

Hermes 的 prompt 工程核心不是“写一个很长的 system prompt”，而是 **把 stable prefix 和 ephemeral overlays 分开**。`_build_system_prompt()` 只负责构建可缓存部分，`ephemeral_system_prompt` 在 API 调用时再注入。

缓存态 system prompt 的主要层级是：

1. `SOUL.md`（若存在）或 `DEFAULT_AGENT_IDENTITY`
2. 工具感知指导（memory/session_search/skills 的行为约束）
3. model-specific 执行纪律（GPT/Codex / Gemini/Gemma 特判）
4. 用户自定义 `system_message`
5. frozen `MEMORY.md` / `USER.md`
6. 外部 memory provider block
7. skills index
8. context files（`.hermes.md` / `AGENTS.md` / `CLAUDE.md` / `.cursorrules` 优先级发现）
9. 时间戳 / session id / model / provider
10. platform hint（CLI、Telegram、cron、email 等）

### 动态 Prompt 组装

Hermes 的动态性体现在两层：

- **构建时动态**：根据当前 toolset、model family、cwd、skills、memory、platform 决定有哪些 section
- **调用时动态**：临时性的 `ephemeral_system_prompt`、gateway overlay、prefill message、Honcho recall 不写回 cached prompt

这样做的直接收益是：

- 最大化 Anthropic/OpenRouter 前缀缓存命中
- 避免 mid-session memory 写入把 system prompt 变脏
- gateway / ACP / CLI 能叠加各自上下文，而不破坏 session 级一致性

### Prompt 模板位置

| 文件 | 用途 |
|------|------|
| `agent/prompt_builder.py` | identity、skills、context files、platform hints |
| `run_agent.py::_build_system_prompt` | 统一拼装 cached system prompt |
| `tools/memory_tool.py` | MEMORY / USER snapshot 生成 |
| `skills/*/SKILL.md` | 技能正文 |
| `~/.hermes/SOUL.md` | persona / 身份 |
| 工作区 `.hermes.md` / `AGENTS.md` / `CLAUDE.md` | 项目上下文 |

### 关键代码

```python
# run_agent.py
if not self.skip_context_files:
    _context_cwd = os.getenv("TERMINAL_CWD") or None
    context_files_prompt = build_context_files_prompt(
        cwd=_context_cwd, skip_soul=_soul_loaded)
    if context_files_prompt:
        prompt_parts.append(context_files_prompt)

platform_key = (self.platform or "").lower().strip()
if platform_key in PLATFORM_HINTS:
    prompt_parts.append(PLATFORM_HINTS[platform_key])
```

```python
# agent/prompt_builder.py
def build_context_files_prompt(cwd: Optional[str] = None, skip_soul: bool = False) -> str:
    project_context = (
        _load_hermes_md(cwd_path)
        or _load_agents_md(cwd_path)
        or _load_claude_md(cwd_path)
        or _load_cursorrules(cwd_path)
    )
    if project_context:
        sections.append(project_context)
    if not skip_soul:
        soul_content = load_soul_md()
        if soul_content:
            sections.append(soul_content)
```

---

## 5. 上下文管理

### 上下文窗口策略

Hermes 的上下文管理分成三层：

1. **会话内压缩**：`ContextCompressor` 默认在上下文达到阈值（默认 50%）时做结构化摘要
2. **gateway hygiene safety net**：消息网关在 85% 处做更保守的预压缩，避免平台 session 在 agent 进入前就爆 context
3. **外部可插拔 context engine**：`context.engine` 可切换为 plugin，例如 lossless context management

压缩流程不是简单截断，而是：

- 清理旧 tool 输出
- 保护前几条消息与最近 tail
- 对中间区段生成结构化 summary
- 保持 tool_call / tool_result 成对完整
- 压缩后创建 session lineage（新 session 继承旧 session）

### 文件/代码的 context 策略

Hermes 不像 aider 那样依赖 repo map，而是走“**工具按需读取 + context files 指令 + subdirectory hints**”路线：

- 项目根的 `.hermes.md` / `AGENTS.md` / `.cursorrules` 进入 system prompt
- 具体代码内容通过 `read_file` / `search_files` / `terminal` 按需拉取
- 子目录提示由 `agent/subdirectory_hints.py` 渐进发现
- `execute_code` / `delegate_task` 可把机械流程或子问题移出主上下文，降低主回路 token 压力

### 对话历史管理

Hermes 的历史管理同时包含：

- **SQLite message history**：所有 turn 写入 `state.db`
- **session lineage**：compression 或 delegation 会产生 parent/child session 关系
- **session_search**：用 FTS5 找旧对话，再用辅助模型总结后注入当前 turn
- **frozen memory snapshot**：重要稳定事实不依赖历史回放，而是直接放入 system prompt

### 关键代码

```python
# tools/session_search_tool.py
raw_results = db.search_messages(
    query=query,
    role_filter=role_list,
    exclude_sources=list(_HIDDEN_SESSION_SOURCES),
    limit=50,
    offset=0,
)

messages = db.get_messages_as_conversation(session_id)
conversation_text = _format_conversation(messages)
conversation_text = _truncate_around_matches(conversation_text, query)
```

```python
# tools/session_search_tool.py
response = await async_call_llm(
    task="session_search",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    temperature=0.1,
    max_tokens=MAX_SUMMARY_TOKENS,
)
```

---

## 6. 错误处理与恢复

### LLM 输出解析错误

Hermes 对模型输出的容错做得非常重，典型包括：

- **无效 tool 名**：先尝试 `_repair_tool_call()` 自动修复，再把“可用工具列表”作为 tool error 发回模型自纠
- **损坏 JSON arguments**：先重试；如果仍失败，则把错误包装成 tool result，让模型下一轮自恢复
- **空响应 / 只返回 `<think>`**：尝试 partial stream recovery、prior-turn content fallback、post-tool empty nudge
- **finish_reason=length**：继续生成或触发压缩后重试
- **不同 API mode 的响应格式异常**：分别检查 `choices` / `output` / `content` 结构

### Tool 执行失败

- 注册表 dispatch 层捕获所有 handler 异常并返回 JSON 错误字符串
- `check_fn` 失败的工具直接不暴露给模型，减少 hallucination
- `terminal` 工具有危险命令检测与审批回调
- `delegate_task` 有深度限制、并发上限、blocked toolsets，避免子 agent 失控
- tool batch 在只读场景支持并行执行；互斥或 path-overlap 时回退到顺序执行

### 重试机制

Hermes 的恢复策略是多层的：

1. **本 provider 内重试**：`jittered_backoff` + streaming/non-streaming fallback
2. **fallback provider/model**：`fallback_providers` / `fallback_model` 链式切换
3. **credential pool**：同 provider 多 key 轮换
4. **context compression**：context 太大时先压缩再继续
5. **interrupt-safe backoff**：长时间等待仍保持可中断

### 关键代码

```python
# run_agent.py
if invalid_tool_calls:
    self._invalid_tool_retries += 1
    available = ", ".join(sorted(self.valid_tool_names))
    messages.append(assistant_msg)
    for tc in assistant_message.tool_calls:
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": f"Tool '{tc.function.name}' does not exist. Available tools: {available}",
        })
    continue
```

```python
# tools/registry.py
if entry.is_async:
    from model_tools import _run_async
    return _run_async(entry.handler(args, **kwargs))
return entry.handler(args, **kwargs)
```

```python
# tools/approval.py
DANGEROUS_PATTERNS = [
    (r'\brm\s+-[^\s]*r', "recursive delete"),
    (r'\bDROP\s+(TABLE|DATABASE)\b', "SQL DROP"),
    (r'\b(curl|wget)\b.*\|\s*(ba)?sh\b', "pipe remote content to shell"),
    (r'\bgit\s+reset\s+--hard\b', "git reset --hard (destroys uncommitted changes)"),
]
```

---

## 7. 关键创新点

### 独特设计

1. **稳定 prompt / 临时 overlay 分离**
   - cached system prompt 与 `ephemeral_system_prompt` 分开，直接服务 prefix caching
2. **memory + session_search + skills 三层长期知识闭环**
   - memory 存稳定事实
   - session_search 回忆细节
   - skills 沉淀可执行经验
3. **单一 AIAgent 服务多入口**
   - CLI、gateway、ACP、cron 都复用同一个 agent runtime
4. **工具系统天然平台化**
   - 自注册 registry + toolset + MCP/plugin，使 Hermes 更像 agent OS 而不是单个 agent 脚本
5. **terminal backend 抽象非常完整**
   - local / docker / ssh / singularity / modal / daytona 统一暴露给模型

### 值得借鉴的模式

- **Prompt stability**：需要长期会话和 Anthropic caching 的 agent 都值得借鉴
- **Session lineage**：压缩不是“丢历史”，而是“分叉 session + FTS5 可回溯”
- **Agent-level tools**：`memory` / `todo` / `session_search` / `delegate_task` 不强行塞进通用 dispatch，可减少实现耦合
- **Dangerous command approval**：把终端审批当成平台级安全模型，而不是工具内部临时补丁
- **Subagent fresh context**：子 agent 只接收明确 goal/context，防止父上下文污染

---

## 7.5 MVP 组件清单

基于以上分析，构建最小可运行版本需要以下组件：

| 组件 | 对应维度 | 核心文件 | 建议语言 | 语言理由 |
|------|----------|----------|----------|----------|
| 主循环 | D2 | `run_agent.py` | Python | 原仓库主循环、provider 适配、异常恢复都在 Python 中实现，复现无需原生特性 |
| Tool 注册与分发 | D3 | `tools/registry.py`, `model_tools.py`, `toolsets.py` | Python | 自注册与 AST discovery 机制直接用 Python 最容易还原 |
| Prompt 组装 | D4 | `agent/prompt_builder.py`, `run_agent.py::_build_system_prompt` | Python | 主要是 markdown/context 处理与条件拼装 |
| LLM 调用与响应规范化 | D2/D6 | `run_agent.py`, `agent/anthropic_adapter.py` | Python | 三种 API mode 与 fallback 逻辑都基于 Python SDK |
| 文件/终端执行 | D3/D11 | `tools/file_tools.py`, `tools/terminal_tool.py`, `tools/approval.py` | Python | 沙箱、审批、后端切换都可用 Python 进程模型复现 |
| 通道路由 | D9 | `gateway/run.py`, `gateway/session.py`, `gateway/platforms/base.py` | Python | 多平台 `MessageEvent` 标准化与 session key 构建不依赖其他语言 |
| 记忆检索 | D10 | `tools/memory_tool.py`, `tools/session_search_tool.py`, `hermes_state.py` | Python | SQLite + FTS5 + 文件持久化在 Python 中即可完成 |
| 安全沙箱 | D11 | `tools/code_execution_tool.py`, `tools/terminal_tool.py`, `tools/approval.py` | Python | execute_code RPC 与后端抽象主要是 Python orchestration，而非底层 runtime 特性 |

---

## 8. 跨 Agent 对比

### vs 其他 agent

| 维度 | hermes-agent | 对比 Agent |
|------|----------------|------------|
| Agent Loop | 一个 `AIAgent` 统一服务 CLI / gateway / ACP / cron，内建 fallback、compression、interrupt、subagent budget | `pi-agent` 更像 agent harness；`gemini-cli` 更偏 CLI 会话与事件流 |
| Tool 系统 | AST discovery + self-registering registry + toolsets + MCP/plugin 混合接入 | `openclaw` 偏预定义 tool catalog/profile；`nanoclaw` 更强调容器/任务编排 |
| Context 策略 | 压缩 + frozen memory + SQLite FTS5 session_search + skills progressive disclosure | `aider` 强在 repo map；`gemini-cli` 强在超大上下文/JIT 文件读取；Hermes 更偏“长期记忆平台” |
| 错误处理 | 无效 tool/JSON 自修复、fallback providers、credential pool、dangerous command approval | `pi-agent` 有统一 provider/tool 架构，但 Hermes 在 gateway/cron/approval 上更完整 |
| 平台能力 | 原生消息网关、ACP、cron、跨平台 delivery、pairing/allowlist | `openclaw` 同样是平台型，但 Hermes 以 Python 单体统一实现，个人 agent / self-hosted 气质更强 |

### 总结

Hermes 与本仓库已分析的 agent 相比，最像 **“个人 AI 平台版的 pi-agent”**：它保留了 coding agent 需要的 file/terminal/tool loop，又进一步吸收了 OpenClaw 式的平台能力（网关、cron、多入口、跨 session 记忆）。和 `openclaw` 相比，Hermes 的核心差异在于 **Python 单仓统一实现 + memory/session_search/skills 闭环更强**；和 `gemini-cli` 相比，Hermes 更偏长期运行、多入口 agent，而不是单次 coding CLI。

### vs codex-cli

`codex-cli` 更像一个**高性能、强安全边界的单机 CLI coding agent**：OS 级沙箱、审批门和 Rust 运行时是它的核心护城河。`hermes-agent` 则把同类 coding 能力扩展成**平台运行时**，把 gateway、ACP、cron、memory、skills 与多终端后端纳入一个统一的 `AIAgent` 生命周期中。

因此，两者并不是简单的功能多寡差别，而是边界不同：codex-cli 优先解决“在本地终端里安全而高效地完成编码任务”，hermes-agent 优先解决“让一个个人 agent 在多个入口和长期会话中持续工作”。

### vs eigent

Eigent 和 `hermes-agent` 都超出了纯 coding agent 范畴，但侧重点不同：Eigent 强在 **CAMEL Workforce 驱动的多 Agent 并行协作**，适合图形化桌面工作台与团队式任务分解；hermes-agent 强在 **单核心 agent 的长期运行能力**，用 gateway、ACP、cron、memory 与 skills 把一个个人 assistant 铺到更多入口。

换句话说，Eigent 更像“多角色 AI 团队协调器”，hermes-agent 更像“有长期记忆和自治能力的个人 AI 平台”。前者在并行多 Agent 编排更强，后者在跨入口持续会话与 self-hosted 日常使用上更成熟。

---

## 9. 通道层与网关 _(平台维度 · 可选)_

### 通道架构

Hermes 的平台层围绕 `gateway/run.py` 的 `GatewayRunner` 展开。各平台 adapter 把外部事件规范化成 `MessageEvent`，交给 `_handle_message()`；之后由 `SessionStore` 用 `build_session_key()` 决定会话边界，再创建对应 `AIAgent` 继续处理。

```text
Platform adapter.on_message()
  → MessageEvent
  → GatewayRunner._handle_message()
  → 授权检查 / slash command / running-agent guard
  → SessionStore + build_session_key()
  → AIAgent.run_conversation()
  → DeliveryRouter / adapter.send()
```

### 支持的通道

| 通道 | 协议/集成方式 | 特点 |
|------|--------------|------|
| CLI | `hermes` 本地 TUI | 最完整的交互与本地审批 |
| ACP | stdio JSON-RPC (`acp_adapter/`) | VS Code / Zed / JetBrains 内编辑器接入 |
| Telegram / Discord / Slack / Signal / WhatsApp | Bot API / WebSocket / bridge | 长期会话、跨设备对话 |
| Email / SMS | IMAP/SMTP / Twilio 等 | 低频通知与异步交付 |
| Matrix / Mattermost | 社群协作平台 | 群聊 / 房间内共享 session |
| DingTalk / Feishu / WeCom / Weixin / QQBot | 企业/国内消息平台适配 | 平台扩展面广 |
| BlueBubbles | iMessage bridge | 苹果生态接入 |
| Webhook / API Server / Home Assistant | Webhook / REST / HA integration | 系统事件触发与自动化 |

### 消息标准化

Hermes 用 `build_session_key()` 统一编码 `platform/chat_type/chat_id/thread_id/user_id`，既支持 DM 级隔离，也支持 thread 共享 session。这个设计保证：

- Telegram 论坛话题、Discord thread、Slack thread 能映射到稳定 session
- 群聊可按 user 隔离或按线程共享
- gateway 层不会把“渠道差异”泄露到 agent loop 内部

### 多模态支持

- 浏览器工具支持视觉截图与 DOM 操作
- `vision_analyze`、`image_generate`、`text_to_speech` 提供图像/语音能力
- messaging 平台的 `PLATFORM_HINTS` 会约束 markdown、媒体发送格式与 voice memo 行为
- ACP 把 Hermes 的工具调用与状态事件桥接给 IDE 客户端

### 关键代码

```python
# gateway/session.py
def build_session_key(source: SessionSource, group_sessions_per_user: bool = True, ...):
    if source.chat_type == "dm":
        if source.chat_id:
            if source.thread_id:
                return f"agent:main:{platform}:dm:{source.chat_id}:{source.thread_id}"
            return f"agent:main:{platform}:dm:{source.chat_id}"
    ...
    return ":".join(key_parts)
```

---

## 10. 记忆与持久化 _(平台维度 · 可选)_

### 持久化架构

Hermes 的持久化是“双层”：

1. **结构化 session storage**：`~/.hermes/state.db`
   - `sessions`
   - `messages`
   - `messages_fts`
   - `schema_version`
2. **轻量长期记忆**：`~/.hermes/memories/MEMORY.md` + `USER.md`

前者负责完整可检索历史，后者负责少量高价值稳定事实。

### 长期记忆

Hermes 的长期记忆不是单一向量库，而是组合策略：

- **MEMORY.md / USER.md**：有限容量、人工/agent 筛选后的稳定事实
- **session_search**：SQLite FTS5 查到历史消息，再用辅助模型总结相关 session
- **external memory providers**：可额外挂接 Honcho、Mem0、Hindsight、Supermemory 等插件，但 builtin memory 始终存在

这种设计的优点是：

- 高频稳定事实走 prompt 注入，零检索延迟
- 低频细节走 session_search，避免 memory 爆炸
- 更深层 user modeling 再交给插件扩展

### 状态恢复

- context compression 会生成新的 child session，并通过 `parent_session_id` 形成 lineage
- gateway 重新建 `AIAgent` 时会重用 SQLite 中保存的 `system_prompt`，避免 session continuation 破坏缓存
- session_search 会把 delegation/compression 产生的 child session 向上解析到 parent，减少碎片化回忆

### 关键代码

```python
# hermes_state.py
CREATE TABLE IF NOT EXISTS sessions (... parent_session_id TEXT ...);
CREATE TABLE IF NOT EXISTS messages (... tool_calls TEXT, reasoning TEXT ...);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content=messages,
    content_rowid=id
);
```

```python
# hermes_state.py
self._conn.execute("PRAGMA journal_mode=WAL")
self._conn.execute("PRAGMA foreign_keys=ON")
```

```python
# tools/memory_tool.py
registry.register(
    name="memory",
    toolset="memory",
    schema=MEMORY_SCHEMA,
    handler=lambda args, **kw: memory_tool(...),
    check_fn=check_memory_requirements,
    emoji="🧠",
)
```

---

## 11. 安全模型与自治 _(平台维度 · 可选)_

### 信任分级

Hermes 在 gateway 层做了明确的授权边界：

1. per-platform allow-all flag
2. platform/global allowlist
3. DM pairing approved list
4. global allow-all
5. 默认 deny

即便 agent runtime 自身能力很强，外部入口仍然先过授权门槛。这使 Hermes 更像“可对外暴露的 agent 服务”，而不是单机 CLI。

### 沙箱策略

Hermes 有两类安全执行策略：

- **terminal backend 隔离**：local / docker / ssh / singularity / modal / daytona
- **execute_code sandbox**：在受控子环境里执行 Python 脚本，并通过 RPC 暴露受限工具集

同时，`tools/approval.py` 用大量危险命令模式（删除、格式化磁盘、改 `/etc/`、kill 自身 gateway、force push 等）在执行前触发审批。

### 自主调度

`cron/` 是 Hermes 平台化最明显的证据之一：

- `jobs.json` 保存任务
- scheduler 周期 tick
- 每个 cron job 运行在 fresh session 内
- 可附加 skills 与预执行脚本
- 结果可投递回任意平台

这意味着 Hermes 不需要用户在线，也能做“每天汇报”“定时检查”“夜间任务”等自治工作。

### 多 Agent 协作

`delegate_task` 支持：

- 单任务 child agent
- 最多 3 个并行子 agent
- 深度上限 2
- 子 agent fresh context + 独立终端 session
- 禁止 `delegate_task`/`clarify`/`memory`/`send_message`/`execute_code` 等高风险递归能力

### 关键代码

```python
# gateway/run.py
if platform_allow_all_var and os.getenv(platform_allow_all_var, "").lower() in ("true", "1", "yes"):
    return True
if self.pairing_store.is_approved(platform_name, user_id):
    return True
...
return bool(check_ids & allowed_ids)
```

```python
# tools/delegate_tool.py
if depth >= MAX_DEPTH:
    return json.dumps({
        "error": (
            f"Delegation depth limit reached ({MAX_DEPTH}). "
            "Subagents cannot spawn further subagents."
        )
    })
```

---

## 12. 其他特色机制 _(平台维度 · 可选)_

### 机制列表

| 机制 | 简述 | 关键代码 |
|------|------|----------|
| ACP bridge | 把同步 `AIAgent` 封装成异步 JSON-RPC stdio server，供 VS Code/Zed/JetBrains 使用 | `acp_adapter/entry.py`, `acp_adapter/server.py`, `acp_adapter/session.py` |
| Skills progressive disclosure | 技能先列索引，再按需加载正文/引用文件；兼容 agentskills.io | `agent/skill_utils.py`, `tools/skills_tool.py`, `tools/skill_manager_tool.py` |
| Plugin + Context Engine | 支持 memory provider、context engine、CLI/plugin 扩展 | `plugins/`, `agent/context_engine.py`, `hermes_cli/plugins.py` |
| Profile isolation | `HERMES_HOME` / profile 隔离 config、memory、session、gateway PID | `hermes_constants.py`, `gateway/status.py` |

### 详细分析

#### ACP bridge

Hermes 不是简单地暴露一个 HTTP API，而是专门做了 ACP 适配层：`acp_adapter/entry.py` 负责加载环境并启动 stdio JSON-RPC server，`HermesACPAgent` 把 `AIAgent` 的 callback（thinking、tool progress、step）转成 ACP `session_update` 事件。这个机制让 Hermes 直接进入编辑器生态，而不必重写一套 IDE 专用 agent 核心。

#### Skills progressive disclosure

Hermes 的技能系统不是一次性把所有知识塞进 prompt，而是：

- Level 0：`skills_list()` 暴露索引
- Level 1：`skill_view(name)` 读取完整技能
- Level 2：按需读 skill 附带 references / scripts

这比把全部 workflow 文档硬塞进 system prompt 更节省 token，也更适合 agent 自主沉淀经验。

#### Plugin + Context Engine

Hermes 把“长期记忆”和“上下文压缩”都做成插件扩展点：

- memory provider：外挂 Honcho/Mem0 等更强记忆后端
- context engine：可替换默认 lossy summarizer

这种设计让 Hermes 不是一个封闭产品，而是一个可继续演化的 agent 平台。

#### Profile isolation

Hermes 支持 `hermes -p <name>` 级别的 profile 隔离。每个 profile 拥有自己的：

- `HERMES_HOME`
- config
- memories
- sessions
- gateway pid / token locks

对于需要多身份、多 bot、多环境并存的个人 agent 平台，这点很实用，也明显超出普通 coding agent 的范围。
