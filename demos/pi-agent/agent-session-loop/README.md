# Demo: Pi-Agent — Agent Session Loop

## 目标

用最简代码复现 Pi-Agent 的双层循环 + 消息队列架构。

## MVP 角色

会话主循环是 agent 的"心脏"——驱动 LLM 调用、tool 执行、结果回填的核心节拍器。Pi-Agent 的特色是**双层循环 + 双消息队列**：外层处理排队消息，内层驱动 tool 迭代，两者配合 steering 中断实现用户对 agent 的实时控制。

## 原理

Pi-Agent 的会话循环由两层循环和两个消息队列组成：

```
外层循环：处理 follow-up 消息（等 Agent 空闲后执行）
 └─ 内层循环：处理 steering 消息（立即中断当前 tool 执行）
    ├─ 1. 调用 LLM（流式）
    ├─ 2. 检查 tool calls
    │   └─ 执行所有 tool（并行）
    ├─ 3. 检查 steering 消息
    │   └─ 有 steering → 跳过 tool results，注入用户消息
    └─ 4. 有 tool call → 继续；无 → 退出内层循环
```

**双消息队列**：
- **Steering**：中断当前执行，立即改变 agent 行为方向（如"停下来"、"换个方法"）
- **Follow-up**：排队等待，agent 完成当前任务后再处理（如"还有一件事"）

**三种终止条件**：
1. LLM 未返回 tool call → 内层循环退出
2. 无 follow-up 消息 → 外层循环退出
3. Abort 信号 → 立即终止

## 运行

```bash
cd demos/pi-agent/agent-session-loop
uv run python main.py
```

无需 API key，使用 mock LLM 演示循环机制。

## 文件结构

```
demos/pi-agent/agent-session-loop/
├── README.md       # 本文件
├── loop.py         # 可复用模块: SessionLoop + EventStream + MessageQueue
└── main.py         # Demo 入口（从 loop.py import）
```

## 关键代码解读

### EventStream（异步事件迭代器）

```python
class EventStream:
    """消费者通过 async for 遍历事件。"""

    async def __anext__(self) -> Event:
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

# 使用:
async for event in events:
    print(event.type)
```

### 双消息队列

```python
class MessageQueue:
    def add_steering(self, msg):   # 中断型
    def add_followup(self, msg):   # 排队型
    def dequeue_steering(self):    # 内层循环检查
    def dequeue_followup(self):    # 外层循环检查
```

### 双层循环

```python
class SessionLoop:
    async def run(self, initial_message):
        # 外层循环
        while True:
            await self._inner_loop()
            followups = self.queue.dequeue_followup()
            if not followups:
                break
            self.messages.extend(followups)

    async def _inner_loop(self):
        # 内层循环
        while True:
            response = await self.llm.complete(self.messages)
            if not response.tool_calls:
                break
            tool_results = await execute_tool_calls(...)
            steering = self.queue.dequeue_steering()
            if steering:
                self.messages.extend(steering)  # 注入 steering
                continue  # 跳过 tool results
            self.messages.extend(tool_results)
```

## 语言选择说明

原实现使用 TypeScript（`async/await` + `AsyncIterator`），本 demo 使用 Python（`asyncio` + `__aiter__/__anext__`）。Python 3.10+ 的异步迭代器支持与 TypeScript 等价，且保持与其他 demo 的一致性。

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 语言 | TypeScript | Python (asyncio) |
| LLM 调用 | 流式 SSE streaming | Mock（同步返回） |
| Tool 执行 | 并行 Promise.all | 串行 for 循环 |
| 上下文转换 | transformContext() 钩子 | 省略 |
| 消息格式转换 | convertToLlm() | 省略（直接使用） |
| EventStream | 完整 async iterator + 错误处理 | 简化版 Queue-based |
| 队列模式 | all / one-at-a-time | all only |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 基于 commit: `316c2af`
- 核心源码: `packages/agent/src/agent-loop.ts`
