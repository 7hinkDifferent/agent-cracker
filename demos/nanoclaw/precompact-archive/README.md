# precompact-archive — PreCompact 对话归档

## 目标

复现 NanoClaw 的 PreCompact hook 机制：在 Claude SDK 执行 context compaction 前，自动将完整对话 transcript 解析并归档为人类可读的 Markdown 文件。

## MVP 角色

PreCompact Archive 是 NanoClaw 上下文管理的关键补充。SDK compaction 会丢弃旧对话内容，但归档文件保留了完整历史，使 agent 在后续 session 中仍可通过文件系统访问。

## 原理

```
Claude SDK                    PreCompact Hook               文件系统
  │                              │                            │
  │ 1. context 接近窗口上限        │                            │
  │    触发 compaction            │                            │
  │──PreCompact event──────────→│                            │
  │  {transcript_path,           │                            │
  │   session_id}                │                            │
  │                              │ 2. 读取 JSONL transcript    │
  │                              │    (SDK 内部对话日志)         │
  │                              │                            │
  │                              │ 3. parseTranscript()        │
  │                              │    逐行解析 JSON:            │
  │                              │    - user: string/array     │
  │                              │    - assistant: text+tools  │
  │                              │    - 跳过无效行              │
  │                              │                            │
  │                              │ 4. 截断长消息 (>2000 chars)  │
  │                              │                            │
  │                              │ 5. formatTranscriptMarkdown()
  │                              │────写入 Markdown────────→  │
  │                              │    conversations/           │
  │                              │    YYYY-MM-DD-summary.md    │
  │                              │                            │
  │←─────返回 {} ────────────────│                            │
  │ 6. SDK 继续执行 compaction    │                            │
```

**JSONL transcript 格式**: SDK 内部将每轮对话写为 JSONL 文件，每行一个 JSON 事件。user 消息的 content 可以是字符串或数组（多个 text block），assistant 消息的 content 始终是数组（text block + tool_use block 混合）。

**截断策略**: 每条消息限制 2000 字符，超出部分用 "..." 表示。这是在归档可读性和存储空间之间的平衡。

## 运行

```bash
uv run python main.py
```

无外部依赖，仅使用标准库。

## 文件结构

```
precompact-archive/
├── README.md       # 本文件
├── main.py         # Demo 入口（5 个演示场景）
└── archiver.py     # 可复用模块: parse_transcript + archive_to_markdown + generate_summary
```

## 关键代码解读

### JSONL 解析（archiver.py）

```python
def parse_transcript(jsonl_content: str) -> list[ParsedMessage]:
    for line in jsonl_content.split("\n"):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # 跳过无效行（SDK 日志等）

        if entry_type == "user":
            # content: string 或 [{"type":"text","text":"..."}]
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "".join(block.get("text", "") for block in content)

        elif entry_type == "assistant":
            # text blocks + tool_use blocks 分离
            for block in content:
                if block["type"] == "text": text_parts.append(...)
                elif block["type"] == "tool_use": tool_uses.append(...)
```

两种 user content 格式的处理是关键细节——简单消息用 string，多模态或分段消息用 array。

### Markdown 归档（archiver.py）

```python
def archive_to_markdown(messages, title, output_dir):
    for msg in messages:
        content = _truncate(msg.content)  # >2000 chars → 截断+"..."
        lines.append(f"**{sender}**: {content}")
        for tool in msg.tool_uses:
            lines.append(f"> Tool: {name}({args})")  # 引用块格式
```

Tool use 以 blockquote 格式保留，便于在 Markdown 中视觉区分。

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| Session 摘要 | 从 sessions-index.json 读取 | 从首条用户消息生成 |
| 时间格式 | `toLocaleString('en-US')` | `strftime` 格式化 |
| Tool use | 不保留（原实现 parseTranscript 只提取 text） | 扩展保留 tool_use blocks |
| 文件名回退 | `conversation-HHmm`（当前时间） | `conversation`（固定） |
| assistantName | 从 ContainerInput 传入 | 参数可选，默认 "Assistant" |
| Hook 返回值 | `return {}` (空对象，SDK 要求) | N/A（demo 不模拟 hook 注册） |

## 相关文档

- 分析文档: [docs/nanoclaw.md — D5 上下文管理](../../docs/nanoclaw.md#5-上下文管理)
- 机制描述: [docs/nanoclaw.md — D12 对话归档](../../docs/nanoclaw.md#12-其他特色机制-平台维度)
- 原始源码: `projects/nanoclaw/container/agent-runner/src/index.ts` (588 行)
- 基于 commit: [`bc05d5f`](https://github.com/qwibitai/nanoclaw/tree/bc05d5fbea00cc81ca68c643b61c6f1b7ca8a147)
