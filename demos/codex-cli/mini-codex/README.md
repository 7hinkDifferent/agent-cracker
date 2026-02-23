# mini-codex — 最小完整 Codex CLI Agent

串联 4 个 MVP 组件的最小完整 agent 实现。

> Based on commit: [`0a0caa9`](https://github.com/openai/codex/tree/0a0caa9df266ebc124d524ee6ad23ee6513fe501) (2026-02-23)

## 运行

```bash
uv run python main.py
```

## 组件串联

```
用户请求
  ↓
┌─ 1. Prompt Assembly ─────────────────┐
│  AssemblyConfig → assemble() → render()  │
│  7 层叠加: base → personality → policy   │
│           → mode → memory → custom → slash│
└──────────────────────────────────────────┘
  ↓ system prompt
┌─ 4. Event Multiplex (TurnLoop) ──────┐
│  while needs_follow_up:              │
│    ┌─ 2. Response Stream ──────────┐ │
│    │  SSE events → ResponseAssembler │ │
│    │  → FunctionCallAccumulator    │ │
│    │  → TurnResult (content+tools) │ │
│    └───────────────────────────────┘ │
│    ↓ tool_calls                      │
│    ┌─ 3. Tool Execution ───────────┐ │
│    │  ToolRouter.build_tool_call() │ │
│    │  → evaluate_approval()        │ │
│    │  → sandbox_wrap_command()     │ │
│    │  → execute (shell/patch/search)│ │
│    └───────────────────────────────┘ │
│    ↓ tool results → 下一轮          │
└──────────────────────────────────────┘
  ↓
完成
```

## 导入的模块

| 组件 | 模块路径 | 导入内容 |
|------|----------|----------|
| Prompt Assembly | `prompt-assembly/assembler.py` | `AssemblyConfig`, `assemble()`, `render()` |
| Response Stream | `response-stream/stream.py` | `ResponseAssembler`, `SSEEvent`, `approx_token_count()` |
| Tool Execution | `tool-execution/executor.py` | `ToolRouter`, `ApprovalMode`, `SandboxConfig` |
| Event Multiplex | `event-multiplex/multiplex.py` | `TurnLoop`, `TurnResult` |

## 核心源码

| 机制 | 原始文件 | Demo 模块 |
|------|----------|-----------|
| 7 层 prompt 组装 | `codex-rs/core/src/codex.rs` → `build_initial_context()` | `assembler.py` |
| SSE 流解析 | `codex-rs/core/src/stream.rs` | `stream.py` |
| Tool 路由 + 审批 | `codex-rs/core/src/tools/` + `codex-rs/core/src/exec_policy.rs` | `executor.py` |
| 事件多路复用 | `codex-rs/tui/src/app.rs` → `App::run()` | `multiplex.py` |

## 与原实现的差异

- **无实际 LLM 调用**: 使用 MockLlm 4 轮脚本（read → patch → verify → done）
- **SSE 是模拟生成**: `make_sse_response()` 构造 SSE 事件，由 `ResponseAssembler` 真实解析
- **沙箱是标记式**: `sandbox_wrap_command()` 标记 sandboxed=true，不实际调用 sandbox-exec
- **Tool 路由完整**: 审批策略（safe/banned 列表）和三级模式（suggest/auto-edit/full-auto）完整复现
