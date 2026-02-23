# Demo: Aider — Core Loop（主循环）

## 目标

用最简代码复现 Aider 的三层嵌套主循环骨架。

## MVP 角色

主循环是 Aider 的核心骨架，负责驱动整个"用户输入 → LLM 调用 → 编辑应用 → 自动修复"的闭环。

## 原理

Aider 的主循环采用**三层嵌套架构**：

1. **外层**（`main.py`）：处理模式/Coder 切换。当用户切换编辑格式或模型时，通过 `SwitchCoder` 异常跳出当前 Coder，创建新实例重新进入。
2. **中层**（`run()`）：REPL 交互循环。等待用户输入 → 处理斜杠命令（`/add`, `/drop`）→ 非命令消息交给 `run_one()` 处理。
3. **内层**（`run_one()`）：反思循环。调用 LLM → 解析响应 → 应用编辑 → lint/test 检查 → 如果失败则将错误反馈给 LLM 自动修复，最多 3 次。

```
外层 main():
  while True:
    try:
      run(mode)           ← 中层
    except SwitchMode:
      mode = new_mode     ← 切换模式

中层 run():
  while True:
    input = get_input()
    if is_command(input):
      handle_command()    ← /add, /drop, /quit
    else:
      run_one(input)      ← 内层

内层 run_one():
  while message:
    response = call_llm(message)
    edits = parse_edits(response)
    applied, failed = apply_edits(edits)
    if failed or lint_errors:
      if reflections >= 3: break
      message = error_feedback   ← 反思
    else:
      break
```

## 运行

```bash
cd demos/aider/core-loop

# 设置模型（可选，默认 openai/gpt-4o-mini）
export LITELLM_MODEL=openai/gpt-4o-mini

uv run --with litellm python main.py
```

需要设置对应模型的 API key 环境变量（如 `OPENAI_API_KEY`）。

## 文件结构

```
demos/aider/core-loop/
├── README.md       # 本文件
└── main.py         # 三层主循环 + 极简编辑解析
```

## 关键代码解读

### 三层循环

```python
# 外层：模式切换
def main():
    mode = "code"
    while True:
        try:
            run(mode)
            break
        except SwitchMode as e:
            mode = e.mode       # SwitchCoder 异常模式

# 中层：REPL
def run(mode):
    while True:
        user_input = input("> ")
        if user_input.startswith("/"):
            handle_command(...)  # /add, /drop, /quit, /mode
        else:
            run_one(user_input, messages, mode)

# 内层：反思循环
def run_one(user_message, messages, mode):
    reflected_message = user_message
    num_reflections = 0
    while reflected_message:
        response = call_llm(messages)
        edits = parse_edits(response)
        applied, failed = apply_edits(edits)
        if failed or lint_errors:
            num_reflections += 1
            if num_reflections >= 3: break
            reflected_message = error_feedback
        else:
            break
```

### 反思触发条件

```python
# 1. SEARCH 块未匹配 → 编辑失败
if failed:
    reflected_message = "These blocks failed...\nPlease fix."

# 2. 语法检查失败
lint_errors = lint_check(applied)
if lint_errors:
    reflected_message = f"Lint errors:\n{lint_errors}\nPlease fix."
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| Coder 体系 | 12+ 种 Coder 子类，工厂模式创建 | 单一模式，用字符串标识 |
| 命令系统 | 40+ 斜杠命令，`cmd_*` 自动发现 | 4 个基础命令（/add, /drop, /mode, /quit） |
| 编辑解析 | 多格式适配（EditBlock/Whole/Udiff/Patch） | 仅 SEARCH/REPLACE |
| 反思触发 | lint + test + parse error，用户可确认 | lint + parse error，自动进行 |
| 上下文管理 | RepoMap + token 预算 + 历史摘要 | 简单的消息列表累积 |
| Git 集成 | 自动 commit + undo + diff | 无 |
| 流式输出 | 支持 streaming，实时显示 | 非流式，完整返回 |

## 相关文档

- 分析文档: [docs/aider.md](../../../docs/aider.md)
- 原项目: https://github.com/Aider-AI/aider
- 基于 commit: `7afaa26`
- 核心源码: `aider/coders/base_coder.py`（run / run_one / send_message）
