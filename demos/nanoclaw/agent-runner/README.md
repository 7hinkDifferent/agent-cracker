# agent-runner — 容器内 Agent 运行器

## 目标

复现 NanoClaw 容器内的 Agent 运行器核心机制：MessageStream (push-based AsyncIterable) + query 循环 + IPC 消息管道 + PreCompact 对话归档。

## MVP 角色

Agent Runner 是容器层的心脏。它接收 host 传入的 prompt，调用 Claude SDK 处理，通过 MessageStream 接收后续 IPC 消息，并在 context compaction 前归档对话历史。

## 原理

```
stdin JSON ──→ 解析 ContainerInput
                │
                ▼
          ┌─────────────┐
          │ query loop   │
          │  while(true) │
          └──────┬──────┘
                 │
    ┌────────────▼────────────┐
    │ runQuery(prompt, ...)   │
    │                         │
    │  MessageStream ◄── IPC  │  ← 并行轮询 /workspace/ipc/input/
    │    push(text)           │    管道后续消息到 SDK
    │                         │
    │  SDK query() 处理...     │
    │    ↓                    │
    │  result → writeOutput() │  → stdout: OUTPUT_START/END markers
    │                         │
    │  hooks:                 │
    │    PreCompact → archive │  → conversations/YYYY-MM-DD-*.md
    │    PreToolUse → unset   │  → strip API keys from Bash
    └────────────┬────────────┘
                 │
            _close?  ──→ 退出
                 │ no
                 ▼
        waitForIpcMessage()
            │
            ▼ 收到新消息
        prompt = newMessage
        继续循环 ↑
```

**MessageStream 设计**: Push-based AsyncIterable，让 SDK 的 `isSingleUserTurn=false`。活跃容器通过此机制实时接收后续消息，无需重启。

## 运行

```bash
npx tsx main.ts
```

无外部依赖。使用 mock 替代 `@anthropic-ai/claude-agent-sdk`。

## 为何选择 TypeScript

原实现依赖 `@anthropic-ai/claude-agent-sdk` 的 `query()` API 和 `AsyncIterable` 消息协议，这是 TypeScript 的核心异步模式。

## 文件结构

```
agent-runner/
├── README.md       # 本文件
└── main.ts         # Demo: MessageStream + query loop + PreCompact + 5 个场景
```

## 关键代码解读

### MessageStream (push-based AsyncIterable)

```typescript
class MessageStream {
  private queue: UserMessage[] = [];
  private waiting: (() => void) | null = null;
  private done = false;

  push(text: string): void {        // 外部注入消息（IPC）
    this.queue.push({...});
    this.waiting?.();                // 唤醒等待中的 iterator
  }

  end(): void {                      // _close sentinel
    this.done = true;
    this.waiting?.();
  }

  async *[Symbol.asyncIterator]() {  // SDK 消费此 iterator
    while (true) {
      while (this.queue.length > 0) yield this.queue.shift()!;
      if (this.done) return;
      await new Promise<void>(r => { this.waiting = r; });  // 阻塞等待
    }
  }
}
```

### PreCompact 对话归档

```typescript
function archiveConversation(transcriptContent: string, outputDir: string) {
  const messages = parseTranscript(content);  // JSONL → ParsedMessage[]
  // 写入 conversations/YYYY-MM-DD-summary.md
  // 每条消息截断到 2000 字符
}
```

### Bash 密钥清理

```typescript
function sanitizeBashCommand(command: string): string {
  return `unset ANTHROPIC_API_KEY CLAUDE_CODE_OAUTH_TOKEN 2>/dev/null; ${command}`;
}
```

确保容器内的 Bash 子进程无法读取 API 密钥（密钥仅在 SDK 进程内存中）。

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| SDK | `@anthropic-ai/claude-agent-sdk` query() | mock 函数（50ms 延迟） |
| MessageStream | 注入到 SDK 的 prompt 参数 | 独立演示 push/end/iterate |
| IPC 轮询 | setTimeout 500ms 循环 | 文件系统轮询（简化） |
| Session resume | sessionId + resumeAt (lastAssistantUuid) | 仅 sessionId |
| PreCompact | SDK HookCallback 接口 | 独立函数调用 |
| 输出协议 | stdout sentinel markers | 相同实现 |

## 相关文档

- 分析文档: [docs/nanoclaw.md — D2 Agent Loop](../../docs/nanoclaw.md#2-agent-loop主循环机制)
- Prompt 工程: [docs/nanoclaw.md — D4 Prompt 工程](../../docs/nanoclaw.md#4-prompt-工程)
- 原始源码: `projects/nanoclaw/container/agent-runner/src/index.ts` (588 行)
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
