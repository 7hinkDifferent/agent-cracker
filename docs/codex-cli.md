# codex-cli — Deep Dive Analysis

> Auto-generated from template on 2026-02-23
> Repo: https://github.com/openai/codex
> Analyzed at commit: [`0a0caa9`](https://github.com/openai/codex/tree/0a0caa9df266ebc124d524ee6ad23ee6513fe501) (2026-02-23)

## 1. Overview & Architecture

### 项目定位

Codex CLI 是 OpenAI 官方的**轻量级终端 Coding Agent**，用 Rust 实现核心引擎，TypeScript 封装 CLI 入口。它的核心设计哲学是**安全优先**——通过三级审批策略（Suggest / Auto-Edit / Full-Auto）和平台级沙箱（macOS Seatbelt / Linux Landlock）让用户在不同信任级别下使用 AI Agent。

### 技术栈

- **核心语言**: Rust（异步 Tokio 运行时）
- **CLI 入口**: TypeScript / Node.js（仅平台检测 + 二进制分发）
- **运行时**: Tokio + async/await
- **终端 UI**: Ratatui + crossterm
- **构建**: Cargo workspace + Bazel
- **协议**: 自定义 SQ/EQ（Submission Queue / Event Queue）模式

| 类别 | 关键依赖 |
|------|----------|
| 异步运行时 | tokio, async-channel |
| 序列化 | serde, serde_json |
| 终端 UI | ratatui, crossterm |
| 网络 | reqwest |
| MCP 协议 | rmcp |
| 安全 | seccompiler（Linux）, seatbelt（macOS） |
| 工具 | rand, chrono, glob |

### 核心架构图

```
┌──────────────────────────────────────────────────────────────┐
│                      用户入口层                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐              │
│  │ codex.js   │  │ exec       │  │ MCP Server │              │
│  │ (Node CLI  │  │ (Headless  │  │ (外部集成) │              │
│  │  → Rust)   │  │  非交互)   │  │            │              │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘              │
└────────┼───────────────┼───────────────┼─────────────���────────┘
         │               │               │
         ▼               ▼               ▼
┌──────────────────────────────────────────────────────────────┐
│              TUI / App (tui/src/app.rs)                       │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  tokio::select! 事件多路复用                          │     │
│  │  ├─ app_event_rx     (内部事件)                       │     │
│  │  ├─ active_thread_rx  (LLM 响应)                     │     │
│  │  ├─ tui_events       (用户输入)                       │     │
│  │  └─ thread_created_rx (子线程)                        │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              Core Engine (core/src/codex.rs)                  │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  run_turn() 主循环                                    │     │
│  │  ├─ 构建 prompt (base_instructions + context)         │     │
│  │  ├─ 调用 LLM (stream responses)                      │     │
│  │  ├─ 解析 tool calls → 审批 → 沙箱执行                  │     │
│  │  ├─ 结果反馈 → 继续循环                                │     │
│  │  └─ Auto-compact (token 超限时)                       │     │
│  └─────────────────────────────────────────────────────┘     │
│  ┌───────────┐ ┌────────────┐ ┌──────────┐ ┌───────────┐    │
│  │ExecPolicy │ │ Sandbox    │ │ Network  │ │ Compact   │    │
│  │(审批策略)  │ │(沙箱执行)   │ │ Proxy   │ │(上下文压缩)│    │
│  └───────────┘ └────────────┘ └──────────┘ └───────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 关键文件/目录

| 文件/目录 | 作用 |
|-----------|------|
| `codex-cli/bin/codex.js` | Node.js CLI 入口：平台检测、Rust 二进制分发 |
| `codex-rs/cli/src/main.rs` | Rust CLI 多工具入口：子命令路由（exec, review, login...） |
| `codex-rs/tui/src/app.rs` | TUI 主循环：Ratatui + tokio::select! 事件多路复用 |
| `codex-rs/core/src/codex.rs` | 核心引擎：run_turn() 主循环（~9000 行） |
| `codex-rs/core/src/exec.rs` | 命令执行：子进程 spawn + 输出捕获 |
| `codex-rs/core/src/exec_policy.rs` | 审批策略：AskForApproval + 规则引擎 + 危险命令检测 |
| `codex-rs/core/src/truncate.rs` | 输出截断：bytes/4 token 估算 + 首尾保留 |
| `codex-rs/core/src/compact.rs` | 上下文压缩：自动 compaction + LLM 摘要 |
| `codex-rs/core/src/seatbelt.rs` | macOS 沙箱：Seatbelt 策略生成 + sandbox-exec |
| `codex-rs/core/src/error.rs` | 错误分类：CodexErr + SandboxErr + 可重试性判断 |
| `codex-rs/core/src/tools/` | 工具系统：registry + router + sandboxing |
| `codex-rs/core/templates/` | Prompt 模板集：指令、人格、压缩、协作模式 |
| `codex-rs/network-proxy/` | 网络代理：HTTP/SOCKS5 + 域名策略 + SSRF 防护 |
| `codex-rs/protocol/src/protocol.rs` | 协议定义：Op/EventMsg（SQ/EQ 模式） |

---

## 2. Agent Loop（主循环机制）

### 循环流程

Codex CLI 采用**双层架构**：外层 TUI 事件循环（多路复用）+ 内层 turn 执行循环。

**外层：TUI 事件循环**（`tui/src/app.rs` — `App::run()`）

```
tokio::select! 多路复用 4 个通道：
├─ app_event_rx      → 内部事件（tool 完成、compaction 结果）
├─ active_thread_rx  → LLM 响应流事件
├─ tui_events        → 用户键盘/鼠标输入
└─ thread_created_rx → 子线程创建通知
```

**内层：Turn 执行循环**（`core/src/codex.rs` — `run_turn()`）

```
loop {
  1. 收集待处理的用户输入
  2. 记录消息 + 发射 turn item 事件
  3. 构建 sampling input（完整历史）
  4. 调用 LLM（流式响应）
     ├─ 解析 tool calls
     ├─ 审批检查（ExecPolicy）
     ├─ 沙箱执行（Seatbelt/Landlock）
     └─ 结果反馈到 context
  5. 检查 token 用量
     ├─ 超限 + 还有后续 → auto-compact → continue
     └─ 无后续 → 执行 after-agent hooks → break
}
```

### 终止条件

1. **Agent 完成**：LLM 返回 `needs_follow_up = false`（无 tool call 且无待处理内容）
2. **用户中断**：Ctrl+C → `TurnAborted`
3. **Token 超限**：触发 auto-compact 后继续，或超限无法压缩则退出
4. **致命错误**：API key 缺失、不可恢复的服务端错误

### 关键代码

```rust
// core/src/codex.rs — run_turn() 核心循环（简化版）
loop {
    // 1. 收集用户输入
    let pending_response_items = sess.get_pending_input().await;

    // 2. 构建 sampling input
    let sampling_request_input: Vec<ResponseItem> =
        sess.clone_history().await.for_prompt(/*...*/);

    // 3. 调用 LLM + 执行 tool calls
    match run_sampling_request(
        sess, turn_context, client_session,
        sampling_request_input, cancellation_token,
    ).await {
        Ok(result) => {
            let SamplingRequestResult { needs_follow_up, .. } = result;

            // 4. 检查 token 超限
            let total_usage = sess.get_total_token_usage().await;
            let limit = model_info.auto_compact_token_limit();
            if total_usage >= limit && needs_follow_up {
                run_auto_compact(&sess, &turn_context).await?;
                continue;  // 压缩后继续
            }

            // 5. Agent 完成
            if !needs_follow_up {
                sess.hooks().dispatch(HookPayload { /* after_agent */ }).await;
                break;
            }
        }
        Err(_) => { /* 错误处理 */ }
    }
}
```

---

## 3. Tool/Action 系统

### Tool 注册机制

Codex CLI 使用**协议驱动**的 tool 系统，通过 `Op`（提交）和 `EventMsg`（事件）定义 tool 调用流程。Tool 不是静态注册表，而是 LLM 原生 function calling 生成 tool calls，由 Router 分发到对应的 handler。

```rust
// core/src/tools/router.rs — tool call 构建
pub async fn build_tool_call(
    session: &Session,
    item: ResponseItem,
) -> Result<Option<ToolCall>, FunctionCallError> {
    match item {
        ResponseItem::FunctionCall { name, arguments, call_id, .. } => {
            // MCP tool → 委派给 MCP server
            if let Some((server, tool)) = session.parse_mcp_tool_name(&name).await {
                Ok(Some(ToolCall { payload: ToolPayload::Mcp { server, tool, raw_arguments: arguments } }))
            } else {
                // 标准 function call
                Ok(Some(ToolCall { payload: ToolPayload::Standard { /* ... */ } }))
            }
        }
        ResponseItem::LocalShellCall { action, .. } => {
            // Shell 命令
            Ok(Some(ToolCall { payload: ToolPayload::Shell { action } }))
        }
        _ => Ok(None),  // 不认识的 item → 跳过
    }
}
```

### Tool 列表

| Tool | 功能 | 审批要求 | 沙箱约束 |
|------|------|---------|----------|
| **Shell** | 执行 bash 命令（Agent 生成） | ExecPolicy 控制 | Seatbelt/Landlock |
| **apply_patch** | 精确文件修改（unified diff 格式） | Auto-Edit 以上免审批 | 写入限制 |
| **Search** | 文件搜索（rg 驱动） | 无需审批 | 只读 |
| **MCP Tools** | 外部 MCP 协议工具 | 上下文相关 | 取决于 MCP server |
| **Skills** | Python 自定义工具（~/.codex/skills/） | 取决于 skill | 沙箱执行 |
| **Web Search** | 网页搜索（可配置启用） | 无需审批 | API 调用 |
| **View Image** | 查看图片（多模态） | 无需审批 | 只读 |
| **Plan** | 任务规划工具 | 无需审批 | 无 I/O |

### Tool 调用流程

```
LLM 返回 tool calls（function_call / local_shell_call）
    │
    ▼
build_tool_call() — 分类 tool 类型
    │
    ├─ Shell 命令
    │   ├─ ExecPolicy 评估（trusted? dangerous? banned?）
    │   │   ├─ 已知安全 → Skip（跳过审批）
    │   │   ├─ 未知 → NeedsApproval → 发射 ExecApprovalRequest
    │   │   │   └─ 等待用户 → Approved / Denied / Modified
    │   │   └─ 禁止前缀 → Forbidden → 拒绝执行
    │   ├─ 沙箱包装（Seatbelt/Landlock/Docker）
    │   ├─ spawn 子进程，捕获 stdout/stderr
    │   └─ 发射 ExecCommandEnd（输出 + 退出码 + 耗时）
    │
    ├─ MCP Tool
    │   └─ 委派给 MCP Connection Manager → 调用外部 server
    │
    └─ apply_patch
        ├─ 解析 unified diff
        ├─ 审批检查（Suggest 模式需审批）
        └─ 应用补丁到文件
    │
    ▼
Tool 结果 → 加入 Session history → 下一轮 LLM 调用看到结果
```

---

## 4. Prompt 工程

### System Prompt 结构

Codex CLI 的 system prompt 由**多层模板动态组装**，核心基础指令存放在 `core/templates/` 下。

**基础指令**（`model_instructions/gpt-5.2-codex_instructions_template.md`）：

```markdown
You are Codex, a coding agent based on GPT-5.
{{ personality }}

# Working with the user
- GitHub-flavored Markdown 格式化
- 不用嵌套列表，保持扁平
- 文件引用用 inline code（可点击）
- 不用 emoji

# Presenting your work
- 平衡简洁与细节
- 用户看不到命令输出，需要转述关键信息
- 复杂变更先说结论，再说过程

# General
- 搜索优先用 rg（比 grep 快）
- apply_patch 做单文件编辑
- 不要 git reset --hard（除非用户明确要求）
- 非交互式 git 命令

# Frontend tasks
- 避免"AI slop"风格
- 大胆设计，不要默认紫色
```

### 动态 Prompt 组装

`build_initial_context()` 按顺序叠加多层指令：

| 层 | 来源 | 作用 |
|----|------|------|
| 1 | Base Instructions 模板 | 角色定义 + 格式规则 + 工具使用规范 |
| 2 | `{{ personality }}` 注入 | 人格模板（pragmatic / friendly） |
| 3 | DeveloperInstructions::from_policy() | 沙箱策略 + 审批策略 → 权限约束 |
| 4 | Collaboration Mode 模板 | 协作模式（default / plan / execute / pair_programming） |
| 5 | Memory Tool Instructions | 长期记忆管理（~/.codex/memories/） |
| 6 | Custom developer_instructions | 每次 turn 的自定义指令 |
| 7 | Custom Prompts（~/.codex/prompts/） | 用户自定义 slash 命令（Markdown + frontmatter） |

### Prompt 模板位置

| 目录 | 用途 |
|------|------|
| `core/templates/model_instructions/` | 模型专属基础指令 |
| `core/templates/personalities/` | 人格模板（pragmatic, friendly） |
| `core/templates/collaboration_mode/` | 协作模式（default, plan, execute, pair_programming） |
| `core/templates/compact/` | 压缩 prompt（checkpoint 摘要 + summary prefix） |
| `core/templates/memories/` | 长期记忆管理 prompt |
| `core/templates/review/` | Code review 专用 prompt |
| `core/templates/search_tool/` | 搜索工具描述 |

---

## 5. 上下文管理

### 上下文窗口策略

Codex CLI 采用 **bytes/4 token 近似 + 首尾保留截断 + LLM 压缩**的三层策略。

**Token 估算**：

```rust
// core/src/truncate.rs
const APPROX_BYTES_PER_TOKEN: usize = 4;

pub fn approx_token_count(text: &str) -> usize {
    (text.len() + 3) / 4  // 向上取整的 bytes/4
}
```

与 pi-agent 的 `chars/4` 启发式完全相同的思路——保守高估，不依赖特定 tokenizer。

### 文件/代码的 context 策略

Codex CLI **没有** Aider 那样的 RepoMap/AST 分析，而是完全依赖 tool-driven 探索：

1. **搜索优先**：指令要求用 `rg`（ripgrep）搜索文件和代码
2. **Tool 输出截断**：每个 tool 返回的输出有大小限制
3. **首尾保留**：截断时保留输出的头部和尾部，中间插入 `…N tokens truncated…`

```rust
// core/src/truncate.rs — 首尾保留截断
fn split_string(s: &str, left_budget: usize, right_budget: usize) -> (&str, &str) {
    // 在 UTF-8 字符边界上切割
    // 保留前 left_budget bytes + 后 right_budget bytes
    // 中间插入截断标记
}

fn truncate_with_byte_estimate(text: &str, budget: usize) -> String {
    let left_budget = budget / 2;
    let right_budget = budget - left_budget;
    let (prefix, suffix) = split_string(text, left_budget, right_budget);
    format!("{prefix}…{removed} tokens truncated…{suffix}")
}
```

### 对话历史管理

**Auto-Compaction 机制**（`core/src/compact.rs`）：

1. **触发条件**：`total_usage_tokens >= model_info.auto_compact_token_limit()`
2. **压缩 prompt**（`templates/compact/prompt.md`）：

```markdown
You are performing a CONTEXT CHECKPOINT COMPACTION.
Create a handoff summary for another LLM that will resume the task.

Include:
- Current progress and key decisions made
- Important context, constraints, or user preferences
- What remains to be done (clear next steps)
- Any critical data, examples, or references needed to continue
```

3. **压缩流程**：
   - 向后遍历历史消息，按 token 预算选择保留的消息
   - 被丢弃的消息 → 发给 LLM 生成摘要
   - 压缩后重新注入 initial context（权限指令等）
   - 用 `summary_prefix.md` 模板包装摘要，注入新对话

4. **Context Window 溢出恢复**：
   ```rust
   Err(CodexErr::ContextWindowExceeded) => {
       if turn_input_len > 1 {
           history.remove_first_item();  // 逐条移除最旧消息
           continue;
       }
       // 无法继续 → 提示用户开新线程
   }
   ```

---

## 6. 错误处理与恢复

### LLM 输出解析错误

Codex CLI 使用 LLM 原生 function calling，不依赖文本解析。Tool call 参数由 `build_tool_call()` 按类型分发：

```rust
// core/src/tools/router.rs — 优雅降级
match item {
    ResponseItem::FunctionCall { .. } => { /* MCP or standard */ }
    ResponseItem::LocalShellCall { .. } => { /* shell command */ }
    _ => Ok(None),  // 不认识的类型 → 静默跳过
}
```

Tool 执行失败不会终止 Agent，而是将错误封装为 `FunctionCallOutput` 返回给 LLM：

```rust
// 非致命错误 → 转为结构化响应，让 LLM 处理
Err(err) => Ok(Self::failure_response(call_id, err))
// 致命错误 → 向上传播
Err(FunctionCallError::Fatal(message)) => Err(...)
```

### Tool 执行失败

**三层安全门**：

| 层级 | 检查 | 失败处理 |
|------|------|---------|
| ExecPolicy | 命令是否被策略允许 | Forbidden → 拒绝执行，告知 LLM |
| 审批 | 用户是否同意执行 | Denied → 返回拒绝结果给 LLM |
| 沙箱 | 平台沙箱是否放行 | SandboxErr::Denied → 返回沙箱拒绝信息 |

**沙箱错误类型**：
```rust
pub enum SandboxErr {
    Denied { output, network_policy_decision },  // 沙箱拒绝（Seatbelt/Landlock）
    Timeout { output },                          // 命令超时
    Signal(i32),                                 // 被信号杀死
    LandlockRestrict,                            // Landlock 无法完全限制
}
```

### 重试机制

**指数退避 + 随机抖动**：

```rust
// core/src/util.rs
const INITIAL_DELAY_MS: u64 = 200;
const BACKOFF_FACTOR: f64 = 2.0;

pub fn backoff(attempt: u64) -> Duration {
    let exp = BACKOFF_FACTOR.powi(attempt.saturating_sub(1) as i32);
    let base = (INITIAL_DELAY_MS as f64 * exp) as u64;
    let jitter = rand::rng().random_range(0.9..1.1);
    Duration::from_millis((base as f64 * jitter) as u64)
}
// 200ms → 400ms → 800ms → 1600ms ...（±10% 抖动）
```

**错误可重试性分类**（`CodexErr::is_retryable()`）：

| 可重试 | 不可重试 |
|--------|---------|
| `Stream`（SSE 断连） | `TurnAborted`（用户中断） |
| `Timeout`（进程超时） | `ContextWindowExceeded` |
| `UnexpectedStatus`（HTTP 错误） | `QuotaExceeded`（配额用完） |
| `ConnectionFailed`（网络失败） | `InvalidRequest`（请求格式错误） |
| `InternalServerError`（5xx） | `Sandbox`（沙箱拒绝） |
| `ResponseStreamFailed` | `RefreshTokenFailed`（Auth 失败） |

---

## 7. 关键创新点

### 独特设计

#### 1. 三级审批策略（Suggest / Auto-Edit / Full-Auto）

Codex CLI 最核心的差异化设计。通过 `AskForApproval` 枚举 + `SandboxPolicy` 组合，实现**渐进式信任**：

| 模式 | 文件读取 | 文件写入 | Shell 执行 | 网络 |
|------|---------|---------|-----------|------|
| **Suggest** | 自由 | 需审批 | 需审批 | 关闭 |
| **Auto-Edit** | 自由 | 自动 | 需审批 | 关闭 |
| **Full-Auto** | 自由 | 自动 | 自动 | 关闭 |

Full-Auto 模式之所以"安全"，是因为底层有平台沙箱兜底——即使 Agent 完全自主，也只能在 `$CWD` + `$TMPDIR` 写入，网络完全隔离。

#### 2. 平台级沙箱（Defense-in-Depth）

```
用户意图（审批策略）
    ↓
执行策略规则（ExecPolicy 前缀匹配 + 危险命令检测）
    ↓
审批决策（AskForApproval + 缓存）
    ↓
网络策略（HTTP/SOCKS5 代理 + 域名白名单 + SSRF 防护）
    ↓
平台沙箱（Seatbelt read-only jail / Landlock / Windows Sandbox）
```

**macOS Seatbelt** 策略（`.sbpl` 格式）：
```seatbelt
(deny default)           ; 默认拒绝一切
(allow process-exec)     ; 允许执行进程
(allow process-fork)     ; 允许 fork
(allow file-write-data (require-all (path "/dev/null")))
; 精细控制每一项权限
```

**禁止前缀列表**（50+ 个解释器/提权命令）：
```rust
static BANNED_PREFIX_SUGGESTIONS: &[&[&str]] = &[
    &["python3"], &["python3", "-c"],
    &["bash"], &["bash", "-lc"],
    &["sudo"],
    &["node"], &["node", "-e"],
    &["perl"], &["perl", "-e"],
    // ... 50+ 个
];
```

#### 3. 网络代理与 SSRF 防护

独立的 `network-proxy` crate 提供 HTTP/SOCKS5 代理：
- **域名白名单/黑名单**：GlobSet 模式匹配
- **SSRF 防护**：`is_non_public_ip()` 检测内网地址（loopback、private、link-local、CGNAT）
- **策略层叠**：BaselinePolicy → ModeGuard → ProxyState → Decider
- **Unix Socket 控制**：可配置是否允许 Unix domain socket 通信

#### 4. 协作模式系统

通过 `collaboration_mode/` 模板实现模式切换：
- **Default**：正常执行模式，倾向行动而非提问
- **Plan**：规划模式，先制定方案再执行
- **Execute**：纯执行模式，不做额外规划
- **Pair Programming**：对话式编程

#### 5. 多模态支持

原生支持图片输入（截图、设计稿），通过 `view_image` tool 查看图片，`input_image` 类型传递给 LLM。

### 值得借鉴的模式

1. **渐进式信任**：三级审批 + 平台沙箱的组合，让"全自动"模式既安全又好用
2. **bytes/4 token 估算**：与 pi-agent 相同的思路，简单但跨 provider 通用
3. **首尾保留截断**：截断输出时保留头尾，比简单截断保留更多上下文
4. **错误可重试性分类**：`is_retryable()` 方法让重试逻辑清晰明确
5. **指数退避 + 抖动**：标准但实现简洁（±10% jitter）
6. **Tool 错误 → LLM 可见**：非致命错误封装为 tool output 返回给 LLM 自行处理
7. **禁止前缀列表**：硬编码 50+ 危险命令前缀，简单粗暴但有效

---

## 7.5 MVP 组件清单

基于以上分析，构建最小可运行版本需要以下组件：

| 组件 | 对应维度 | 核心文件 | 建议语言 | 语言理由 |
|------|----------|----------|----------|----------|
| 事件多路复用 (event-multiplex) | D2 | `codex-rs/core/src/codex.rs` (run_turn), `codex-rs/core/src/protocol.rs` | Rust | tokio select! 多通道并发是核心机制，async runtime 不可替代 |
| Tool 沙箱执行 (tool-execution) | D3 | `codex-rs/exec/src/lib.rs`, `codex-rs/exec/src/seatbelt.rs` | Rust | 平台 API 集成 (sandbox-exec) + 进程管理 |
| Prompt 组装 (prompt-assembly) | D4 | `codex-rs/core/src/prompt.rs`, `codex-rs/core/src/config_profile.rs` | Python | 模板拼接逻辑可用 Python 复现 |
| 流式响应解析 (response-stream) | D2/D6 | `codex-rs/core/src/stream.rs`, `codex-rs/core/src/turns.rs` | Python | SSE 解析和增量拼接可简化复现 |

**说明**: codex-cli 的核心是 Rust async runtime 驱动的事件循环，MVP 中前两个组件需要 Rust 才能体现其设计精髓。

---

## 8. 跨 Agent 对比

### vs Aider / Pi-agent / OpenClaw

| 维度 | codex-cli | aider | pi-agent | openclaw |
|------|-----------|-------|----------|----------|
| **定位** | CLI 编码 agent | 终端编码助手 | 模块化 agent 工具包 | 多通道 AI 助手平台 |
| **语言** | Rust + TypeScript | Python | TypeScript | TypeScript |
| **Agent Loop** | tokio::select! 多路复用 + turn 循环 | 三层嵌套（外层切换 + REPL + 反思） | 双层循环（steering + follow-up） | 内嵌 pi-agent + 编排层（model fallback） |
| **Tool 系统** | 原生 function calling + 协议驱动 + 审批门 | 双轨制：用户命令 + LLM 文本格式 | 原生 tool calling + pluggable ops | 47 tool + 4 档 profile + policy pipeline |
| **Context 策略** | bytes/4 估算 + 首尾保留截断 + auto-compact | tree-sitter AST + PageRank RepoMap | chars/4 估算 + 结构化摘要压缩 | pi-agent 摘要 + tool result 截断 + DM 限制 |
| **编辑方式** | apply_patch（unified diff） | 12+ 编辑格式多态切换 | edit tool（精确替换 + 模糊匹配） | 继承 pi-agent edit tool |
| **安全模型** | 三级审批 + 平台沙箱 + 网络代理 | Git 集成（自动 commit + undo） | 无内建沙箱 | Docker 沙箱 + Owner 信任分级 |
| **错误处理** | 可重试性分类 + 指数退避 | 反思循环 + 多级解析容错 | 多 provider overflow 检测 | Failover 分类器 + Auth 轮转 + session 修复 |
| **扩展性** | Hooks + MCP + Skills + Custom Prompts | 无正式扩展系统 | 深度扩展（生命周期钩子） | Plugin SDK + 31 extension + 51 skills |
| **多模态** | 支持图片输入 | 不支持 | 不支持 | 语音 + Canvas + 浏览器 + 图片 |
| **Session** | 无明显持久化 | Git 集成（auto-commit） | JSONL 持久化 + 分支 | JSONL + SQLite 语义记忆 + 混合检索 |
| **LLM 支持** | OpenAI 为主（可配置） | litellm 统一适配 | 原生多 provider SDK | 继承 pi-agent + auth profile 轮转 |
| **通道** | 仅 CLI | 仅 CLI | CLI + Slack Bot | 13+ 消息平台 + Gateway RPC |

### 总结

Codex CLI 是一个**安全优先、性能导向**的 AI Coding Agent。其核心优势在于两点：

1. **Defense-in-Depth 安全模型**：三级审批策略（Suggest/Auto-Edit/Full-Auto）+ 平台级沙箱（macOS Seatbelt / Linux Landlock）+ 网络代理（SSRF 防护），让用户可以放心使用 Full-Auto 模式。这是同类 Agent 中安全模型最完善的。

2. **Rust 原生性能**：核心引擎用 Rust 实现，tokio 异步运行时 + Ratatui TUI，在大规模代码库上的响应速度和资源占用优于 Python/TypeScript 实现。

与 Aider 相比，Codex CLI 更重**安全与执行控制**（沙箱、审批、网络策略），Aider 更重**代码理解智能**（RepoMap、多编辑格式、反思循环）。与 pi-agent 相比，Codex CLI 有硬件级沙箱和网络代理，pi-agent 有更灵活的环境抽象（Pluggable Ops）和实时交互（Steering Queue）。与 OpenClaw 相比，两者都重视安全隔离但方式不同——Codex CLI 用**平台级沙箱**（Seatbelt/Landlock，轻量、零配置），OpenClaw 用**Docker 容器沙箱**（重量级但隔离更彻底）；Codex CLI 专注 CLI 单通道高性能执行，OpenClaw 则扩展到 13+ 通道和语义记忆等平台能力。Codex CLI 适合需要高安全性和自主执行的场景，OpenClaw 适合将 AI 能力部署到多种通信平台。
