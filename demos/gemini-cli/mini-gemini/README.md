# Mini Gemini — Agent Integration

## 目标

整合 Gemini CLI 的所有核心机制（6 个 MVP + 3 个进阶），构建最小可运行的完整 AI agent。

## 分层架构

```
┌─────────────────────────────────────────────┐
│           User Input/Output                 │
│        (stdin/stdout + Event Stream)        │
└────────────────────┬────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │  mini-gemini/main.py    │  ← 核心 agent loop
        │  (~250 行)              │
        └────┬──────────────┬─────┘
             │              │
    ┌────────▼────┐   ┌────▼──────────┐
    │ MVP 层      │   │ 进阶/优化层   │
    │ (6 modules) │   │ (3 modules)   │
    └─────────────┘   └───────────────┘

MVP 模块（import from siblings）:
  1. event-driven-loop     → AgentLoop
  2. tool-registry-system  → ToolRegistry
  3. mcp-tool-integration  → MCPClientManager
  4. prompt-assembly       → PromptAssembler
  5. session-replay        → AgentSession + EventHistory
  6. error-handling        → AgentErrorHandler

进阶模块（可选）:
  7. message-bus-confirmation → ApprovalBus
  8. sandbox-execution        → SandboxExecutor
  9. context-window-management → ContextWindowManager
```

## 运行

```bash
cd demos/gemini-cli/mini-gemini/
uv run --with google-generativeai,litellm,pydantic main.py
```

## 文件结构

```
mini-gemini/
├── README.md          # 本文件
└── main.py            # 最小完整 agent (~250 行)
```

## 关键设计

### 1. Agent 生命周期

```python
async def main():
    # 初始化各子系统
    tool_registry = ToolRegistry()        # from tool-registry-system
    mcp_manager = MCPClientManager()      # from mcp-tool-integration
    prompt_assembler = PromptAssembler()  # from prompt-assembly
    session = AgentSession()              # from session-replay
    error_handler = AgentErrorHandler()   # from error-handling
    
    # 处理用户输入
    while True:
        user_input = input("> ")
        
        # 驱动 agent loop
        async for event in agent_loop.run(user_input):
            process_event(event)
            
            if event.type == EventType.ToolCallRequest:
                # 权限确认（可选）
                if not await approval_bus.is_approved(event.tool):
                    continue
                
                # 沙箱执行（可选）
                result = await sandbox.execute(event.tool)
                
                # 错误处理
                if result.error:
                    recovery_action = error_handler.classify(result.error)
                    apply_recovery(recovery_action)
            
            elif event.type == EventType.ContextWindowWillOverflow:
                # 上下文清理
                context_manager.compress_history()
```

### 2. 模块导入策略

每个 MVP demo 都提供可复用的模块，mini-gemini 通过 `sys.path` 导入：

```python
import sys
sys.path.insert(0, '../event-driven-loop')
sys.path.insert(0, '../tool-registry-system')
# ...

from event_driven_loop import AgentLoop
from tool_registry import ToolRegistry
```

### 3. 事件处理管道

```
LLM Response Event (stream)
  ↓
Parse Tools from event
  ↓
[Optional] Request Approval (message-bus-confirmation)
  ↓
[Optional] Clone to Sandbox (sandbox-execution)
  ↓
Execute Tool
  ↓
Classify Error (if any)
  ↓
Add Result to Context
  ↓
[Optional] Check Overflow (context-window-management)
  ↓
Feed Back to LLM
```

## 与完整实现的差异

| 特性 | 完整实现 | Mini Gemini |
|------|---------|-----------|
| 代码行数 | ~5000+ 行（8 个包）| ~250 行 + imports |
| UI 框架 | Ink React TUI | stdin/stdout |
| 工具数 | 11 个内置 + MCP | 4 个演示工具 |
| 权限管理 | 完整的配置系统 | 内存 ApprovalBus（可选） |
| 沙箱 | Docker/Podman | 进程限制（可选） |
| 上下文 | 真实 token 计数 | 粗略估算 |
| 持久化 | 会话数据库 | 内存中 |

## 完整机制覆盖

### MVP 层（必需）

| D | 机制 | Demo | 集成方式 |
|----|------|------|----------|
| D2 | 事件驱动主循环 | event-driven-loop | `AgentLoop.run()` |
| D3 | 工具注册 + MCP | tool-registry-system + mcp-tool-integration | `ToolRegistry` + `MCPClientManager` |
| D4 | 提示工程 | prompt-assembly | `PromptAssembler.assemble()` |
| D5 | 会话恢复 | session-replay | `AgentSession.stream()` + `EventHistory` |
| D6 | 错误处理 | error-handling | `AgentErrorHandler.classify()` |

### 进阶层（可选）

| 机制 | Demo | 集成方式 |
|------|------|----------|
| 权限确认 | message-bus-confirmation | `approval_bus.request_approval()` |
| 沙箱隔离 | sandbox-execution | `sandbox_executor.execute()` |
| 上下文管理 | context-window-management | `context_manager.will_overflow()` |

## 相关文档

- 基于 commit: [`0c91985`](https://github.com/google-gemini/gemini-cli/tree/0c919857fa5770ad06bd5d67913249cd0f3c4f06)
- 核心源码: `packages/core/src/agent/`（所有模块）
- MVP 参考: [event-driven-loop](../event-driven-loop/), [tool-registry-system](../tool-registry-system/), [mcp-tool-integration](../mcp-tool-integration/), [prompt-assembly](../prompt-assembly/), [session-replay](../session-replay/), [error-handling](../error-handling/)
- 进阶参考: [message-bus-confirmation](../message-bus-confirmation/), [sandbox-execution](../sandbox-execution/), [context-window-management](../context-window-management/)
