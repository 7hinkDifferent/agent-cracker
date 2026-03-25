# Gemini CLI — Demo Overview

基于 [docs/gemini-cli.md](../../docs/gemini-cli.md) 分析，以下是构建最小可运行版本和复现特色机制所需的组件。

> Based on commit: [`0c91985`](https://github.com/google-gemini/gemini-cli/tree/0c919857fa5770ad06bd5d67913249cd0f3c4f06) (2026-03-25)

## MVP 组件

构建最小可运行版本需要以下组件：

- [x] **event-driven-loop** — 事件驱动主循环（LLM 流式事件 → 工具调用收集 → 并发执行 → 响应回流）(Python)
- [ ] **tool-registry-system** — 工具注册与分发（内置工具类 + MCP 工具发现 + 调度器）(Python)
- [ ] **mcp-tool-integration** — MCP 工具调用（MCP 客户端库集成 + 工具元数据序列化）(Python)
- [ ] **prompt-assembly** — 提示组装（系统提示 + 工具声明注入 + MCP 提示动态加载）(Python)
- [ ] **session-replay** — 会话恢复（事件重放 + eventId/streamId 精确定位 + 流式订阅）(Python)
- [ ] **error-handling** — 错误处理与恢复（LLM 错误 / 工具失败分类 + 致命错误检测）(Python)

## 进阶机制

以下是该 agent 的特色功能，可选择性复现：

- [ ] **message-bus-confirmation** — 权限确认总线（工具执行前交互确认 + 策略管理）
- [ ] **sandbox-execution** — 沙箱隔离执行（Docker/Podman 容器隔离 + 命令重写）
- [ ] **context-window-management** — 上下文策略（1M token 大窗口 + JIT 文件选择 + 溢出检测）

## 完整串联

- [ ] **mini-gemini** — 组合以上 MVP 组件的最小完整 agent

## 进度

MVP: 1/6 | 进阶: 0/3 | 串联: 0/1 | 总计: 1/10

---

## Demo 运行方式

所有 demo 使用 Python ≥3.10，通过 `uv` 管理依赖：

```bash
cd demos/gemini-cli/<mechanism>/
uv run --with google-generativeai,litellm,pydantic main.py
```

**必须环境**：
```bash
export GEMINI_API_KEY="your-api-key"  # 从 https://aistudio.google.com 获取
```

## 参考资源

- **源码分析**：[docs/gemini-cli.md](../../docs/gemini-cli.md)
- **官方文档**：https://geminicli.com/docs/
- **源码仓库**：[projects/gemini-cli](../../projects/gemini-cli)
