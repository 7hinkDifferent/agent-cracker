# OpenClaw — Channel Dock

复现 OpenClaw 的统一通道能力抽象接口。

## 机制说明

OpenClaw 通过 ChannelDock 接口统一 13+ 通道的能力差异，让 Agent 代码不需要关心底层通道细节。

### Dock 接口结构

```
ChannelDock {
  capabilities: { text, media, threading, mentions, ... }
  streaming:    { blockReplyCoalescing, chunkSize, typingDuringStream }
  groups:       { mentionRequired, groupMessageHandling }
  threading:    { replyContextDepth, inheritParentBinding }
  maxMessageLength: number
}
```

## 对应源码

| 文件 | 作用 |
|------|------|
| `src/channels/dock.ts` | Dock 接口定义 |
| `src/channels/*/` | 各通道实现 |

## 运行

```bash
uv run python main.py
```
