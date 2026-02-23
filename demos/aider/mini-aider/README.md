# Demo: Aider — Mini-Aider（完整串联）

## 目标

将 4 个 MVP 组件串联成一个最小完整可运行的 Coding Agent。

**核心设计**: 通过 import 兄弟 MVP demo 的模块实现组合，而非重写所有代码。Mini-aider 本身只实现 Core Loop 逻辑（REPL + 反思循环 + LLM 调用），其余能力全部来自兄弟 demo。

## 组件导入关系

```
mini-aider/main.py
    │
    ├── from prompt-assembly/assembler.py import PromptAssembler
    │     └── ChatChunks 8 段 prompt 组装 + 模板变量替换
    │
    ├── from search-replace/parser.py import find_edit_blocks, EditBlock
    │     └── SEARCH/REPLACE 块状态机提取
    │
    ├── from search-replace/replacer.py import apply_edit
    │     └── 两级模糊匹配编辑应用
    │
    └── from llm-response-parsing/parsers.py import generate_reflection
          └── 解析失败时的反思反馈生成
```

## 数据流

```
用户输入 "Fix the bug in app.py"
    │
    ▼
┌──────────────────────────────────────────────────┐
│ Prompt Assembly (← assembler.py)                  │
│                                                  │
│  PromptAssembler.assemble() → ChatChunks:        │
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
│ Core Loop (本文件) — call_llm()                   │
│                                                  │
│  litellm.completion(model, messages) → response   │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ Response Parsing (← parser.py)                    │
│                                                  │
│  find_edit_blocks(response) → [EditBlock(...)]    │
│  状态机提取 SEARCH/REPLACE 块                      │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ Edit Apply (← replacer.py)                       │
│                                                  │
│  apply_edit(file, search, replace)                │
│  Tier 1: 精确匹配                                 │
│  Tier 2: 空白容忍匹配                             │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│ Reflection Loop (本文件 + parsers.py)             │
│                                                  │
│  if 匹配失败: generate_reflection() → 反馈消息    │
│  if lint 错误: lint_check() → 错误信息            │
│  → 重新组装 prompt → 再次调用 LLM（最多 3 次）     │
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

可通过 `DEMO_MODEL` 环境变量切换模型：
```bash
export DEMO_MODEL=anthropic/claude-sonnet-4-20250514
export DEMO_MODEL=openai/gpt-4o
```

## 文件结构

```
demos/aider/mini-aider/
├── README.md       # 本文件
└── main.py         # Core Loop + 从兄弟 demo import 组件
```

## 本文件 vs 导入模块

| 来源 | 模块 | 提供的能力 |
|------|------|-----------|
| 本文件 | `main.py` | Core Loop (REPL + 反思循环 + LLM 调用 + lint 检查) |
| 兄弟 demo | `prompt-assembly/assembler.py` | ChatChunks + PromptAssembler |
| 兄弟 demo | `search-replace/parser.py` | EditBlock + find_edit_blocks |
| 兄弟 demo | `search-replace/replacer.py` | apply_edit (两级模糊匹配) |
| 兄弟 demo | `llm-response-parsing/parsers.py` | generate_reflection |

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
| 代码量 | ~30,000 行 | ~150 行（+ 导入模块 ~500 行） |
| 编辑格式 | 12+ 种 Coder 子类 | 仅 SEARCH/REPLACE |
| Prompt | 多态模板 + 10+ 变量 | PromptAssembler + reminder 双重注入 |
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
- [prompt-assembly](../prompt-assembly/) — ChatChunks 组装（提供 `assembler.py`）
- [llm-response-parsing](../llm-response-parsing/) — 多格式解析（提供 `parsers.py`）
- [search-replace](../search-replace/) — 编辑解析与应用（提供 `parser.py` + `replacer.py`）
