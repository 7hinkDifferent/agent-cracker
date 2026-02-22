# Agent Cracker

系统性研究各类 Coding Agent 的实现原理和关键机制。

## Agent 列表

<!-- AGENT_TABLE_START -->

| Agent | Language | Category | Status | Repo |
|-------|----------|----------|--------|------|
| [aider](https://github.com/Aider-AI/aider) | Python | CLI | pending | `Aider-AI/aider` |
| [openhands](https://github.com/All-Hands-AI/OpenHands) | Python | 平台 | pending | `All-Hands-AI/OpenHands` |
| [cline](https://github.com/cline/cline) | TypeScript | IDE插件 | pending | `cline/cline` |
| [continue](https://github.com/continuedev/continue) | TypeScript | IDE插件 | pending | `continuedev/continue` |
| [goose](https://github.com/block/goose) | Rust | CLI | pending | `block/goose` |
| [codex-cli](https://github.com/openai/codex) | TypeScript | CLI | pending | `openai/codex` |
| [swe-agent](https://github.com/SWE-agent/SWE-agent) | Python | 研究 | pending | `SWE-agent/SWE-agent` |
| [bolt.new](https://github.com/stackblitz/bolt.new) | TypeScript | Web | pending | `stackblitz/bolt.new` |
| [devika](https://github.com/stitionai/devika) | Python | 自治 | pending | `stitionai/devika` |
| [gpt-engineer](https://github.com/gpt-engineer-org/gpt-engineer) | Python | CLI | pending | `gpt-engineer-org/gpt-engineer` |

<!-- AGENT_TABLE_END -->

## 快速开始

```bash
# 克隆项目（含 submodule）
git clone --recursive <this-repo-url>

# 或者克隆后再初始化 submodule
git clone <this-repo-url>
cd agent-cracker
./scripts/manage-submodules.sh init

# 添加单个 agent 的源码
./scripts/manage-submodules.sh add aider

# 查看 submodule 状态
./scripts/manage-submodules.sh status

# 为某个 agent 创建分析文档
./scripts/new-analysis.sh aider

# 更新 star 数
./scripts/update-stars.sh

# 从 agents.yaml 更新 README 表格
./scripts/gen-readme.sh
```

## 项目结构

```
agent-cracker/
├── agents.yaml              # Agent 目录（单一数据源）
├── projects/                 # Agent 源码（git submodule）
│   ├── aider/
│   ├── openhands/
│   └── ...
├── docs/                     # 分析文档
│   ├── TEMPLATE.md           # 分析模板
│   ├── aider.md
│   └── ...
├── demos/                    # 机制复现 demo
│   ├── TEMPLATE/
│   └── <agent>/              # 按 agent 分组
│       └── <mechanism>/      # 每个 demo 独立可运行
├── scripts/                  # 辅助脚本
│   ├── manage-submodules.sh  # Submodule 管理
│   ├── new-analysis.sh       # 生成分析文档
│   ├── update-stars.sh       # 更新 star 数
│   └── gen-readme.sh         # 更新 README 表格
└── prd.md                    # 项目需求文档
```

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
