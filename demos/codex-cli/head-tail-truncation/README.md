# Demo: Codex CLI — 首尾保留截断（Head-Tail Truncation）

## 目标

用最简代码复现 Codex CLI 的输出截断机制：bytes/4 token 估算 + 首尾保留截断。

## 原理

当 tool 输出过长时，Codex CLI 不是简单截取前 N 个字符，而是**保留输出的头部和尾部**，中间插入截断标记。这样 LLM 既能看到输出的开头（通常是命令和前几行结果），也能看到结尾（通常是总结或错误信息）。

核心算法：
1. **bytes/4 token 估算**：`approx_token_count = (len_bytes + 3) / 4`，保守高估，不依赖 tokenizer
2. **首尾均分**：将 token 预算转为字节预算，50-50 分配给头部和尾部
3. **UTF-8 边界对齐**：在字符边界上切割，避免截断多字节字符
4. **截断标记**：在切割处插入 `…N tokens truncated…`
5. **多输出共享**：多个 tool 输出共享总 token 预算，逐个截断

## 运行

```bash
cd demos/codex-cli/head-tail-truncation
uv run python main.py
```

## 文件结构

```
demos/codex-cli/head-tail-truncation/
├── README.md    # 本文件
└── main.py      # 核心算法 + 演示（单文件）
```

## 关键代码解读

### bytes/4 token 估算

```python
APPROX_BYTES_PER_TOKEN = 4

def approx_token_count(text):
    byte_len = len(text.encode("utf-8"))
    return (byte_len + 3) // 4  # 向上取整
```

### 首尾均分截断

```python
def truncate_text(text, token_budget):
    byte_budget = token_budget * 4
    left_budget = byte_budget // 2
    right_budget = byte_budget - left_budget
    removed, prefix, suffix = split_string(text, left_budget, right_budget)
    return f"{prefix}\n…{removed_tokens} tokens truncated…\n{suffix}"
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 语言 | Rust（truncate.rs） | Python |
| TruncationPolicy | Bytes/Tokens 双模式 | 仅 token 模式 |
| 字节/字符 | 按 UTF-8 字节 + char_indices 切割 | 按 Python 字符遍历 |
| 输出格式 | "Total output lines: N" 前缀 | 无前缀 |
| 图片处理 | 跳过图片内容 | 无图片支持 |

## 相关文档

- 分析文档: [docs/codex-cli.md](../../../docs/codex-cli.md)
- 原项目: https://github.com/openai/codex
- 核心源码: `codex-rs/core/src/truncate.rs`
