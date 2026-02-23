# Demo: Aider — Prompt Assembly（Prompt 组装）

## 目标

用最简代码复现 Aider 的多层 Prompt 动态组装机制。

## MVP 角色

Prompt 组装决定了发送给 LLM 的完整上下文——system prompt、文件内容、历史对话、格式规则如何拼接。它是 LLM 正确理解任务的前提。

## 原理

Aider 将发送给 LLM 的消息分为 **8 个段（ChatChunks）**，按固定顺序拼接：

```
[0] system         ← 角色定义 + 编辑格式规则 + system_reminder
[1] examples       ← few-shot 示例对话（user/assistant 交替）
[2] readonly_files  ← 只读参考文件（user/assistant 对）
[3] repo            ← RepoMap 仓库概览（user/assistant 对）
[4] done            ← 历史对话（可能已被摘要压缩）
[5] chat_files      ← 可编辑文件内容（user/assistant 对）
[6] cur             ← 当前轮用户消息
[7] reminder        ← system_reminder 再次注入（如果 token 允许）
```

关键设计：
- **system_reminder 双重注入**：格式规则在开头（system）和末尾（reminder）各出现一次，确保 LLM 在生成时"最近"看到过规则
- **模板变量动态替换**：`{fence}`、`{platform}`、`{final_reminders}` 等变量在运行时根据模型特性和用户配置填入
- **文件内容用 user/assistant 对注入**：每段文件内容都是一个 user 消息（"这是文件内容"）+ assistant 确认（"Ok"），避免角色混淆

## 运行

```bash
cd demos/aider/prompt-assembly
python main.py
```

无外部依赖，仅使用 Python 标准库。

## 文件结构

```
demos/aider/prompt-assembly/
├── README.md       # 本文件
└── main.py         # ChatChunks 组装 + 模板引擎 + 可视化输出
```

## 关键代码解读

### ChatChunks 数据结构

```python
@dataclass
class ChatChunks:
    system: list          # System prompt
    examples: list        # Few-shot 示例
    readonly_files: list  # 只读文件
    repo: list            # RepoMap
    done: list            # 历史对话
    chat_files: list      # 可编辑文件
    cur: list             # 当前消息
    reminder: list        # 末尾提醒

    def all_messages(self):
        return system + examples + readonly_files + repo + done + chat_files + cur + reminder
```

### 模板变量替换

```python
def fmt_system_prompt(self, template):
    final_reminders = []
    if self.model_lazy:
        final_reminders.append(LAZY_PROMPT)      # "You are diligent..."
    if self.model_overeager:
        final_reminders.append(OVEREAGER_PROMPT)  # "Do what they ask, no more."
    if self.user_language:
        final_reminders.append(f"Reply in {self.user_language}.")

    return template.format(
        fence=self.fence,                         # ``` 或 ````
        final_reminders="\n\n".join(final_reminders),
        platform=self.platform,                   # macOS/Linux/Windows
        shell_cmd_prompt=...,
    )
```

### system_reminder 双重注入

```python
# 第一次：嵌入 system prompt 末尾
main_sys += "\n\n" + fmt_system_prompt(SYSTEM_REMINDER)
chunks.system = [{"role": "system", "content": main_sys}]

# 第二次：作为独立消息追加到最后
chunks.reminder = [{"role": "system", "content": fmt_system_prompt(SYSTEM_REMINDER)}]
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 模板数量 | 8+ 种编辑格式各有独立 prompt 模板 | 仅 EditBlock 格式 |
| 变量数量 | 10+ 个模板变量 | 6 个核心变量 |
| Token 感知 | 计算 token 总量，空间不足时省略 reminder | 无 token 检查 |
| Example 模式 | 支持 examples_as_sys_msg（嵌入/独立两种） | 两种都实现 |
| RepoMap | tree-sitter AST + PageRank 生成 | 手写静态示例 |
| 历史摘要 | LLM 驱动的二分递归压缩 | 直接使用原始消息 |
| 图片支持 | 支持 vision 模型的图片嵌入 | 无 |

## 相关文档

- 分析文档: [docs/aider.md](../../../docs/aider.md)
- 原项目: https://github.com/Aider-AI/aider
- 基于 commit: `7afaa26`
- 核心源码: `aider/coders/base_coder.py`（format_chat_chunks / fmt_system_prompt）、`aider/coders/editblock_prompts.py`
