# Demo: Aider — Mini-Aider（完整串联）

## 目标

将 4 个 MVP 组件串联成一个最小完整可运行的 Coding Agent。

## 组件串联

```
用户输入 "Fix the bug in app.py"
    │
    ▼
┌──────────────────────────────────────────────────┐
│ Prompt Assembly (组件 1)                          │
│                                                  │
│  ChatChunks:                                     │
│  [system]  角色 + SEARCH/REPLACE 规则 + reminder  │
│  [examples] few-shot 示例                        │
│  [done]    历史对话                               │
│  [files]   app.py 文件内容                        │
│  [cur]     "Fix the bug in app.py"               │
│  [reminder] 格式规则再次提醒                      │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ Core Loop (组件 2) — call_llm()                   │
│                                                  │
│  litellm.completion(model, messages) → response   │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ LLM Response Parsing (组件 3)                     │
│                                                  │
│  parse_edits(response) → [EditBlock(...), ...]    │
│  状态机提取 SEARCH/REPLACE 块                      │
│  文件名模糊匹配                                   │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ Search/Replace (组件 4)                           │
│                                                  │
│  apply_edit(file, search, replace)                │
│  Tier 1: 精确匹配                                 │
│  Tier 2: 空白容忍匹配                             │
│  新文件: 空 SEARCH → 直接创建                      │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ Reflection Loop (组件 2 内层)                      │
│                                                  │
│  if 匹配失败 or lint 错误:                        │
│    反思消息 → 重新组装 prompt → 再次调用 LLM       │
│    最多 3 次                                      │
└──────────────────────────────────────────────────┘
```

## 运行

```bash
cd demos/aider/mini-aider

# 方式 1: 启动时指定文件
uv run --with litellm python main.py app.py utils.py

# 方式 2: 启动后用 /add 添加文件
uv run --with litellm python main.py
> /add app.py
> Fix the divide-by-zero bug
```

需要设置对应模型的 API key 环境变量（如 `OPENAI_API_KEY`）。

可通过 `LITELLM_MODEL` 环境变量切换模型：
```bash
export LITELLM_MODEL=anthropic/claude-sonnet-4-20250514
export LITELLM_MODEL=openai/gpt-4o
```

## 文件结构

```
demos/aider/mini-aider/
├── README.md       # 本文件
└── main.py         # 完整 mini agent（~250 行）
```

## 各组件在 main.py 中的位置

| 组件 | 函数/类 | 行数 |
|------|---------|------|
| Prompt Assembly | `ChatChunks`, `assemble_prompt()` | ~60 行 |
| Response Parsing | `parse_edits()`, `_find_filename()` | ~50 行 |
| Edit Apply | `apply_edit()`, `_find_normalized()`, `_reindent()` | ~60 行 |
| Core Loop | `run_one()`, `run()`, `main()` | ~80 行 |

## 支持的交互命令

| 命令 | 作用 |
|------|------|
| `/add <file>` | 添加文件到聊天上下文 |
| `/drop <file>` | 从上下文移除文件 |
| `/files` | 列出当前上下文中的文件 |
| `/quit` | 退出 |

## 与完整 Aider 的差异

| 方面 | 完整 Aider | Mini-Aider |
|------|-----------|------------|
| 代码量 | ~30,000 行 | ~250 行 |
| 编辑格式 | 12+ 种 Coder 子类 | 仅 SEARCH/REPLACE |
| Prompt | 多态模板 + 10+ 变量 | 固定模板 + reminder 双重注入 |
| 上下文 | RepoMap + token 预算 + 摘要 | 直接拼接文件内容 |
| 匹配 | 5 级容错 | 2 级（精确 + 空白容忍） |
| Git | 自动 commit/undo/diff | 无 |
| 命令 | 40+ 斜杠命令 | 4 个基础命令 |
| 流式输出 | 实时 streaming | 非流式 |
| 模式切换 | SwitchCoder 异常 | 无 |

## 相关文档

- 分析文档: [docs/aider.md](../../../docs/aider.md)
- 原项目: https://github.com/Aider-AI/aider
- 基于 commit: `7afaa26`
- 核心源码: `aider/coders/base_coder.py`, `aider/coders/editblock_coder.py`

### 各组件独立 demo

- [core-loop](../core-loop/) — 三层嵌套主循环
- [prompt-assembly](../prompt-assembly/) — ChatChunks 组装
- [llm-response-parsing](../llm-response-parsing/) — 多格式解析
- [search-replace](../search-replace/) — 编辑解析与应用
