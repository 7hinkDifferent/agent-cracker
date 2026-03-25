# Demo: eigent — prompt-assembly

## 目标

用最简代码复现 eigent 的**角色化 System Prompt 组装**机制 — XML 结构化模板 + 动态变量注入 + 对话历史上下文拼接。

## MVP 角色

**Prompt 组装** — 为 8 类 Agent 各构建差异化的 system prompt，注入运行时变量和对话历史。对应 D4（Prompt 工程）。

## 原理

Eigent 为每种 Agent 定义了独立的 system prompt（`prompt.py`），采用 **XML 标签结构化**：

- `<role>` — 角色定义和核心能力
- `<team_structure>` — 协作的其他 Agent
- `<operating_environment>` — 运行时环境（系统、工作目录、日期）
- `<mandatory_instructions>` — 必须遵循的规则（笔记共享、文件注册）
- `<capabilities>` — 可用工具和技能（Skills 系统最高优先级）
- `<philosophy>` — 工作理念（偏向行动、完成全流程）

动态变量包括 `{working_directory}`、`{platform_system}`、`{now_str}` 等。
多轮对话时通过 `build_conversation_context()` 拼接前序任务结果和文件列表。

## 运行

```bash
cd demos/eigent/prompt-assembly
uv run python main.py
```

无需 API key — 此 demo 不调用 LLM。

## 文件结构

```
demos/eigent/prompt-assembly/
├── README.md           # 本文件
└── main.py             # 6 种 Agent 的 prompt 模板 + 变量注入 + 历史构建
```

## 关键代码解读

### assemble_prompt() — 模板 + 变量注入

```python
def assemble_prompt(agent_type, context):
    template = PROMPT_TEMPLATES[agent_type]
    return template.format(
        working_directory=context.working_directory,
        platform_system=context.platform_system,
        now_str=context.now_str,
    )
```

### build_conversation_context() — 对话历史拼接

```python
def build_conversation_context(history):
    for entry in history:
        if entry["role"] == "task_result":
            context += f"Previous Task Result: {entry['content']}"
        elif entry["role"] == "assistant":
            context += f"Assistant: {entry['content']}"
    # 文件列表只在最后统一列出
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| Prompt 长度 | 每种 100-200 行 | 保留骨架（30-50 行） |
| Agent 类型 | 8 种完整 prompt | 6 种简化 |
| 文件列表 | list_files() 扫描工作目录 | 无 |
| Skills 指令 | 详细的 Skill 工作流规则 | 简化引用 |
| Browser 外部通知 | {external_browser_notice} 变量 | 无 |
| Coordinator context | 任务分解时注入 | 无 |
| 长度检查 | 200k 字符上限 | 计算但不阻断 |

**保留的核心**：XML 标签结构、动态变量注入、对话历史构建、长度限制检查。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/agent/prompt.py`, `backend/app/service/chat_service.py`
