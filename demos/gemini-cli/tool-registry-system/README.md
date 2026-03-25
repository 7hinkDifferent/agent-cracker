# Tool Registry System

复现 Gemini CLI 的工具注册与分发机制。

## 原理

Gemini CLI 支持**多源工具注册**：

1. **内置工具**：在 `tools.ts` 中定义的本地工具类（EditTool, WriteTool, ShellTool 等）
2. **MCP 工具**：从 MCP 服务器动态发现的工具
3. **工具注册流程**：
   ```
   BaseDeclarativeTool (抽象类)
       ↓
   具体工具类（EditTool, ShellTool 等）
       ↓
   为每个工具创建 FunctionDeclaration （用于 Genai SDK）
       ↓
   ToolRegistry 维护工具列表
       ↓
   LLM 可见（作为 function calling）
   ```

## 关键特性

1. **工具基类模式**：所有工具继承 BaseDeclarativeTool
2. **元数据注入**：FunctionDeclaration 自动生成工具签名
3. **参数验证**：Genai SDK 在发送前验证参数合法性
4. **并发调度**：多个工具可同时执行

## 运行方式

```bash
uv run --with google-generativeai,pydantic main.py
```

## 对应源码

- [packages/core/src/tools/tools.ts](../../../projects/gemini-cli/packages/core/src/tools/tools.ts) (BaseDeclarativeTool)
- [packages/core/src/tools/tool-registry.ts](../../../projects/gemini-cli/packages/core/src/tools/tool-registry.ts)
- [packages/core/src/tools/edit.ts](../../../projects/gemini-cli/packages/core/src/tools/edit.ts)
- [packages/core/src/tools/shell.ts](../../../projects/gemini-cli/packages/core/src/tools/shell.ts)
