# Demo: Aider — 双模型协作（Architect Mode）

## 目标

用最简代码复现 Aider 的 Architect 模式：架构师模型规划 → 编辑器模型实现。

## 原理

Aider 的 Architect 模式将代码修改拆分为两个阶段，由不同角色（可以是不同模型）完成：

**Phase 1 — 架构师（Architect）**：接收用户请求和当前代码，输出**自然语言的修改计划**。架构师不需要了解 SEARCH/REPLACE 格式，只需要描述"改什么、怎么改、为什么"。

**Phase 2 — 编辑器（Editor）**：接收架构师的计划和当前代码，输出**SEARCH/REPLACE 编辑块**。编辑器负责将高层设计转化为精确的代码修改。

这种分离的好处：
- 架构师可以使用更强（更贵）的模型，专注于设计决策
- 编辑器可以使用更快（更便宜）的模型，执行机械性的代码修改
- 架构师的输出是自然语言，不受特定格式约束

在 Aider 源码中，这是通过 `ArchitectCoder` 类实现的，它继承自 `Coder` 基类，内部维护一个 `editor_coder` 子实例。

## 运行

```bash
cd demos/aider/architect
pip install -r requirements.txt

# 需要 LLM API key
export OPENAI_API_KEY=sk-...
# 或
export ANTHROPIC_API_KEY=sk-ant-...

python main.py
```

无 API key 时会以模拟模式运行，展示流程概念。

## 文件结构

```
demos/aider/architect/
├── README.md           # 本文件
├── requirements.txt    # litellm
├── main.py             # 双模型协作主逻辑 + 内联解析器
└── sample_project/
    └── app.py          # 示例项目文件
```

## 关键代码解读

### 核心流程

```python
def architect_mode(user_request, files, architect_model, editor_model):
    # Phase 1: 架构师分析，输出自然语言计划
    plan = call_llm(
        model=architect_model,
        system="Act as an expert architect. Describe changes needed...",
        message=user_request + file_contents,
    )

    # Phase 2: 编辑器实现，输出 SEARCH/REPLACE 块
    edits = call_llm(
        model=editor_model,
        system="Act as an expert coder. Use SEARCH/REPLACE blocks...",
        message=plan + file_contents,  # 架构师输出作为编辑器输入
    )

    return parse_edit_blocks(edits)
```

### Prompt 设计

架构师 prompt 的关键约束：
- **不输出代码**：只描述修改计划
- **具体到函数名和行号**：给编辑器足够的信息

编辑器 prompt 的关键约束：
- **严格使用 SEARCH/REPLACE 格式**
- **SEARCH 必须精确匹配**现有代码

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| Coder 工厂 | ArchitectCoder 继承 Coder 基类，动态创建 editor_coder | 简单函数调用 |
| 状态继承 | editor_coder 继承 architect 的文件列表、git 状态等 | 直接传递文件字典 |
| 成本追踪 | 分别记录两个模型的 token 使用和费用 | 无 |
| 模型选择 | 支持任意 litellm 模型组合 | 相同（通过 litellm） |
| 反思集成 | 编辑器输出后可触发 lint/test 反思循环 | 无（见 reflection demo） |

## 相关文档

- 分析文档: [docs/aider.md](../../../docs/aider.md)
- 原项目: https://github.com/Aider-AI/aider
- 核心源码: `aider/coders/architect_coder.py`
