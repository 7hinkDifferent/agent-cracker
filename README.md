# Agent Cracker

系统性研究各类 Coding Agent 的实现原理和关键机制。

## Agent 列表

<!-- AGENT_TABLE_START -->

| Agent | Language | Category | Status | Repo |
|-------|----------|----------|--------|------|
| [aider](https://github.com/Aider-AI/aider) | Python | CLI | in-progress | `Aider-AI/aider` |
| [openhands](https://github.com/All-Hands-AI/OpenHands) | Python | 平台 | pending | `All-Hands-AI/OpenHands` |
| [cline](https://github.com/cline/cline) | TypeScript | IDE插件 | pending | `cline/cline` |
| [continue](https://github.com/continuedev/continue) | TypeScript | IDE插件 | pending | `continuedev/continue` |
| [goose](https://github.com/block/goose) | Rust | CLI | pending | `block/goose` |
| [codex-cli](https://github.com/openai/codex) | Rust | CLI | in-progress | `openai/codex` |
| [swe-agent](https://github.com/SWE-agent/SWE-agent) | Python | 研究 | pending | `SWE-agent/SWE-agent` |
| [bolt.new](https://github.com/stackblitz/bolt.new) | TypeScript | Web | pending | `stackblitz/bolt.new` |
| [devika](https://github.com/stitionai/devika) | Python | 自治 | pending | `stitionai/devika` |
| [gpt-engineer](https://github.com/gpt-engineer-org/gpt-engineer) | Python | CLI | pending | `gpt-engineer-org/gpt-engineer` |
| [pi-agent](https://github.com/badlogic/pi-mono) | TypeScript | CLI | in-progress | `badlogic/pi-mono` |

<!-- AGENT_TABLE_END -->

## 快速开始

```bash
# 克隆项目
git clone https://github.com/7hinkDifferent/agent-cracker.git
cd agent-cracker
npm run setup                # 安装 git hooks

# 初始化 submodule（shallow clone，只拉代码）
npm run init

# 添加单个 agent 的源码
npm run add -- aider

# 查看 submodule 状态
npm run status

# 为某个 agent 创建分析文档
npm run new-doc -- aider

# 一致性检查
npm run lint

# 更新 CLAUDE.md 进度段落
npm run progress

# 更新 star 数 / README 表格
npm run stars
npm run readme
```

## 项目结构

```
agent-cracker/
├── agents.yaml              # Agent 目录（单一数据源）
├── package.json             # npm scripts 统一入口
├── projects/                 # Agent 源码（git submodule, shallow clone）
│   └── <agent>/
├── docs/                     # 分析文档（8 维度深度分析）
│   ├── TEMPLATE.md
│   └── <agent>.md
├── demos/                    # 机制复现 demo（按 agent 分组）
│   ├── TEMPLATE/
│   └── <agent>/
│       ├── README.md         # Demo overview（机制清单 + 进度）
│       └── <mechanism>/      # 每个 demo 独立可运行
├── scripts/                  # 辅助脚本（通过 npm run 调用）
│   ├── manage-submodules.sh
│   ├── new-analysis.sh
│   ├── gen-readme.sh
│   ├── gen-progress.sh
│   ├── update-stars.sh
│   ├── lint.sh
│   └── githooks/pre-commit
└── .claude/
    ├── skills/               # Claude Code skills
    ├── hooks/                # 自动化 hooks
    └── settings.json
```

## 自动化

- **Git pre-commit hook**: agents.yaml 改动 → 自动更新 README 表格 + CLAUDE.md 进度；每次 commit 自动 lint 一致性检查
- **Claude hooks**: 对话中自动注入进度、语法检查 demo .py 文件、校验 agents.yaml 格式、结束时提醒更新文档

## 分析维度

每个 agent 的分析覆盖 8 个维度：

1. **Overview & Architecture** — 项目定位、技术栈、架构图
2. **Agent Loop** — 主循环机制（输入→思考→行动→观察）
3. **Tool/Action 系统** — Tool 注册、调用、执行
4. **Prompt 工程** — System prompt、动态组装
5. **上下文管理** — Context window 策略、文件选择
6. **错误处理与恢复** — 解析错误、重试机制
7. **关键创新点** — 独特设计、可借鉴模式
8. **跨 Agent 对比** — 横向对比分析

## 配合 Claude Code 使用

本项目内置了 Claude Code skills 和 hooks，推荐以下工作流：

### 可用 Skills

| 命令 | 用途 |
|------|------|
| `/analyze-agent <name>` | 对 agent 源码做 8 维度深度分析 |
| `/create-demo <agent> <mechanism>` | 创建机制复现 demo |
| `/audit-coverage [agent]` | 检查 MVP 覆盖缺口 |
| `/check-updates [agent]` | 检查上游更新、评估分析漂移 |
| `/guide <query>` | 学习引导：按需求推荐 docs/demos/源码 |
| `/sync-comparisons` | 同步跨 Agent 对比 |
| `/translate-doc <file>` | 中英文互译 |

### 自动化 Hooks

- **对话开始**: 自动注入项目状态（各 agent 分析进度、drift 检测）
- **编辑 demo**: 自动语法检查（Python/TypeScript/Rust）
- **提交代码**: 自动检查文档配套更新是否完整
- **对话结束**: 检查是否有遗漏的文档更新

### 推荐用法

1. 开启 Claude Code 对话，项目状态会自动注入
2. 用 `/guide` 探索你感兴趣的机制或获取学习路径
3. 用 `/analyze-agent` 分析新的 agent
4. 用 `/create-demo` 复现特定机制
5. 用 `/audit-coverage` 检查还有哪些 MVP 组件缺 demo

## 如何学习

### 按目标选择路径

**"我想了解某个 agent 怎么工作的"**
→ 读 `docs/<agent>.md`（8 维度分析），跑 `demos/<agent>/` 下的 demo

**"我想对比不同 agent 的某个机制"**
→ 读各 docs 的同一维度（如 D3 Tool 系统），或用 `/guide how do agents handle <topic>`

**"我想自己造一个 coding agent"**
→ 参考 `docs/<agent>.md` 的 7.5 节（MVP 组件清单），按 MVP → 进阶 → 串联的顺序学习 demo

**"我想从零学习 agent 基础概念"**
→ 先看任一 agent 的 `docs/<agent>.md` D1-D2，理解 agent loop 的核心模式，再逐步展开其他维度

### 推荐阅读顺序

1. **入门**: 挑一个你熟悉的 agent（如 aider），读 `docs/aider.md` 的 D1（概览）和 D2（主循环）
2. **上手**: 跑 `demos/aider/search-replace/`，对照 README 中的原始源码路径看原实现
3. **对比**: 读第二个 agent 的 docs（如 codex-cli），体会不同设计选择
4. **深入**: 按 D7.5 MVP 组件清单，逐个跑 demo，理解构建完整 agent 需要什么
5. **实践**: 参考 `demos/<agent>/mini-<agent>/` 串联 demo，尝试组装自己的 mini agent

### Demo 与原始源码的关系

每个 demo 的 README 都包含：
- **基于 commit**: 分析时的源码版本
- **核心源码**: 原项目中对应的文件路径（可直接在 `projects/<agent>/` 中查看）
- **与原实现的差异**: 简化了什么、保留了什么
