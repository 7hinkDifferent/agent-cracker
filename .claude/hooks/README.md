# Claude Code Hooks

本目录包含 Claude Code 自动化 hooks，在 `.claude/settings.json` 中配置。

## Hook 列表

### 1. `session-status.sh` — Session 状态注入

- **触发**: `SessionStart`（每次对话开始/恢复时）
- **作用**: 读取 `agents.yaml`，将各 agent 的分析状态和 demo 数量注入对话上下文
- **输出示例**:
  ```
  Current project status:
    - aider: in-progress
    - openhands: pending
    ...
  Total demos: 4
  ```

### 2. `demo-syntax-check.sh` — Demo 语法检查

- **触发**: `PostToolUse`（Write 或 Edit 工具执行后）
- **条件**: 仅检查 `demos/` 目录下的 `.py` 文件
- **作用**: 用 `python3 -m py_compile` 做语法检查，发现错误立即通过 `systemMessage` 反馈给 Claude
- **不依赖**: 任何外部包，仅用系统 Python

### 3. `validate-agents-yaml.sh` — agents.yaml 保护

- **触发**: `PostToolUse`（Write 或 Edit 工具执行后）
- **条件**: 仅检查 `agents.yaml` 文件
- **作用**: 验证 YAML 基本结构——必须有 `agents:` 顶层 key，每个 agent 必须有 `name`、`repo`、`status` 字段，status 值必须是 `pending`/`in-progress`/`done`
- **不依赖**: PyYAML，用纯 bash + grep 实现

### 4. Stop prompt（配置在 settings.json 中）

- **触发**: `Stop`（Claude 结束回答前）
- **类型**: `prompt`（让 LLM 判断）
- **作用**: 检查本次对话是否完成了 agent 分析或创建了 demo，但忘记更新 `agents.yaml` 的 status 字段。如果遗漏了，阻止 Claude 结束并提醒更新

## 测试 Hook

```bash
# 测试 session-status
CLAUDE_PROJECT_DIR="$(pwd)" .claude/hooks/session-status.sh < /dev/null

# 测试 demo-syntax-check
echo '{"tool_input":{"file_path":"demos/aider/search-replace/parser.py"}}' | .claude/hooks/demo-syntax-check.sh

# 测试 validate-agents-yaml
echo '{"tool_input":{"file_path":"agents.yaml"}}' | .claude/hooks/validate-agents-yaml.sh
```
