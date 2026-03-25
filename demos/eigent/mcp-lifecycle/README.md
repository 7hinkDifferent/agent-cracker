# Demo: eigent — mcp-lifecycle

## 目标

用最简代码复现 eigent 的 **MCP 服务器全生命周期管理**机制 — 从配置校验、认证目录初始化、连接重试、工具发现到断开连接的完整流程。

## 原理

Eigent 通过 MCP (Model Context Protocol) 集成外部工具服务：

```
安装流程:
  validate_config()      → 校验 command/args/env
  → pre_instantiate()    → 创建 ~/.mcp-auth 目录 + 注入环境变量
  → connect()            → stdio transport 启动进程（3 次重试, 2s 间隔）
  → get_tools()          → tools/list 获取可用工具
  → 工具注入 Agent toolkit

断开:
  disconnect()           → 关闭进程连接 + 清理工具缓存
```

### 配置格式

```json
{
  "notion": {
    "command": "npx",
    "args": ["-y", "@notionhq/notion-mcp-server"],
    "env": {
      "OPENAPI_MCP_HEADERS": "{\"Authorization\": \"Bearer ntn_xxx\"}"
    }
  }
}
```

### 连接重试策略

| 参数 | 值 |
|------|------|
| 最大重试次数 | 3 |
| 重试间隔 | 2 秒 |
| 传输方式 | stdio (启动子进程) |

## 运行

```bash
uv run python main.py
```

无需 API Key，所有连接和工具发现均使用模拟。

## 文件结构

```
demos/eigent/mcp-lifecycle/
├── README.md           # 本文件
└── main.py             # McpServerManager / AuthManager / 生命周期状态机
```

## 关键代码解读

### McpServerManager.install() — 完整安装流程

```python
def install(self, config):
    self._validate_config(config)     # 1. 校验配置
    self._pre_instantiate(config)     # 2. auth 目录 + 环境变量
    self._connect_with_retry(config)  # 3. 连接（3 次重试）
    tools = self._discover_tools(config)  # 4. 工具发现
```

### _connect_with_retry() — 连接重试

```python
for attempt in range(1, MAX_RETRIES + 1):
    success = self._simulate_connection(config, attempt)
    if success:
        self._servers[config.name] = CONNECTED
        return True
    time.sleep(RETRY_DELAY)  # 2 秒延迟
# 全部失败
self._servers[config.name] = ERROR
```

### AuthManager — 认证目录管理

```python
class AuthManager:
    def __init__(self):
        self.auth_dir = Path("~/.mcp-auth").expanduser()

    def ensure_auth_dir(self):
        self.auth_dir.mkdir(parents=True, exist_ok=True)
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 传输协议 | stdio transport (子进程) | 模拟连接 |
| 工具发现 | MCP protocol tools/list | 静态注册表模拟 |
| auth 管理 | 真实 ~/.mcp-auth + OAuth | 路径模拟，不创建文件 |
| 连接池 | 多 server 并发管理 | 串行管理 |
| 工具注入 | 转换为 CAMEL FunctionTool | 返回 McpTool 列表 |
| 错误处理 | 详细错误码 + 日志 | 简化打印 |

**保留的核心**: 5 步生命周期流程 (validate → pre_instantiate → connect → get_tools → disconnect) + 3 次连接重试 + auth 目录管理。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `server/app/controller/mcp/mcp_controller.py`, `backend/app/agent/toolkit/notion_mcp_toolkit.py`
