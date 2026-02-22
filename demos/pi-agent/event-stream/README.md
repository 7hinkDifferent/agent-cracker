# Demo: Pi-Agent — EventStream 异步事件流

## 目标

用最简代码复现 pi-agent 的 EventStream 模式：自定义 AsyncIterator + 事件队列，实现 producer-consumer 解耦。

## 原理

Pi-agent 的 EventStream 是其事件传递的核心基础设施。Agent Loop 作为 producer 推送事件（thinking、tool 执行、文本输出等），UI/Consumer 用 `async for` 实时消费。

关键设计——**demand-driven delivery**：
- `push(event)` 时检查是否有 consumer 在等待
- **有 waiter** → 直接唤醒，零延迟传递
- **无 waiter** → 入队缓冲，consumer 来了再取

这避免了固定大小 buffer 的背压问题，也避免了无限缓冲的内存问题。

## 运行

```bash
cd demos/pi-agent/event-stream
python main.py
```

无外部依赖，纯 asyncio 实现。

## 文件结构

```
demos/pi-agent/event-stream/
├── README.md          # 本文件
├── main.py            # 3 个演示场景
└── event_stream.py    # EventStream 核心实现（~70 行）
```

## 关键代码解读

### EventStream 核心

```python
class EventStream(Generic[T, R]):
    def push(self, event: T) -> None:
        # demand-driven: 有 waiter 直接唤醒，否则入队
        if self._waiters:
            waiter = self._waiters.pop(0)
            waiter.set_result(event)
        else:
            self._queue.append(event)

    async def __anext__(self) -> T:
        if self._queue:           # 队列有数据 → 立即返回
            return self._queue.pop(0)
        if self._done:            # 已结束 → 停止迭代
            raise StopAsyncIteration
        waiter = Future()         # 等待 producer push
        self._waiters.append(waiter)
        return await waiter
```

### 完成条件 + 结果聚合

```python
stream = EventStream(
    is_complete=lambda e: e.type == "agent_end",  # 完成条件
    extract_result=lambda e: e.data,               # 结果提取
)
# 迭代消费事件，独立等待最终结果
async for event in stream: ...
result = await stream.result()
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 语言 | TypeScript | Python asyncio |
| 泛型 | `EventStream<T, R>` 双泛型 | TypeVar 实现 |
| 事件类型 | 复杂 union type（20+ 种事件） | 简化为 5 种 |
| 子类 | `AssistantMessageEventStream` | 无（直接配置） |
| 错误处理 | try-catch + error event | 简化省略 |

## 相关文档

- 分析文档: [docs/pi-agent.md](../../../docs/pi-agent.md)
- 原项目: https://github.com/badlogic/pi-mono
- 核心源码: `packages/ai/src/utils/event-stream.ts`
