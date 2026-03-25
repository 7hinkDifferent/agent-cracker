# Demo: eigent — failure-retry-replan

## 目标

用最简代码复现 eigent 的 **Workforce 失败处理**机制 — `FailureHandlingConfig` 策略配置、`_analyze_task` 质量评估重试、以及 retry + replan 双策略切换。

## 原理

Eigent 基于 CAMEL Workforce 的失败处理采用**评估驱动的重试策略**：

```
Worker 执行失败 → failure_count += 1
  → failure_count < max_retries?
     ├─ Yes → _analyze_task(for_failure=True)
     │    ├─ result is None → 重试评估（最多 3 次）
     │    │    ├─ 全部 None + for_failure=True → RuntimeError
     │    │    └─ 全部 None + for_failure=False → 默认 score=80
     │    ├─ score >= threshold → retry（同一 Worker）
     │    └─ score < threshold → replan（切换 Worker）
     └─ No → 任务标记为 FAILED
```

### 关键数据结构

| 结构 | 作用 |
|------|------|
| `FailureHandlingConfig` | 配置 enabled_strategies + max_retries |
| `TaskAnalysisResult` | 评估结果: reasoning + quality_score (0-100) |
| `Task.failure_count` | 累计失败次数，决定是否继续重试 |

### _analyze_task 的两种模式

| 参数 | for_failure=True | for_failure=False |
|------|-----------------|-------------------|
| 场景 | 失败后重新评估 | 首次质量评估 |
| None 全部失败 | 抛出 RuntimeError | 接受默认 score=80 |
| 用途 | 决定 retry/replan | 判断任务是否合格 |

## 运行

```bash
uv run python main.py
```

无需 API Key，所有 LLM 调用均使用模拟。

## 文件结构

```
demos/eigent/failure-retry-replan/
├── README.md           # 本文件
└── main.py             # FailureHandlingConfig / TaskAnalyzer / WorkforceFailureHandler
```

## 关键代码解读

### TaskAnalyzer.analyze_task() — 评估重试循环

```python
def analyze_task(self, task, for_failure=False):
    for attempt in range(max_retries):
        result = self._simulate_analysis(task)
        if result is not None:
            return result
    # 全部 None
    if for_failure:
        raise RuntimeError("分析失败")
    else:
        return TaskAnalysisResult(reasoning="默认接受", quality_score=80)
```

### WorkforceFailureHandler.handle_task() — retry + replan

```python
while True:
    try:
        result = worker.execute(task)  # 执行
        break
    except RuntimeError:
        task.failure_count += 1
        if task.failure_count >= max_retries:
            break  # 最终失败
        strategy = self._decide_strategy(task)
        if strategy == REPLAN:
            worker = find_alternative_worker()  # 换 Worker
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 质量评估 | LLM (coordinator_agent) | 基于规则的模拟评分 |
| 策略决定 | _analyze_task score 对比 threshold | failure_count 启发式 |
| Worker 选择 | Task Agent 基于描述匹配 | 简单轮换 |
| 任务状态 | CAMEL Task FSM (8 状态) | 简化 4 状态 |
| replan 范围 | 可重新分解子任务 | 仅切换 Worker |
| 并发控制 | TaskChannel + asyncio | 同步单线程 |

**保留的核心**: _analyze_task 的 None 重试 + for_failure 模式分支 + retry/replan 双策略 + failure_count 跟踪。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/utils/workforce.py`
