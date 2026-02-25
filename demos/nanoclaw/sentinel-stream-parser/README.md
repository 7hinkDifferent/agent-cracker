# sentinel-stream-parser — 流式哨兵标记解析

## 目标

复现 NanoClaw 的**流式**哨兵标记解析机制：在逐 chunk 到达的 stdout 流中，可靠地提取 `---NANOCLAW_OUTPUT_START---` / `---NANOCLAW_OUTPUT_END---` 之间的 JSON 结果，即使标记跨 chunk 边界。

## 与 container-spawn 的区别

`container-spawn` demo 演示了完整的容器生命周期（mount、spawn、stdin、解析、超时），其中 `SentinelParser` 是辅助组件。本 demo 专注于解析器本身的**流式边界处理**，覆盖原实现中 chunk 拆分、buffer 累积、错误恢复等边角场景。

## 原理

```
容器 stdout (chunk 流)                    StreamingSentinelParser
  │                                              │
  │  chunk 0: "[DEBUG] SDK init...\n"           │
  │──────────────────────────────────────────→   │  buffer += chunk
  │                                              │  未找到 START → 丢弃安全部分
  │                                              │
  │  chunk 1: "---NANOCLAW"                      │
  │──────────────────────────────────────────→   │  buffer += chunk
  │                                              │  找到部分 START → 保留在 buffer
  │                                              │
  │  chunk 2: "_OUTPUT_START---\n{...}\n"        │
  │──────────────────────────────────────────→   │  buffer += chunk
  │                                              │  找到完整 START! 搜索 END...
  │                                              │  未找到 END → break，等待
  │                                              │
  │  chunk 3: "---NANOCLAW_OUTPUT_END---\n"      │
  │──────────────────────────────────────────→   │  buffer += chunk
  │                                              │  找到 END!
  │                                              │  提取 JSON → ParseEvent(OUTPUT)
  │                                              │  截断 buffer → 继续搜索
  │                                              │
  │  (容器关闭)                                   │
  │                                              │  flush() → 返回残留日志
```

**关键**: buffer 累积 + while 循环搜索，使得无论 OS 如何拆分 chunk，都能正确匹配标记对。

## 运行

```bash
uv run python main.py
```

无外部依赖，纯标准库实现。

## 文件结构

```
sentinel-stream-parser/
├── README.md     # 本文件
├── main.py       # Demo 入口（5 个演示场景）
└── parser.py     # 可复用模块: StreamingSentinelParser
```

## 关键代码解读

### feed() — 逐 chunk 解析（parser.py）

```python
def feed(self, chunk: str) -> list[ParseEvent]:
    self._buffer += chunk
    events = []
    while True:
        start_idx = self._buffer.find(OUTPUT_START)
        if start_idx == -1:
            # 保留可能的不完整前缀，丢弃安全部分
            break
        end_idx = self._buffer.find(OUTPUT_END, start_idx + len(OUTPUT_START))
        if end_idx == -1:
            break  # 不完整的标记对，等待更多数据
        json_str = self._buffer[start_idx + len(OUTPUT_START):end_idx].strip()
        self._buffer = self._buffer[end_idx + len(OUTPUT_END):]
        events.append(self._parse_json(json_str))
    return events
```

与原实现 `container-runner.ts:302-332` 的 while 循环完全对齐:
- `parseBuffer += chunk` → `self._buffer += chunk`
- `parseBuffer.indexOf(OUTPUT_START_MARKER)` → `self._buffer.find(OUTPUT_START)`
- `parseBuffer.slice(endIdx + OUTPUT_END_MARKER.length)` → `self._buffer[end_idx + len(OUTPUT_END):]`

### buffer 安全丢弃策略（parser.py）

```python
def _find_safe_discard_point(self) -> int:
    max_prefix = len(OUTPUT_START) - 1
    if len(self._buffer) <= max_prefix:
        return 0
    return len(self._buffer) - max_prefix
```

当 buffer 中没有完整 START 标记时，末尾可能是 `"---NANOCLAW_O"` 这样的不完整前缀。保留最后 `len(OUTPUT_START)-1` 个字符，避免丢弃正在形成的标记。

## 5 个演示场景

| # | 场景 | 验证点 |
|---|------|--------|
| 1 | 基本解析 | 完整标记对在单个 chunk → 提取 JSON |
| 2 | 跨 chunk 边界 | START/END 被拆到不同 chunk → buffer 累积后仍能匹配 |
| 3 | 多输出提取 | 单 chunk 含 2 个标记对 → while 循环提取全部 |
| 4 | 混合内容 | SDK 日志交错 → 只提取标记内 JSON，日志被丢弃 |
| 5 | 异常处理 | 缺失 END / 非法 JSON / 嵌套标记 / 错误后恢复 |

## 与原实现的差异

| 方面 | 原实现 (container-runner.ts) | Demo (parser.py) |
|------|------------------------------|-------------------|
| 运行环境 | Node.js `stdout.on('data')` 事件 | Python `feed()` 方法调用 |
| buffer 管理 | `let parseBuffer = ''` 局部变量 | `self._buffer` 实例属性 |
| 输出回调 | `outputChain.then(() => onOutput(parsed))` | 返回 `list[ParseEvent]` |
| 超时重置 | `resetTimeout()` 在解析成功后调用 | 不涉及（专注解析） |
| 日志处理 | 累积到 `stdout` 变量用于日志文件 | `flush()` 返回残留文本 |
| 错误处理 | `logger.warn` 静默跳过 | 返回 `EventType.ERROR` 事件 |

## 相关文档

- 分析文档: [docs/nanoclaw.md — D2 Agent Loop](../../docs/nanoclaw.md#2-agent-loop主循环机制)
- 容器启动 demo: [demos/nanoclaw/container-spawn/](../container-spawn/)
- 原始源码: `projects/nanoclaw/src/container-runner.ts` (第 279-333 行)
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
