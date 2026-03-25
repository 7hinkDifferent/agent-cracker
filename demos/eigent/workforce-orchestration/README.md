# Demo: eigent — workforce-orchestration

## 目标

用最简代码复现 eigent 的 **CAMEL Workforce 多 Agent 并行编排**机制 — 任务自动分解、角色分配、并行执行、失败重试与质量评估。

## MVP 角色

**Workforce 编排** — 这是 eigent 区别于所有其他已分析 Agent 的核心能力。对应 D2（Agent Loop）+ D7（关键创新）。

## 原理

Eigent 基于 CAMEL-AI 的 `BaseWorkforce` 实现多 Agent 协作：

1. **Coordinator Agent** 将用户任务分解为子任务（`eigent_make_sub_tasks` → `handle_decompose_append_task`）
2. **Task Agent** 根据 Worker 描述将子任务分配给最合适的 Agent（`_find_assignee`）
3. **Worker Agent**（8 类：developer, browser, document 等）通过 CAMEL TaskChannel 并行执行
4. 任务完成后 `_analyze_task()` 评估质量，低于阈值触发 retry 或 replan
5. 失败策略：`FailureHandlingConfig(enabled_strategies=["retry", "replan"])`，最多重试 3 次

## 运行

```bash
cd demos/eigent/workforce-orchestration
export OPENAI_API_KEY="sk-..."
uv run --with litellm python main.py
```

## 文件结构

```
demos/eigent/workforce-orchestration/
├── README.md           # 本文件
└── main.py             # Task/WorkerAgent/Workforce/质量评估
```

## 关键代码解读

### Workforce.execute() — 完整编排流程

```python
async def execute(self, task):
    subtasks = await self.decompose_task(task)      # 1. 分解
    await asyncio.gather(*[                         # 2. 并行执行
        self._execute_subtask(st) for st in subtasks
    ])
    for st in subtasks:                             # 3. 失败重试
        while st.state == FAILED and st.failure_count < max_retries:
            await self._execute_subtask(st)
    task.result = aggregate(subtasks)                # 4. 汇总
```

### decompose_task() — Coordinator 分解

Coordinator 接收 Worker 列表描述，LLM 返回 `[{subtask, worker}]` 数组。原实现使用 CAMEL 的 `TASK_DECOMPOSE_PROMPT`。

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 并行机制 | CAMEL TaskChannel + 线程池 | asyncio.gather |
| Worker 类型 | 8 类 ListenChatAgent | 3 类简化 Agent |
| 任务分配 | Coordinator structured output | LLM JSON 解析 |
| 质量评估 | TaskAnalysisResult + quality_score 阈值 | 简化 LLM 评分 |
| 失败策略 | retry + replan（可切换 worker） | 仅 retry |
| 上下文传递 | coordinator_context 注入 | 无 |

**保留的核心**：任务分解→角色分配→并行执行→失败重试→质量评估的完整流程。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/utils/workforce.py`
