# Demo: Aider — 反思循环（Reflection Loop）

## 目标

用最简代码复现 Aider 的反思循环机制：编辑 → lint/test → 失败则将错误反馈 LLM → 重试。

## 原理

Aider 的反思循环是其自动修复能力的核心。当 LLM 生成的代码有语法错误或测试失败时，Aider 不会简单报错，而是将错误信息**自动反馈给 LLM**，让它修正自己的输出。

工作流程（来自 `BaseCoder.run_one()`）：
1. 用户发出编辑请求
2. LLM 生成 SEARCH/REPLACE 编辑块
3. 应用编辑到文件
4. 运行 lint（语法检查）→ 如果失败，将错误反馈 LLM
5. 运行 test（功能测试）→ 如果失败，将错误反馈 LLM
6. 重复 2-5，最多 3 次（`max_reflections` 参数控制）
7. 成功 or 放弃

关键设计：反思消息直接追加到对话历史中，LLM 能看到自己之前的错误输出和具体的错误信息，从而进行针对性修复。

## 运行

```bash
cd demos/aider/reflection
pip install -r requirements.txt

# 需要 LLM API key
export OPENAI_API_KEY=sk-...
# 或
export ANTHROPIC_API_KEY=sk-ant-...

python main.py
```

无 API key 时会以模拟模式运行，展示流程但不实际调用 LLM。

## 文件结构

```
demos/aider/reflection/
├── README.md           # 本文件
├── requirements.txt    # litellm, pytest
└── main.py             # 反思循环主逻辑 + 内联 SEARCH/REPLACE 解析器
```

## 关键代码解读

### 反思循环核心

```python
def reflection_loop(user_request, work_dir, filenames, max_reflections=3):
    message = user_request
    for attempt in range(max_reflections + 1):
        response = call_llm(message, files)        # 调用 LLM
        edits = find_edit_blocks(response)          # 解析编辑
        apply_edits(edits)                          # 应用到文件

        errors = run_lint(files) or run_tests(dir)  # 检查错误
        if not errors:
            return True                              # 成功！

        message = f"Fix these errors:\n{errors}"     # 反思 → 重试
    return False
```

### 错误反馈格式

Aider 将 lint/test 错误直接作为用户消息发送给 LLM：
```
Fix these errors:

Lint error in sample.py:
  File "sample.py", line 5
    def fibonacci(n)  # missing colon
                    ^
SyntaxError: expected ':'
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| Lint 工具 | 可配置（flake8, tree-sitter 等） | 仅 py_compile |
| 测试工具 | 用户指定的测试命令 | 仅 pytest |
| 反思次数 | 可配置，默认 3 | 固定 3 |
| Git 集成 | 每次编辑自动 commit | 无 |
| 对话历史 | 完整多轮对话 | 每次重发文件内容 |

## 相关文档

- 分析文档: [docs/aider.md](../../../docs/aider.md)
- 原项目: https://github.com/Aider-AI/aider
- 核心源码: `aider/coders/base_coder.py` (`run_one()` 方法)
