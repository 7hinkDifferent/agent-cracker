# Demo: eigent — complexity-router

## 目标

用最简代码复现 eigent 的 **任务复杂度路由**机制 — `question_confirm_agent` 判断用户消息是简单问题（直接回答）还是复杂任务（启动 Workforce 多 Agent 编排）。

## 原理

Eigent 在处理用户消息前，先经过复杂度判断路由：

```
用户消息 → question_confirm_agent (LLM 判断)
  ├─ 简单问题 → chat_agent 直接回答（单 Agent）
  └─ 复杂任务 → construct_workforce() → 多 Agent 并行编排
```

### 关键设计

1. **question_confirm_agent**: 使用 LLM 判断消息复杂度，决定是否需要多 Agent 协作
2. **直接回答路径**: 简单问题跳过 Workforce 开销，由单个 chat_agent 处理
3. **Workforce 路径**: 复杂任务走 Coordinator → 任务分解 → Worker 并行执行

## 运行

```bash
uv run python main.py
```

无需 API Key，所有 LLM 调用均使用启发式模拟。

## 文件结构

```
demos/eigent/complexity-router/
├── README.md           # 本文件
└── main.py             # ComplexityRouter + 关键词启发式 + Workforce 桩
```

## 关键代码解读

### ComplexityRouter.route() — 路由决策

```python
def route(self, query: str) -> RoutingResult:
    score, reasons = self._compute_score(query)
    if score < self.complexity_threshold:
        return RoutingResult(decision=DIRECT_ANSWER, ...)
    else:
        return RoutingResult(decision=WORKFORCE, ...)
```

### _compute_score() — 复杂度评分

通过四类启发式规则计算 complexity_score (0.0~1.0)：

| 规则 | 影响 | 示例 |
|------|------|------|
| 简单问题关键词 | score -= 0.3 | "what is", "explain", "是什么" |
| 复杂任务关键词 | score += 0.3 | "create", "build", "编写", "部署" |
| 多步骤指示词 | score += 0.2 | "and then", "step by step", "然后" |
| 消息长度 | +0.2 (>200) / -0.1 (<50) | 长消息更可能是复杂任务 |

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 判断方式 | LLM (question_confirm_agent) | 关键词启发式评分 |
| 判断结果 | 二值（是/否为简单问题） | 连续分数 + 可调阈值 |
| 直接回答 | chat_agent LLM 生成 | 模拟字符串 |
| Workforce | CAMEL BaseWorkforce 完整编排 | 模拟任务分解列表 |
| 上下文 | 包含对话历史和项目信息 | 仅当前消息 |

**保留的核心**: 简单问题 vs 复杂任务的二分路由逻辑，以及两条不同处理路径的分流设计。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/service/chat_service.py`
