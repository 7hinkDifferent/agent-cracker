# Demo: Pi-Agent — Steering Queue 双消息队列

## 目标

用最简代码复现 pi-agent 最核心的创新——Steering / Follow-up 双消息队列，以及支持它的双层循环结构。

## 原理

传统 Agent 是"提交-等待"模式：用户发消息 → 等 Agent 完成 → 才能继续输入。Pi-agent 通过双消息队列打破这个限制：

**Steering（方向盘）**：
- 中断当前 tool 执行，跳过剩余 tool
- 将用户消息注入上下文，Agent 立即响应
- 适合"停下来"或"改方向"

**Follow-up（排队）**：
- 等 Agent 完成当前任务后再处理
- 适合追加需求、分步指示

**双层循环**：
```
外层 while: 处理 follow-up 消息
 └─ 内层 while: LLM → tool calls → 检查 steering
     ├─ 执行每个 tool → 检查 steering 队列
     │   └─ 有 steering → 跳过剩余 tool，注入消息
     └─ 无 tool call → Agent 任务完成
 └─ 检查 follow-up → 有 → 继续；无 → 退出
```

**Dequeue 模式**：
- `one-at-a-time`：每次取 1 条，逐个处理
- `all`：一次取出全部，批量处理

## 运行

```bash
cd demos/pi-agent/steering-queue
python main.py
```

无外部依赖，mock LLM 响应，纯 asyncio 实现。

## 文件结构

```
demos/pi-agent/steering-queue/
├── README.md       # 本文件
├── main.py         # 4 个演示场景
└── agent.py        # 简化 Agent + 双队列 + 双层循环
```

## 关键代码解读

### 双队列 + Dequeue

```python
class Agent:
    def steer(self, content):       # → steering_queue
    def follow_up(self, content):   # → followup_queue

    def _dequeue_steering(self):
        if self.steering_mode == "one-at-a-time":
            return [self.steering_queue.pop(0)]  # 取 1 条
        else:
            msgs = self.steering_queue[:]        # 取全部
            self.steering_queue.clear()
            return msgs
```

### Steering 中断时机

```python
# 每个 tool 执行后检查 steering
for i, tc in enumerate(tool_calls):
    await execute_tool(tc)
    steering = self._dequeue_steering()
    if steering:
        # 跳过剩余 tool，注入 steering 消息
        for skipped in tool_calls[i+1:]:
            skip(skipped)
        break
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| LLM 调用 | 真实流式 API | Mock 函数 |
| 消息格式 | AgentMessage union type | 简单 dataclass |
| AbortSignal | 支持 Ctrl+C 取消 | 无 |
| Tool 并行 | 并行执行 tool calls | 串行逐个执行 |
| 消息转换 | convertToLlm() 格式转换 | 无 |
| 上下文变换 | transformContext() 扩展 hook | 无 |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 核心源码: `packages/agent/src/agent.ts` + `packages/agent/src/agent-loop.ts`
