# Demo: Codex CLI — Event Multiplex

## 目标

用最简代码复现 Codex CLI 的 tokio::select! 多通道事件调度机制。

## MVP 角色

事件多路复用是 agent 的"中枢神经"——同时监听 LLM 响应、用户输入、工具完成等多个事件源，哪个先到就先处理。Codex CLI 的特色是**双层架构**：外层 TUI 事件循环（4 通道 select!）+ 内层 turn 执行循环。

## 原理

### 外层：多路复用

```
tokio::select! 同时监听 4 个通道：
├─ app_event_rx      → 内部事件（tool 完成、compaction 结果）
├─ active_thread_rx  → LLM 响应流事件
├─ tui_events        → 用户键盘/鼠标输入
└─ thread_created_rx → 子线程创建通知
```

### 内层：Turn 循环

```
loop {
  1. 收集待处理输入
  2. 调用 LLM（流式）
  3. 执行 tool calls（审批 + 沙箱）
  4. 检查 token → 超限则 auto-compact
  5. needs_follow_up == false → break
}
```

## 运行

```bash
cd demos/codex-cli/event-multiplex
uv run python main.py
```

## 文件结构

```
demos/codex-cli/event-multiplex/
├── README.md        # 本文件
├── multiplex.py     # 可复用模块: EventMultiplexer + TurnLoop
└── main.py          # Demo 入口
```

## 语言选择说明

原实现使用 Rust（tokio::select! 宏 + mpsc channel），本 demo 使用 Python（asyncio.wait + asyncio.Queue）。Python 的 asyncio 提供了等价的异步多路复用能力，保持与其他 demo 的一致性。

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 语言 | Rust (tokio) | Python (asyncio) |
| 多路复用 | tokio::select! 宏 | asyncio.wait(FIRST_COMPLETED) |
| 通道 | tokio mpsc channel | asyncio.Queue |
| TUI | Ratatui 终端 UI | 省略 |
| 流式 LLM | SSE 增量解析 | Mock 同步返回 |
| Compaction | LLM 摘要压缩 | 简化裁剪 |

## 相关文档

- 分析文档: [docs/codex-cli.md](../../../docs/codex-cli.md)
- 原项目: https://github.com/openai/codex
- 基于 commit: `0a0caa9`
- 核心源码: `codex-rs/tui/src/app.rs`, `codex-rs/core/src/codex.rs`
