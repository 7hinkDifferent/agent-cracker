# Message Bus Confirmation

## 目标

复现 Gemini CLI 的权限确认机制（`MessageBus`），使工具执行前可进行交互式权限检查和灵活的策略管理。

## 原理

Gemini CLI 通过 **MessageBus** 实现工具执行的权限控制：

1. **权限策略 (ApprovalMode)**：
   - `AUTO` — 自动执行，无需确认
   - `INTERACTIVE` — 每次执行前交互确认
   - `DENY` — 拒绝所有执行请求

2. **确认流程**：
   ```
   Tool Invocation Request
      ↓
   Check ApprovalMode
      ├─→ AUTO: 直接执行
      ├─→ INTERACTIVE: 向用户询问 → 等待响应
      └─→ DENY: 返回错误
      ↓
   Execute Tool (Approved) / Reject (Denied)
      ↓
   Return Result / Error
   ```

3. **消息总线的角色**：
   - 路由权限请求至 UI 层（Ink 框架）
   - 等待用户输入（是/否/始终允许）
   - 缓存策略决策，减少后续重复询问

4. **关键区别于单纯的 Ask 工具**：
   - `ask-user` 是 LLM 可见的工具，用于通用用户交互
   - `MessageBus` 是基础设施层，阻止工具执行前的权限校验
   - 支持白名单/黑名单和工具级别的策略

## 运行

```bash
cd demos/gemini-cli/message-bus-confirmation/
uv run --with pydantic main.py
```

## 文件结构

```
message-bus-confirmation/
├── README.md          # 本文件
└── main.py            # 权限确认总线实现 (~350 行)
```

## 关键代码解读

### 1. 权限策略定义
```python
class ApprovalMode(Enum):
    """工具执行权限模式"""
    AUTO = "auto"              # 自动批准
    INTERACTIVE = "interactive" # 交互确认
    DENY = "deny"              # 拒绝执行
```

### 2. 消息总线核心
```python
class ApprovalMessage:
    """权限请求消息"""
    tool_name: str
    parameters: dict
    reason: str = "Tool execution requires approval"
    
class ConfirmationBus:
    """权限确认总线"""
    
    async def request_approval(self, message: ApprovalMessage) -> ApprovalDecision:
        """
        请求权限。根据策略决定：
        1. 检查工具是否在允许列表中
        2. 根据 ApprovalMode 决定是否需要交互
        3. 返回批准/拒绝决定
        """
```

### 3. 工具执行管道
```python
async def schedule_tool_execution(tool_request: ToolCallRequest) -> ToolResult:
    """
    执行工具，但先通过权限确认总线：
    1. 构建权限请求
    2. 等待确认
    3. 如果批准，执行工具；否则返回错误
    """
    message = ApprovalMessage(
        tool_name=tool_request.name,
        parameters=tool_request.input,
    )
    decision = await confirmation_bus.request_approval(message)
    
    if decision.approved:
        return await execute_tool(tool_request)
    else:
        return ToolResult.error(f"Tool execution denied: {decision.reason}")
```

## 与原实现的差异

| 特性 | 原实现 | Demo |
|------|--------|------|
| 工具执行 | Scheduler + 沙箱 | 内存模拟执行 |
| UI 交互 | Ink React 框架 | stdin/stdout 交互 |
| 权限存储 | 持久化策略配置 | 内存决策缓存 |
| 工具黑名单 | 支持正则表达式 | 简单字符串匹配 |
| 链式确认 | 支持（同一会话多次） | 支持 |

## 相关文档

- 基于 commit: [`0c91985`](https://github.com/google-gemini/gemini-cli/tree/0c919857fa5770ad06bd5d67913249cd0f3c4f06)
- 核心源码: `packages/core/src/agent/`，`packages/core/src/tools/`
- 相关维度: D3（工具系统）
- 配套 Demo: [tool-registry-system](../tool-registry-system/) (D3)
