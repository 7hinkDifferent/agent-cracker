# OpenClaw — Skills Injection

复现 OpenClaw 的 Skills 按需匹配注入 prompt 机制（Dimension 12: 其他特色机制）。

## 机制说明

OpenClaw 维护 51+ 个 Skill，每轮对话自动匹配最相关的 1 个注入到 system prompt。

```
用户消息 → 关键词匹配 skills/ 目录
  → 找到匹配 → 读取 SKILL.md → 注入到 system prompt 的 # Skills section
  → 无匹配 → 不注入
```

### 规则

- 每轮最多注入 **1 个** Skill（避免 prompt 膨胀）
- 按匹配分数排序，选最佳
- Skill 内容直接追加到 system prompt

## 对应源码

| 文件 | 作用 |
|------|------|
| `skills/*/SKILL.md` | 各 Skill 定义 |
| `src/agents/system-prompt.ts` | Skills section 注入 |

## 运行

```bash
uv run python main.py
```
