# Demo: eigent — agent-factory

## 目标

用最简代码复现 eigent 的 **Agent 工厂 + ListenChatAgent 事件织入**机制 — 8 类专业 Agent 的创建流程和 step/tool 执行时的 UI 事件注入。

## MVP 角色

**Agent 创建与执行** — 工厂函数按类型组装 Toolkit + System Prompt，ListenChatAgent 在 step/tool 执行前后注入 SSE 事件。对应 D2/D3。

## 原理

Eigent 的 Agent 创建分三层：

1. **Factory 层**（`factory/developer.py` 等）：按 Agent 类型收集对应的 Toolkit 列表，注册 ToolkitMessageIntegration
2. **agent_model()**：创建 CAMEL ModelFactory 模型实例，包装为 ListenChatAgent，发送 `create_agent` 事件到前端
3. **ListenChatAgent**：重写 `step()` 和 `_execute_tool()`，在前后注入 `activate_agent`/`deactivate_agent` 和 `activate_toolkit`/`deactivate_toolkit` 事件

事件织入的关键设计是 **@listen_toolkit 装饰器** — 已装饰的方法自带事件，ListenChatAgent 检查 `__listen_toolkit__` 标记避免重复发送。

## 运行

```bash
cd demos/eigent/agent-factory
export OPENAI_API_KEY="sk-..."
uv run --with litellm python main.py
```

## 文件结构

```
demos/eigent/agent-factory/
├── README.md           # 本文件
└── main.py             # AgentType/FunctionTool/ListenChatAgent/create_agent 工厂
```

## 关键代码解读

### ListenChatAgent.step() — 事件织入

```python
def step(self, message):
    self._emit("activate_agent", message=message)   # 1. 激活
    response = litellm.completion(...)               # 2. LLM 调用
    if choice.message.tool_calls:                    # 3. 工具执行
        result = self._execute_tool(name, args)
    self._emit("deactivate_agent", message=result)   # 4. 停用
```

### create_agent() — 工厂函数

```python
def create_agent(agent_type, on_event):
    system_prompt = AGENT_PROMPTS[agent_type]        # 按类型选 prompt
    tools = AGENT_TOOLKITS[agent_type]               # 按类型选 toolkit
    agent = ListenChatAgent(agent_name, system_prompt, tools, on_event)
    on_event(AgentEvent("create_agent", ...))         # 通知前端
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| Agent 类型 | 8 类（含 social_media, mcp） | 3 类核心（developer, browser, document） |
| Toolkit 数量 | 30+ 个 | 3 个模拟 |
| 模型创建 | CAMEL ModelFactory + 多平台支持 | litellm 直接调用 |
| @listen_toolkit | 装饰器自动织入事件 | 手动在 _execute_tool 中发送 |
| 流式响应 | _stream_chunks/_astream_chunks 包装 | 无流式 |

**保留的核心**：工厂模式创建 Agent、按类型分配 Toolkit/Prompt、step 和 tool 执行的事件织入。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/agent/agent_model.py`, `backend/app/agent/listen_chat_agent.py`, `backend/app/agent/factory/`
