# aider — Deep Dive Analysis

> Auto-generated from template on 2026-02-22
> Repo: https://github.com/Aider-AI/aider
> Analyzed at commit: [`7afaa26`](https://github.com/Aider-AI/aider/tree/7afaa26f8b8b7b56146f0674d2a67e795b616b7c) (2026-02-22)

## 1. Overview & Architecture

### 项目定位

Aider 是一个**终端 AI 结对编程助手**，让开发者在命令行中直接与 LLM 协作编辑代码。它能理解整个代码库的上下文，进行多文件编辑，并自动 git commit 所有修改。

### 技术栈

- **语言**: Python 3.10+
- **包管理**: setuptools + setuptools_scm
- **入口**: `aider.main:main`（安装后命令行 `aider`）

| 类别 | 关键依赖 |
|------|----------|
| LLM 集成 | litellm, openai, tiktoken |
| CLI & I/O | prompt-toolkit, rich, configargparse |
| 版本控制 | gitpython |
| 代码分析 | tree-sitter, tree-sitter-language-pack, grep-ast, networkx, scipy |
| Diff/Patch | diff-match-patch |
| Web & API | fastapi, httpx, beautifulsoup4 |
| 数据处理 | pydantic, pyyaml, json5 |
| 音频输入 | pydub, sounddevice, soundfile |

### 核心架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    AIDER CLI (main.py)                       │
│              配置解析 / 模型加载 / Git 初始化                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    Coder.create()
                    (工厂模式，按 edit_format 选择子类)
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    EditBlockCoder    ArchitectCoder    WholeFileCoder ...
    (SEARCH/REPLACE)  (双模型规划)     (整文件替换)
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
              ┌────────────▼────────────┐
              │   BaseCoder.run()       │
              │   ┌──────────────────┐  │
              │   │ while True:      │  │
              │   │  get_input()     │  │  ← 用户输入
              │   │  run_one()       │  │  ← 预处理 + 反思循环
              │   │   └─ send_message│  │  ← LLM 调用 + 后处理
              │   │      ├─ apply    │  │  ← 解析 & 应用编辑
              │   │      ├─ commit   │  │  ← 自动 git commit
              │   │      ├─ lint     │  │  ← 自动 lint → 反思
              │   │      └─ test     │  │  ← 自动 test → 反思
              │   └──────────────────┘  │
              └───────────��─────────────┘
                           │
              ┌────────────▼────────────┐
              │    辅助系统              │
              │  ├─ RepoMap (仓库地图)  │  ← tree-sitter + PageRank
              │  ├─ Commands (斜杠命令) │  ← /add, /drop, /test ...
              │  ├─ ChatSummary (历史)  │  ← LLM 驱动的摘要
              │  └─ Linter (代码检查)   │
              └─────────────────────────┘
```

### 关键文件/目录

| 文件/目录 | 作用 |
|-----------|------|
| `aider/main.py` | CLI 入口，配置解析，Git 初始化，模型选择 |
| `aider/coders/base_coder.py` | 基类 Coder，包含主循环 `run()`, `run_one()`, `send_message()`, `send()` |
| `aider/coders/__init__.py` | 导出 13 种 Coder 子类 |
| `aider/coders/*_coder.py` | 各编辑格式实现（EditBlock, Whole, Patch, Architect 等） |
| `aider/coders/*_prompts.py` | 各格式对应的 prompt 模板 |
| `aider/commands.py` | 斜杠命令系统（`/add`, `/drop`, `/test` 等 40+ 命令） |
| `aider/repomap.py` | 仓库地图：tree-sitter 解析 + PageRank 排序 |
| `aider/history.py` | 对话历史摘要（LLM 驱动的二分压缩） |
| `aider/models.py` | LLM 模型注册和管理，通过 litellm 调用 |
| `aider/repo.py` | Git 仓库操作封装 |
| `aider/linter.py` | Lint 集成 |
| `aider/prompts.py` | 全局 prompt 模板（摘要、commit message 等） |
| `aider/io.py` | 终端 I/O 处理（rich 渲染） |

---

## 2. Agent Loop（主循环机制）

### 循环流程

Aider 采用**三层嵌套循环**架构：

1. **外层循环**（`main.py`）：处理 Coder 切换（如用户切换模型/编辑格式）
2. **中层循环**（`run()`）：REPL 交互循环，获取用户输入 → 处理 → 显示结果
3. **内层循环**（`run_one()` 中的反思循环）：lint/test 失败后自动重试，最多 3 次

```
外层 (main.py):
  while True:
    try:
      coder.run()               ← 中层循环
    except SwitchCoder:
      coder = Coder.create(...)  ← 切换 Coder（模型/格式变更）

中层 (run()):
  while True:
    user_message = get_input()   ← 等待用户输入
    run_one(user_message)        ← 处理单次交互
    show_undo_hint()             ← 提示可 /undo

内层 (run_one()):
  while message:
    send_message(message)        ← 调用 LLM + 后处理
    if reflected_message:        ← lint/test/parse 失败触发反思
      if num_reflections >= 3:
        break                    ← 最多反思 3 次
      message = reflected_message
    else:
      break
```

### 终止条件

| 条件 | 触发方式 | 行为 |
|------|---------|------|
| 正常退出 | `Ctrl+D` (EOFError) | 优雅退出 `run()` |
| 强制退出 | 2 秒内连按两次 `Ctrl+C` | `sys.exit()` |
| 单消息模式 | `--message` 参数 | 执行一次后返回 |
| 上下文耗尽 | ContextWindowExceededError | 显示错误，终止本轮 |
| 反思上限 | `num_reflections >= 3` | 警告用户，停止本轮 |
| Coder 切换 | `SwitchCoder` 异常 | 外层捕获，创建新 Coder |

### 关键代码

**中层 REPL 循环** (`base_coder.py:876`):
```python
def run(self, with_message=None, preproc=True):
    try:
        if with_message:
            self.io.user_input(with_message)
            self.run_one(with_message, preproc)
            return self.partial_response_content

        while True:
            try:
                if not self.io.placeholder:
                    self.copy_context()
                user_message = self.get_input()
                self.run_one(user_message, preproc)
                self.show_undo_hint()
            except KeyboardInterrupt:
                self.keyboard_interrupt()
    except EOFError:
        return
```

**反思循环** (`base_coder.py:932`):
```python
while message:
    self.reflected_message = None
    list(self.send_message(message))
    if not self.reflected_message:
        break
    if self.num_reflections >= self.max_reflections:
        self.io.tool_warning(f"Only {self.max_reflections} reflections allowed, stopping.")
        return
    self.num_reflections += 1
    message = self.reflected_message
```

**`send_message()` 后处理**（简化版，`base_coder.py:1560`）:
```python
# 1. 解析并应用代码编辑
edited = self.apply_updates()
if edited:
    self.auto_commit(edited)                    # 自动 git commit

# 2. 自动 lint → 失败则触发反思
if edited and self.auto_lint:
    lint_errors = self.lint_edited(edited)
    if lint_errors:
        self.reflected_message = lint_errors     # 反思：修复 lint 错误
        return

# 3. 自动 test → 失败则触发反思
if edited and self.auto_test:
    test_errors = self.commands.cmd_test(self.test_cmd)
    if test_errors:
        self.reflected_message = test_errors     # 反思：修复 test 错误
        return
```

---

## 3. Tool/Action 系统

### Tool 注册机制

Aider 有**两套**独立的 Tool 系统：

#### 1. 用户斜杠命令（`/commands`）

基于**命名约定自动发现**：`Commands` 类中所有 `cmd_*` 方法自动注册为斜杠命令。

```python
# commands.py
def get_commands(self):
    commands = []
    for attr in dir(self):
        if not attr.startswith("cmd_"):
            continue
        cmd = attr[4:]               # 去掉 "cmd_" 前缀
        cmd = cmd.replace("_", "-")  # 下划线转连字符
        commands.append("/" + cmd)   # 加 "/" 前缀
    return commands
```

匹配和分发支持**命令缩写**（如 `/a` 可匹配 `/add`，前提是无歧义）：
```python
def matching_commands(self, inp):
    first_word = inp.strip().split()[0]
    all_commands = self.get_commands()
    return [cmd for cmd in all_commands if cmd.startswith(first_word)]
```

#### 2. LLM 函数调用（Function Calling）

部分 Coder 子类通过 `functions` 类属性定义 JSON Schema，使用 OpenAI tools 格式强制 LLM 结构化输出：

```python
# wholefile_func_coder.py
class WholeFileFunctionCoder(Coder):
    functions = [
        dict(
            name="write_file",
            description="create or update one or more files",
            parameters=dict(
                type="object",
                required=["explanation", "files"],
                properties=dict(
                    explanation=dict(type="string", ...),
                    files=dict(type="array", items=dict(...)),
                ),
            ),
        ),
    ]
```

转换为 OpenAI tools 格式（`models.py:991`）：
```python
if functions is not None:
    kwargs["tools"] = [dict(type="function", function=functions[0])]
    kwargs["tool_choice"] = {"type": "function", "function": {"name": functions[0]["name"]}}
```

### Tool 列表

**用户斜杠命令（40+ 个）**：

| 命令 | 功能 | 类别 |
|------|------|------|
| `/add` | 添加文件到聊天上下文 | 文件管理 |
| `/drop` | 从聊天中移除文件 | 文件管理 |
| `/read-only` | 添加只读文件 | 文件管理 |
| `/ls` | 列出所有已知文件 | 文件管理 |
| `/model` | 切换主模型 | 模型管理 |
| `/editor-model` | 切换编辑器模型 | 模型管理 |
| `/chat-mode` | 切换聊天模式 | 模型管理 |
| `/code` | 代码编辑模式 | 模式切换 |
| `/ask` | 问答模式（不编辑） | 模式切换 |
| `/architect` | 架构师模式（双模型） | 模式切换 |
| `/commit` | 提交外部编辑 | Git |
| `/undo` | 撤销上一次 aider commit | Git |
| `/diff` | 显示上次消息以来的 diff | Git |
| `/git` | 运行 git 命令 | Git |
| `/lint` | Lint 并修复文件 | 代码质量 |
| `/test` | 运行测试命令 | 代码质量 |
| `/run` | 运行 shell 命令（别名 `!`） | 工具 |
| `/voice` | 语音输入 | 输入 |
| `/paste` | 粘贴图片/文本 | 输入 |
| `/web` | 抓取网页转 markdown | 工具 |
| `/map` | 显示仓库地图 | 上下文 |
| `/tokens` | 显示 token 用量 | 上下文 |
| `/clear` | 清除聊天历史 | 会话 |
| `/reset` | 清除所有文件和历史 | 会话 |
| `/settings` | 显示当前设置 | 信息 |
| `/help` | 帮助信息 | 信息 |
| `/exit` | 退出（别名 `/quit`） | 会话 |

### Tool 调用流程

LLM **不能调用斜杠命令**。LLM 只能通过以下两种方式"使用工具"：

1. **文本解析方式**（主要）：LLM 在回复中包含 SEARCH/REPLACE 块、整文件、diff 等格式，由 Coder 子类的 `get_edits()` 解析并应用
2. **函数调用方式**（部分格式）：通过 OpenAI function calling，LLM 返回结构化 JSON，由 `parse_partial_args()` 解析

```
用户输入 "/add file.py"
    → Commands.run("/add file.py")
    → matching_commands() → ["/add"]
    → do_run("add", "file.py")
    → cmd_add("file.py")
    → self.coder.abs_fnames.add(abs_path)

LLM 返回 SEARCH/REPLACE 块
    → send_message() 获取 LLM 响应
    → apply_updates()
    → get_edits() → 解析编辑块
    → apply_edits() → 写入文件
    → auto_commit() → git commit
```

---

## 4. Prompt 工程

### System Prompt 结构

Aider 采用**多态 Prompt 系统**：基类 `CoderPrompts` 定义通用结构，每种编辑格式的子类覆盖特定部分。

System Prompt 由以下部分组成：

1. **主系统提示**（`main_system`）：角色定义 + 编辑格式说明 + 规则
2. **示例对话**（`example_messages`）：few-shot 演示期望的输出格式
3. **系统提醒**（`system_reminder`）：重要规则的重复强调
4. **行为修饰器**：根据模型特性动态添加
   - `lazy_prompt`：鼓励模型不偷懒（"You are diligent and tireless!"）
   - `overeager_prompt`：告诫模型不过度修改（"Do what they ask, but no more."）
5. **Shell 命令提示**：允许 LLM 建议 shell 命令（平台感知）
6. **语言指令**：按用户语言回复

### 动态 Prompt 组装

`fmt_system_prompt()` 在运行时动态组装 prompt：

```python
def fmt_system_prompt(self, prompt):
    final_reminders = []

    # 1. 模型行为适配
    if self.main_model.lazy:
        final_reminders.append(self.gpt_prompts.lazy_prompt)
    if self.main_model.overeager:
        final_reminders.append(self.gpt_prompts.overeager_prompt)

    # 2. 用户语言
    user_lang = self.get_user_language()
    if user_lang:
        final_reminders.append(f"Reply in {user_lang}.\n")

    # 3. Shell 命令能力（平台感知）
    platform_text = self.get_platform_info()
    shell_cmd_prompt = self.gpt_prompts.shell_cmd_prompt.format(platform=platform_text)

    # 4. 代码围栏选择（三重 vs 四重反引号）
    if self.fence[0] == "`" * 4:
        quad_backtick_reminder = "IMPORTANT: Use *quadruple* backticks..."

    # 5. 模板替换
    prompt = prompt.format(
        fence=self.fence,
        final_reminders="\n\n".join(final_reminders),
        platform=platform_text,
        shell_cmd_prompt=shell_cmd_prompt,
        language=language,
    )
    return prompt
```

消息上下文的完整组装（`format_chat_chunks()`）：

```
[system]     main_system + example_messages + system_reminder
[user/asst]  done_messages（历史对话，可能已被摘要）
[user]       repo_content_prefix + RepoMap 输出
[user]       read_only_files_prefix + 只读文件内容
[user]       files_content_prefix + 聊天文件内容
[user/asst]  cur_messages（当前轮对话）
[system]     system_reminder（末尾再次提醒）
```

### Prompt 模板位置

| 文件 | 编辑格式 | 核心特征 |
|------|---------|---------|
| `aider/coders/editblock_prompts.py` | editblock (默认) | SEARCH/REPLACE 块规则 |
| `aider/coders/wholefile_prompts.py` | whole | 整文件输出规则 |
| `aider/coders/udiff_prompts.py` | udiff | `diff -U0` 格式规则 |
| `aider/coders/patch_prompts.py` | patch | V4A diff 格式规则 |
| `aider/coders/architect_prompts.py` | architect | 规划指令（不写代码） |
| `aider/coders/ask_prompts.py` | ask | 只分析不修改 |
| `aider/coders/context_prompts.py` | context | 文件选择指令 |
| `aider/coders/base_prompts.py` | — | 基类通用模板 |
| `aider/prompts.py` | — | 全局模板（摘要、commit message） |

---

## 5. 上下文管理

### 上下文窗口策略

Aider 采用**多层策略**管理有限的 context window：

1. **Token 预算分配**：RepoMap 有独立的 token 预算（默认 1024 tokens），与文件内容和历史分开管理
2. **发送前检查**：`check_tokens()` 在调用 LLM 前验证总 token 数不超限
3. **超限处理**：ContextWindowExceededError 触发清理提示（`/drop`, `/clear`）
4. **续写机制**：FinishReasonLength 时追加 assistant 前缀消息继续生成

**Token 估算优化**（大文件采样估算，不逐字计数）：
```python
def token_count(self, text):
    if len(text) < 200:
        return self.main_model.token_count(text)  # 精确计数
    # 采样 ~100 行估算
    lines = text.splitlines(keepends=True)
    step = len(lines) // 100 or 1
    sample = "".join(lines[::step])
    return self.main_model.token_count(sample) / len(sample) * len(text)
```

### 文件/代码的 context 策略

**RepoMap — 核心创新**（`repomap.py`）

Aider 使用 tree-sitter 解析代码 AST，提取函数/类定义和引用关系，构建依赖图，然后用 **PageRank 算法**排序最相关的代码片段。

流程：

1. **AST 解析**：tree-sitter 提取每个文件的 `def`（定义）和 `ref`（引用）标签
2. **构建依赖图**：文件 A 引用了文件 B 中定义的符号 → A→B 边
3. **PageRank 排序**：用户聊天文件和提到的标识符获得更高权重
4. **Token 约束**：二分搜索找到能塞进 token 预算的最优文件子集
5. **渲染输出**：用 `TreeContext` 只展示相关行及其上下文

**PageRank 个性化权重**：
- 聊天文件中引用的符号：**50x** 加成（最强信号）
- 用户消息中提及的标识符：**10x** 加成
- 命名良好的标识符（8+ 字符，camelCase/snake_case）：**10x** 加成
- 私有符号（`_` 开头）：**0.1x** 降权
- 定义在 5+ 处的符号：**0.1x** 降权

**三层降级策略**（`get_repo_map()`）：
```python
# Tier 1: 聚焦地图（基于聊天文件 + 提及）
repo_content = self.repo_map.get_repo_map(chat_files, other_files, mentioned_fnames, mentioned_idents)

# Tier 2: 全局地图（忽略聊天文件上下文）
if not repo_content:
    repo_content = self.repo_map.get_repo_map(set(), all_files, mentioned_fnames, mentioned_idents)

# Tier 3: 纯 PageRank 地图（无提及信息）
if not repo_content:
    repo_content = self.repo_map.get_repo_map(set(), all_files)
```

### 对话历史管理

`ChatSummary`（`history.py`）使用 **LLM 驱动的二分递归摘要**：

```python
def summarize_real(self, messages, depth=0):
    if total_tokens <= self.max_tokens:
        return messages  # 不需要摘要

    # 二分：保留最新消息，摘要较旧消息
    half_budget = self.max_tokens // 2
    split_index = find_split_point(messages, half_budget)

    head = messages[:split_index]   # 旧消息 → 摘要
    tail = messages[split_index:]   # 新消息 → 保留

    summary = self.summarize_all(head)  # 调用 LLM 摘要
    return self.summarize_real(summary + tail, depth + 1)  # 递归
```

摘要 prompt 要求以用户第一人称撰写（"I asked you..."），必须保留函数名、库名、文件名等关键信息。

摘要模型优先使用 `weak_model`（便宜/快速），失败则降级到 `main_model`。摘要在**后台线程**中异步执行。

---

## 6. 错误处理与恢复

### LLM 输出解析错误

当 LLM 返回的编辑块格式不正确时，Aider 采用**多级容错解析**：

1. **精确匹配**：逐行对比 SEARCH 块和文件内容
2. **空白容忍**：忽略首尾空白差异（fuzz level 1-100）
3. **省略号处理**：支持 `...` 行代表省略的代码
4. **编辑距离匹配**：80% 相似度阈值的模糊匹配
5. **跨文件搜索**：如果目标文件匹配失败，尝试其他聊天文件

```python
# editblock_coder.py — 解析失败处理
if failed:
    res = f"# {len(failed)} SEARCH/REPLACE blocks failed to match!\n"
    # 提供详细的失败信息：显示相似行、已存在的替换内容等
    raise ValueError(res)

# base_coder.py — 捕获解析错误，触发反思
except ValueError as err:
    self.num_malformed_responses += 1
    self.io.tool_error("The LLM did not conform to the edit format.")
    self.reflected_message = str(err)  # 将错误信息作为反思内容
```

### Tool 执行失败

**API 调用失败**：指数退避重试（0.125s → 0.25s → ... → 最大 32s）

```python
retry_delay = 0.125
while True:
    try:
        yield from self.send(messages, functions=self.functions)
        break
    except litellm_ex.exceptions_tuple() as err:
        if ex_info.name == "ContextWindowExceededError":
            exhausted = True
            break           # 上下文耗尽不重试
        retry_delay *= 2
        if retry_delay > 32:
            break           # 超时放弃
        time.sleep(retry_delay)
```

**Git 操作失败**：捕获 `ANY_GIT_ERROR`，记录错误但不中断流程。

### 重试机制

| 错误类型 | 重试策略 | 最大次数 |
|---------|---------|---------|
| 编辑块解析失败 | 反思循环 + reflected_message | 3 次 |
| Lint 错误 | 反思循环（需用户确认） | 3 次 |
| Test 失败 | 反思循环（需用户确认） | 3 次 |
| API 瞬时错误 | 指数退避 | ~8 次（0.125s→32s） |
| 上下文耗尽 | 不重试，提示用户 `/drop`, `/clear` | 0 |
| Git 错误 | 不重试，记录并继续 | 0 |

---

## 7. 关键创新点

### 独特设计

#### 1. RepoMap — 基于 AST 的仓库语法地图

Aider 最独特的创新。用 tree-sitter 解析所有文件的 AST，提取定义和引用关系，构建依赖图，用 PageRank 算法选出与当前任务最相关的代码片段。这让 LLM 即使不读完整文件，也能"看到"整个仓库的结构。

- **语言感知**：支持 20+ 编程语言的 AST 解析
- **高效缓存**：SQLite 缓存 + mtime 失效策略
- **Token 约束**：二分搜索确保输出在 token 预算内

#### 2. 多 Coder 架构 — 编辑格式多态

不同的 LLM 擅长不同的输出格式。Aider 通过**工厂模式 + 继承多态**支持 12+ 种 Coder 子类，每种有独立的 prompt、解析器和应用逻辑。可在会话中随时切换。

| Coder | 格式 | 适用场景 |
|-------|------|---------|
| EditBlockCoder | SEARCH/REPLACE | 默认，精确行级编辑 |
| WholeFileCoder | 整文件 | 新文件或大改 |
| PatchCoder | V4A diff | 复杂多文件修改 |
| ArchitectCoder | 自然语言规划 | 双模型，规划+执行分离 |
| AskCoder | 无编辑 | 纯问答 |
| ContextCoder | 文件列表 | 智能文件选择 |

#### 3. Architect 模式 — 双模型协作

架构师模式将编码任务分为两阶段：
- **规划阶段**：主模型（如 Claude/GPT-4）分析需求并输出修改方案
- **执行阶段**：编辑器模型（可以是更便宜的模型）实现具体代码修改

```python
class ArchitectCoder(AskCoder):
    def reply_completed(self):
        # 1. 获取架构师的规划
        content = self.partial_response_content
        # 2. 创建编辑器 Coder（可能使用不同模型）
        editor_coder = Coder.create(main_model=editor_model, edit_format=editor_format, ...)
        # 3. 将规划作为指令发送给编辑器
        editor_coder.run(with_message=content, preproc=False)
```

#### 4. Git 深度集成

- **自动 commit**：每次成功编辑后自动 git commit，commit message 由 LLM 生成
- **一键回滚**：`/undo` 撤销上一次 aider 的 commit
- **修改追踪**：区分 aider 的 commit 和用户的 commit
- **脏文件检测**：启动时检测未提交的修改

#### 5. 反思循环（Reflection Loop）

编辑 → lint → test 的自动化闭环。Lint/Test 失败后，将错误信息自动反馈给 LLM 尝试修复，最多重试 3 次。

### 值得借鉴的模式

1. **命名约定注册**：`cmd_*` 方法自动成为斜杠命令，零配置，极易扩展
2. **PageRank 用于代码相关性排序**：将代码依赖建模为图，用成熟算法排序
3. **Token 采样估算**：大文件不逐字计数，采样 100 行估算，性能提升显著
4. **二分搜索 Token 约束**：在 token 预算内找到最优内容集合
5. **SwitchCoder 异常模式**：用异常实现状态机切换，简洁优雅
6. **多级容错解析**：精确匹配 → 空白容忍 → 模糊匹配，最大化编辑成功率
7. **后台线程摘要**：历史摘要异步执行，不阻塞用户交互

---

## 7.5 MVP 组件清单

基于以上分析，构建最小可运行版本需要以下组件：

| 组件 | 对应维度 | 核心文件 | 建议语言 | 语言理由 |
|------|----------|----------|----------|----------|
| 主循环 (core-loop) | D2 | `aider/coders/base_coder.py` (run / run_one) | Python | 原生 Python，无特殊语言依赖 |
| 编辑应用 (search-replace) | D3 | `aider/coders/editblock_coder.py`, `aider/coders/editblock_fenced.py` | Python | 正则解析 + 字符串处理 |
| Prompt 组装 (prompt-assembly) | D4 | `aider/coders/base_coder.py` (format_messages), `aider/prompts/` | Python | 字符串模板拼接 |
| LLM 响应解析 (llm-response-parsing) | D2/D6 | `aider/coders/editblock_coder.py`, `aider/coders/base_coder.py` | Python | markdown 解析 + 多格式适配 |

**说明**: aider 不使用 function-calling，因此无需 "Tool 分发" 组件。编辑指令通过 LLM 文本响应中的 SEARCH/REPLACE 块传递。

---

## 8. 跨 Agent 对比

### vs 其他 agent

| 维度 | aider | 通用 Agent 模式 |
|------|-------|----------------|
| Agent Loop | 三层嵌套（外层切换 + REPL + 反思循环） | 通常单层 while 循环 |
| Tool 系统 | 双轨：用户命令（约定发现）+ LLM 函数调用 | 通常统一的 tool 注册表 |
| Context 策略 | tree-sitter AST + PageRank + 二分搜索 | 通常简单的文件列表或 embedding 检索 |
| 编辑方式 | 12+ 种编辑格式，可运行时切换 | 通常固定 1-2 种格式 |
| 错误处理 | 多级容错 + 反思循环 + 指数退避 | 通常简单重试或报错 |
| Git 集成 | 深度集成（自动 commit, undo, diff） | 通常无或仅基础集成 |
| 模型支持 | 通过 litellm 支持几乎所有 LLM | 通常绑定特定提供商 |

### 总结

Aider 是一个**成熟、工程化程度极高的终端 AI 编程助手**。其核心竞争力在于三点：

1. **RepoMap**：通过 tree-sitter AST 解析 + PageRank 排序，在有限的 context window 中塞入最相关的代码上下文，这是其他 agent 少有的创新
2. **多 Coder 多态架构**：通过工厂模式和继承，支持 12+ 种编辑格式的无缝切换，适配不同模型的输出特性
3. **反思闭环**：编辑 → lint → test → 自动修复的全自动闭环，大幅减少人工干预

适用场景：需要在终端环境中进行多文件代码编辑的开发者，特别是已有 git 工作流的项目。不适合：没有代码库的绿地项目（RepoMap 无用武之地），或需要 GUI 交互的场景。
