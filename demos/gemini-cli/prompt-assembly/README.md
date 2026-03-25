# Prompt Assembly

复现 Gemini CLI 的动态 Prompt 组装机制。

## 原理

Gemini CLI 的 system prompt 由多个动态部分组成：

```
Base System Prompt
  ↓
+ Tool Definitions (FunctionDeclaration)
  ↓
+ MCP Prompts (from PromptRegistry)
  ↓
+ File Context (相关代码文件)
  ↓
+ Chat History (截断的对话)
  ↓
= 最终 Prompt 发送给 LLM
```

## 关键特性

1. **模块化组装**：每个部分独立管理，动态注入
2. **MCP 提示集成**：从 MCP 服务器加载动态提示
3. **上下文感知**：根据用户任务调整提示内容
4. **Token 管理**：确保总 token 数不超过限制

## 运行方式

```bash
uv run main.py
```

## 对应源码

- [packages/core/src/prompts/prompt-registry.ts](../../../projects/gemini-cli/packages/core/src/prompts/prompt-registry.ts)
- Agent loop 中 sendMessageStream() 时的提示组装
