# Agent Cracker

系统性研究开源 Coding Agent 的实现原理，提取关键机制并用最简代码复现。

## 项目结构

```
agent-cracker/
├── agents.yaml              # Agent 目录（单一数据源，所有脚本从此读取）
├── package.json             # npm scripts 统一入口
├── projects/                 # Agent 源码（git submodule, shallow clone）
│   └── <agent>/
├── docs/                     # 分析文档（8 维度深度分析）
│   ├── TEMPLATE.md
│   └── <agent>.md
├── demos/                    # 机制复现 demo（按 agent 分组）
│   ├── TEMPLATE/
│   └── <agent>/
│       └── <mechanism>/      # 每个 demo 独立可运行
├── scripts/                  # 辅助脚本（通过 npm run 调用）
└── .claude/
    ├── skills/               # Claude Code skills
    │   ├── analyze-agent/    # /analyze-agent <name> — 8 维度分析
    │   ├── check-updates/   # /check-updates — 检查上游更新、评估分析漂移
    │   ├── create-demo/      # /create-demo <agent> <mechanism> — 创建机制 demo
    │   ├── sync-comparisons/ # /sync-comparisons — 同步跨 Agent 对比（Dimension 8）
    │   ├── translate-doc/    # 中英文翻译
    │   └── update-repo/      # 更新 submodule 和 README
    ├── hooks/                # 自动化 hooks
    │   ├── session-status.sh       # SessionStart: 注入 agents.yaml 进度
    │   ├── pre-commit-check.sh    # PreToolUse: 提交前任务完成检查
    │   ├── demo-syntax-check.sh    # PostToolUse: demos/ 下 .py 语法检查
    │   └── validate-agents-yaml.sh # PostToolUse: agents.yaml 格式校验
    └── settings.json         # Hooks 配置 + Stop prompt 完成提醒
```

## 常用命令

```bash
npm run status               # 查看 submodule 状态
npm run add -- <agent>       # 添加 agent 源码（shallow clone）
npm run update -- <agent>    # 更新 agent 源码
npm run init                 # 初始化所有 submodule
npm run new-doc -- <agent>   # 从模板创建分析文档
npm run readme               # 从 agents.yaml 更新 README 表格
npm run stars                # 查询 GitHub star 数
npm run lint                 # 一致性检查（agents.yaml/docs/demos/README 是否对齐）
npm run progress             # 更新 CLAUDE.md 进度段落
npm run setup                # 安装 git hooks（clone 后执行一次）
```

## 工作流

1. **添加 agent**: `npm run add -- <name>` → 源码到 `projects/<name>/`
2. **分析 agent**: `/analyze-agent <name>` → 输出到 `docs/<name>.md`
3. **创建 demo**: `/create-demo <agent> <mechanism>` → 输出到 `demos/<agent>/<mechanism>/`

## 约定

- **语言**: 文档和注释用中文，代码标识符用英文
- **Demo 目录**: `demos/<agent>/<mechanism>/`，按 agent 分组，每个 mechanism 一个子目录
- **Demo Overview**: 每个 agent 的 `demos/<agent>/README.md` 维护机制清单（`- [x]`/`- [ ]`），用于追踪进度和判断 status
- **Demo 原则**: 单一机制、最少依赖、独立可运行
- **包管理**: 使用 `uv` 运行 Python demo（`uv run --with <deps> python main.py`）
- **LLM 调用**: Demo 中使用 `litellm` 库，支持通过环境变量 `DEMO_MODEL` 配置模型
- **数据源**: `agents.yaml` 是 agent 列表的唯一数据源
- **Agent status**: pending → in-progress → done，分析或 demo 完成后必须更新
- **Commit 跟踪**: 分析完成后自动记录 analyzed_commit/analyzed_date 到 agents.yaml，demo 记录基于的 commit
- **Submodule**: 默认 shallow clone（--depth=1），只拉代码不拉历史

## 自动化

### Git hooks（commit 时自动触发）

| Hook | 触发条件 | 作用 |
|------|----------|------|
| `pre-commit` | agents.yaml 改动 | 自动更新 README 表格（`gen-readme.sh`） |
| `pre-commit` | agents.yaml 或 demos/ 改动 | 自动更新 CLAUDE.md 进度段落（`gen-progress.sh`） |
| `pre-commit` | 每次 commit | 跑 `lint.sh` 一致性检查 |

Git hooks 存放在 `scripts/githooks/`，`npm run setup` 安装到 `.git/hooks/`。

### Claude hooks（对话中自动触发）

| Hook | 触发时机 | 作用 |
|------|----------|------|
| `session-status.sh` | 每次对话开始 | 从 agents.yaml 读取各 agent 状态，注入为上下文，检测本地 drift |
| `pre-commit-check.sh` | 执行 git commit 前 | 检查未暂存文档、缺少配套变更等遗漏（含 analyzed_commit 同步），阻断并提示修复 |
| `demo-syntax-check.sh` | 编辑 demos/ 下 .py 文件后 | 自动 py_compile 语法检查，错误立即反馈 |
| `validate-agents-yaml.sh` | 编辑 agents.yaml 后 | 校验 YAML 结构完整性（必须有 name/repo/status，analyzed_commit 格式） |
| Stop prompt | Claude 结束回答前 | 按文件→文档映射规则检查是否有文档/配置遗漏未更新 |

## 当前进度

<!-- PROGRESS_START -->
- **进行中**: aider, codex-cli, pi-agent
- **待分析**: openhands, cline, continue, goose, swe-agent, bolt.new, devika, gpt-engineer

Demo 覆盖:
- **aider**: 4/8 (repomap, search-replace, reflection, architect)
- **codex-cli**: 4/6 (approval-policy, head-tail-truncation, network-policy, prompt-assembly)
- **pi-agent**: 4/6 (event-stream, pluggable-ops, steering-queue, structured-compaction)

<!-- PROGRESS_END -->
