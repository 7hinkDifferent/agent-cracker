# Demo: Pi-Agent — Prompt Builder

## 目标

用最简代码复现 Pi-Agent 的分层 System Prompt 组装机制。

## MVP 角色

Prompt 组装是 agent 的"语言"——决定 LLM 看到什么工具、遵循什么规则。Pi-Agent 的特色是**自适应指南**：同一 agent 会根据当前激活的工具组合生成不同的提示内容。

## 原理

Pi-Agent 的 system prompt 由 5 层组装：

1. **角色定义** — 固定的 expert coding assistant 身份
2. **工具描述** — 动态注入每个激活工具的名称、描述、参数 schema
3. **自适应指南** — 根据工具组合条件生成（如：有 bash 但没 grep → "用 bash 搜索"；有 bash 也有 grep → "优先用 grep"）
4. **项目上下文** — 注入 `.pi/context/*.md` 的内容（用户自定义的项目说明）
5. **元信息** — 当前时间戳和工作目录

关键洞察：指南不是静态的，而是根据工具可用性**自适应**生成的。

## 运行

```bash
cd demos/pi-agent/prompt-builder
uv run python main.py
```

## 文件结构

```
demos/pi-agent/prompt-builder/
├── README.md       # 本文件
├── builder.py      # 可复用模块: PromptBuilder + ToolDef + 自适应指南
└── main.py         # Demo 入口（从 builder.py import）
```

## 关键代码解读

### 自适应指南（条件生成）

```python
def generate_adaptive_guidelines(tools):
    tool_names = {t.name for t in tools}
    guidelines = []

    # 工具组合不同 → 指南不同
    if "bash" in tool_names and "grep" not in tool_names:
        guidelines.append("Use bash for file searching")
    elif "bash" in tool_names and "grep" in tool_names:
        guidelines.append("Prefer grep over bash for searching")

    if "read" in tool_names and "edit" in tool_names:
        guidelines.append("Always read before editing")
    ...
```

### 工具 Schema 双格式输出

```python
@dataclass
class ToolDef:
    def to_schema_text(self) -> str:
        """文本格式（注入 system prompt）"""

    def to_function_schema(self) -> dict:
        """OpenAI function calling 格式（传给 LLM API）"""
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 语言 | TypeScript | Python |
| 上下文文件 | 读取 `.pi/context/*.md` 磁盘文件 | 字符串参数传入 |
| Skills 系统 | 解析 `~/.pi/skills/` YAML | 省略 |
| 扩展钩子 | `beforeAgentStart` 可修改 prompt | 省略 |
| Schema 格式 | TypeBox JSON Schema | 简化的 dataclass |
| 指南数量 | 10+ 条件规则 | 4 条核心规则 |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 基于 commit: `316c2af`
- 核心源码: `packages/coding-agent/src/core/system-prompt.ts`
