# Demo: Pi-Agent — Extension Hooks

## 目标

用最简代码复现 Pi-Agent 的深度扩展系统。

## 原理

Pi-Agent 的扩展可以介入 Agent 生命周期的每个阶段，并动态注册工具和命令：

### 生命周期钩子

| Hook | 介入点 | 能力 |
|------|--------|------|
| `input` | 用户输入前 | 拦截/转换输入 |
| `beforeAgentStart` | Agent 思考前 | 注入 messages、改写 system prompt |
| `context` | 上下文变换 | 裁剪/富化消息 |
| `toolCall` | Tool 执行前 | 拦截危险操作 |
| `toolResult` | Tool 执行后 | 修改/过滤结果 |
| `turnStart` | 每轮开始 | 日志/统计 |
| `turnEnd` | 每轮结束 | 日志/清理 |
| `resourcesDiscover` | 资源发现 | 注册 provider、tool、command |

### 动态注册

- **工具**：扩展可在运行时注册新的 tool（如 JIRA 查询、测试执行）
- **命令**：扩展可注册自定义斜杠命令（如 `/test`、`/ticket`）

### 钩子链

多个扩展的同类型钩子按注册顺序链式执行，任一返回 `cancelled=True` 则中断后续钩子。

## 运行

```bash
cd demos/pi-agent/extension-hooks
uv run python main.py
```

## 文件结构

```
demos/pi-agent/extension-hooks/
├── README.md       # 本文件
└── main.py         # Demo（自包含，含 ExtensionManager + 4 个示例扩展）
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 语言 | TypeScript | Python |
| 扩展加载 | 文件系统扫描 + 动态 import | 代码内注册 |
| UI 覆盖 | React 组件覆盖 | 省略 |
| 键盘快捷键 | 注册自定义快捷键 | 省略 |
| CLI 参数 | 注册自定义 CLI flag | 省略 |
| 异步钩子 | 完整 async/await | 同步函数 |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 基于 commit: `316c2af`
- 核心源码: `packages/agent/src/extensions/`
