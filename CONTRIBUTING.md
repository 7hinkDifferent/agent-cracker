# Contributing to Agent Cracker

感谢你对 Agent Cracker 的兴趣！以下是参与贡献的指南。

## 贡献方式

### 1. 分析新的 Agent

如果你想分析一个还没覆盖的 Coding Agent：

1. 在 `agents.yaml` 中添加 agent 信息
2. 用 `npm run add -- <agent>` 添加源码
3. 用 `/analyze-agent <agent>` 执行 8 维度分析（需要 Claude Code）
4. 或手动按 `docs/TEMPLATE.md` 格式编写分析文档

### 2. 创建 Demo

复现某个 agent 的特定机制：

1. 确保对应的分析文档已存在（`docs/<agent>.md`）
2. 用 `/create-demo <agent> <mechanism>` 创建 demo（需要 Claude Code）
3. 或手动按 `demos/TEMPLATE/README.md` 格式编写
4. 确保 demo 独立可运行，用 100-200 行核心代码复现

### 3. 改进现有内容

- 修复分析文档中的错误
- 补充遗漏的机制细节
- 改进 demo 的代码质量或文档

### 4. 报告问题

- 分析文档与最新源码不符
- Demo 无法运行
- 缺少重要的 agent 或机制

## 开发环境

```bash
git clone https://github.com/7hinkDifferent/agent-cracker.git
cd agent-cracker
npm run setup    # 安装 git hooks
npm run init     # 初始化 submodule
```

工具链要求见 [README.md](README.md#环境要求)。

## 代码规范

- **文档和注释**: 中文
- **代码标识符**: 英文
- **Python**: ≥3.10，用 uv 运行
- **Demo 原则**: 单一机制、最少依赖、独立可运行
- **Mini-agent**: 必须 import 兄弟 MVP demo 的模块，不重写代码

## 提交规范

- 提交前会自动运行 `lint.sh` 一致性检查
- 修改 demo 后需更新对应的 `demos/<agent>/README.md` 进度
- 如果改动影响 README 演示效果，可用 `npm run demo-gif` 重新录制动画
- 修改分析文档后需确认 `agents.yaml` 状态一致

## 文件对应关系

修改某个文件时，通常需要同步更新相关文件：

| 修改内容 | 需要同步 |
|---------|---------|
| 新增 demo 目录 | `demos/<agent>/README.md` 进度标记 |
| 新增分析文档 | `agents.yaml` status 字段 |
| 修改 `agents.yaml` | README 表格（pre-commit 自动更新） |
| 修改 demos/ | CLAUDE.md 进度（pre-commit 自动更新） |

## 问题反馈

请通过 [GitHub Issues](https://github.com/7hinkDifferent/agent-cracker/issues) 提交问题或建议。
