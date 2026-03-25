# Demo: eigent — toolkit-dispatch

## 目标

用最简代码复现 eigent 的 **Toolkit 三层分发体系** — AbstractToolkit 基类、get_toolkits() 收集器、@listen_toolkit 事件装饰器。

## MVP 角色

**Tool 注册与分发** — 按 Agent 类型动态收集和过滤可用工具，执行时自动织入 UI 事件。对应 D3（Tool/Action 系统）。

## 原理

Eigent 的 Tool 系统由三层组成：

1. **AbstractToolkit 基类**：所有 Toolkit 继承此类，通过 `get_can_use_tools(api_task_id)` 实现条件过滤（如 GithubToolkit 检查 token 是否存在、HumanToolkit 只暴露 ask 不暴露 send）
2. **get_toolkits() 收集器**（`tools.py`）：按名称列表从全局注册表查找 Toolkit 类，调用 `get_can_use_tools()` 收集可用工具，合并为统一列表
3. **@listen_toolkit 装饰器**：包装 Toolkit 方法，在执行前后自动发送 `activate_toolkit`/`deactivate_toolkit` 事件。设置 `__listen_toolkit__ = True` 标记，`ListenChatAgent._execute_tool()` 检查此标记避免重复发送

## 运行

```bash
cd demos/eigent/toolkit-dispatch
uv run python main.py
```

无需 API key — 此 demo 不调用 LLM。

## 文件结构

```
demos/eigent/toolkit-dispatch/
├── README.md           # 本文件
└── main.py             # @listen_toolkit/AbstractToolkit/get_toolkits/4 个 Toolkit
```

## 关键代码解读

### @listen_toolkit — 事件装饰器

```python
def listen_toolkit(inputs=None, return_msg=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            print(f"[activate] {toolkit}.{func.__name__}")
            result = func(self, *args, **kwargs)
            print(f"[deactivate] {toolkit}.{func.__name__}")
            return result
        wrapper.__listen_toolkit__ = True  # 关键标记
        return wrapper
    return decorator
```

### get_can_use_tools — 条件过滤

```python
class SearchToolkit(AbstractToolkit):
    @classmethod
    def get_can_use_tools(cls, api_task_id, agent_name=""):
        if agent_name == "browser_agent":
            return cls(api_task_id).get_tools()  # 只有 browser 可用
        return []
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| Toolkit 数量 | 30+（含 MCP） | 4 个核心 |
| MCP 工具 | get_mcp_tools() 动态连接 MCP 服务器 | 无 |
| @auto_listen_toolkit | 类级装饰器自动包装所有方法 | 定义但未演示 |
| ToolkitMessageIntegration | 注入 send_message 到其他 Toolkit | 无 |
| Skill 配置 | 三层配置文件 + 按 Agent 类型权限 | 简化为允许列表 |

**保留的核心**：三层体系（基类→收集器→装饰器）、条件过滤（get_can_use_tools）、`__listen_toolkit__` 标记机制。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/agent/toolkit/abstract_toolkit.py`, `backend/app/agent/tools.py`, `backend/app/utils/listen/toolkit_listen.py`
