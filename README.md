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
git clone <this-repo-url>
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
