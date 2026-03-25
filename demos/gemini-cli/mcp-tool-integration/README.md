# MCP Tool Integration

复现 Gemini CLI 的 MCP（Model Context Protocol）工具集成。

## 原理

MCP 是标准化的工具/资源 protocol，允许 Gemini CLI 无需修改源码即可加载任意 MCP 服务器的工具：

1. **MCP 客户端**：连接到 MCP 服务器（subprocess/HTTP）
2. **工具发现**：获取服务器提供的工具列表及元数据
3. **工具序列化**：将 MCP 工具转换为 FunctionDeclaration
4. **工具调用**：发送工具参数给 MCP 服务器，获取结果

## 关键特性

1. **插件式扩展**：无需修改 Gemini CLI 源码，启动 MCP 服务器即可获得新工具
2. **标准化接口**：所有 MCP 工具都遵循统一的参数/返回格式
3. **动态发现**：在启动时发现工具列表
4. **错误处理**：MCP 服务器故障不影响内置工具

## 运行方式

```bash
# 需要启动一个 MCP 服务器（此 demo 模拟 MCP 服务）
uv run --with pydantic,typing-extensions main.py
```

## 对应源码

- [packages/core/src/tools/mcp-client-manager.ts](../../../projects/gemini-cli/packages/core/src/tools/mcp-client-manager.ts)
- [packages/core/src/tools/mcp-tool.ts](../../../projects/gemini-cli/packages/core/src/tools/mcp-tool.ts)
