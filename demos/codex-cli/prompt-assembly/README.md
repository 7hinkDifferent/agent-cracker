# Demo: Codex CLI — 多层 Prompt 组装（Prompt Assembly）

## 目标

用最简代码复现 Codex CLI 的 7 层 prompt 模板叠加组装机制。

## 原理

Codex CLI 的 system prompt 不是一个固定字符串，而是由 `build_initial_context()` 按顺序叠加多层模板动态生成。每层负责一个关注点，最终组合成完整的 system prompt。

7 层叠加顺序：

| 层 | 名称 | 来源 | 作用 |
|----|------|------|------|
| 1 | Base Instructions | `templates/base.md` | 角色定义 + 格式规则 + 工具规范 |
| 2 | Personality | `templates/personalities/` | 人格注入（pragmatic / friendly） |
| 3 | Policy Constraints | `DeveloperInstructions::from_policy()` | 沙箱策略 + 审批策略 → 权限约束 |
| 4 | Collaboration Mode | `templates/collaboration_mode/` | 协作模式（default / plan） |
| 5 | Memory Tool | `templates/memories/` | 长期记忆管理指令 |
| 6 | Custom Instructions | `developer_instructions` | 用户自定义指令 |
| 7 | Slash Command | `~/.codex/prompts/` | 用户 slash 命令扩展 |

关键设计：`{{ variable }}` 模板变量在组装时被替换（如人格模板注入到基础指令中）。

## 运行

```bash
cd demos/codex-cli/prompt-assembly
uv run python main.py
```

## 文件结构

```
demos/codex-cli/prompt-assembly/
├── README.md           # 本文件
├── assembler.py        # 7 层组装逻辑
├── main.py             # 演示：逐层叠加、人格切换、模式对比
└── templates/          # 简化版模板
    ├── base.md                 # 基础指令
    ├── personality_pragmatic.md # 务实人格
    ├── personality_friendly.md  # 友好人格
    ├── mode_default.md         # 默认模式
    └── mode_plan.md            # 规划模式
```

## 关键代码解读

### 模板变量替换

```python
def _substitute(template, variables):
    # "{{ personality }}" → 替换为人格模板内容
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, template)
```

### 7 层组装

```python
def assemble(config) -> list[Layer]:
    # 1. 加载 base.md + 注入 personality
    # 2. 添加 personality 层
    # 3. 生成 policy constraints（sandbox + approval）
    # 4. 加载 collaboration mode 模板
    # 5. 添加 memory tool 指令
    # 6. 添加 custom instructions
    # 7. 添加 slash command
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 语言 | Rust（codex.rs） | Python |
| 模板 | 完整版（每层 50-200 行） | 简化版（每层 5-10 行） |
| 发现 | 文件系统 prompt 发现 + frontmatter 解析 | 固定模板文件 |
| 模型适配 | 按模型选择不同基础指令 | 固定一套 |
| 功能开关 | Feature flag 控制各层启用 | 简化为 bool 开关 |

## 相关文档

- 分析文档: [docs/codex-cli.md](../../../docs/codex-cli.md)
- 原项目: https://github.com/openai/codex
- 核心源码: `codex-rs/core/src/codex.rs` (`build_initial_context()`)
- 模板目录: `codex-rs/core/templates/`
