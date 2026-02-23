# Demo: Codex CLI — Tool Execution

## 目标

用最简代码复现 Codex CLI 的 Tool 沙箱执行管线。

## MVP 角色

Tool 执行管线是 agent 的"手"——决定 LLM 生成的 tool call 如何被安全地执行。Codex CLI 的特色是**三层防护**：审批策略 → 沙箱包装 → 受控执行。

## 原理

### 执行管线

```
LLM 返回 tool calls
    │
    ▼
build_tool_call() — 分类 tool 类型
    │
    ├─ Shell 命令 ─→ ExecPolicy 审批 ─→ 沙箱包装 ─→ subprocess 执行
    ├─ apply_patch ─→ 审批检查 ─→ 解析 diff ─→ 应用补丁
    ├─ Search ─→ 免审批 ─→ ripgrep 执行
    └─ MCP Tool ─→ 委派给 MCP server
```

### 三级审批

| 模式 | Shell | File Edit | Search |
|------|-------|-----------|--------|
| Suggest | 需审批 | 需审批 | 放行 |
| Auto-Edit | 需审批（安全命令除外） | 放行 | 放行 |
| Full-Auto | 放行（禁止命令除外） | 放行 | 放行 |

## 运行

```bash
cd demos/codex-cli/tool-execution
uv run python main.py
```

## 文件结构

```
demos/codex-cli/tool-execution/
├── README.md       # 本文件
├── executor.py     # 可复用模块: ToolRouter + 审批 + 沙箱
└── main.py         # Demo 入口
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 语言 | Rust | Python |
| 沙箱 | Seatbelt (macOS) / Landlock (Linux) / Docker | 标记模拟 |
| 进程管理 | tokio::process + 信号处理 | subprocess.run |
| MCP | 完整 MCP 协议客户端 | 仅路由识别 |
| 审批 UI | TUI 交互确认 | 回调函数 |

## 相关文档

- 分析文档: [docs/codex-cli.md](../../../docs/codex-cli.md)
- 原项目: https://github.com/openai/codex
- 基于 commit: `0a0caa9`
- 核心源码: `codex-rs/core/src/tools/router.rs`, `codex-rs/exec/src/`
