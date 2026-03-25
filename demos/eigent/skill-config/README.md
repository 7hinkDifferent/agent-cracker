# Demo: eigent — skill-config

## 目标

用最简代码复现 eigent 的 **多层 Skill 配置体系** — 项目级 > 用户全局 > legacy 三层配置优先级、按 Agent 类型权限过滤、合并配置加载。

## 平台角色

**特色扩展层**（D12）— Skill 是 eigent 的用户自定义能力扩展机制。通过 skills-config.json 配置文件，用户可以在不修改代码的情况下为 Agent 添加新能力。三层配置体系（项目级 > 用户全局 > legacy）支持灵活的权限管理，`_is_agent_allowed()` 确保每个 Skill 只暴露给合适的 Agent 类型。

## 原理

Eigent 的 Skill 配置分三层：

1. **Legacy 默认**：硬编码的默认 Skill 列表，所有用户/项目共享
2. **用户全局**：`/user/<id>/skills-config.json`，覆盖 legacy 中的同名 Skill，可新增/修改 scope
3. **项目级**：`/project/<id>/skills-config.json`，最高优先级，可禁用/新增/覆盖任何 Skill

每个 Skill 配置包含：
- `enabled`：是否启用
- `scope`：`all_agents`（所有 Agent 可用）或 `selected`（指定 Agent）
- `selectedAgents`：当 scope=selected 时，允许的 Agent 名称列表
- `instructions`：注入到 Agent system prompt 的指令文本

`_get_merged_skill_config()` 按优先级合并三层配置，`_is_agent_allowed()` 按当前 Agent 类型过滤。

## 运行

```bash
cd demos/eigent/skill-config
uv run python main.py
```

无需 API key — 此 demo 不调用 LLM，完全模拟配置加载和过滤逻辑。

## 文件结构

```
demos/eigent/skill-config/
├── README.md           # 本文件
└── main.py             # SkillConfig/SkillConfigStore/SkillToolkit + 三层配置演示
```

## 关键代码解读

### _get_merged_skill_config() — 三层合并

```python
def get_merged_config(self, user_id, project_id):
    merged = dict(self._legacy)              # 1. Legacy 基础
    for name, config in user_configs.items():
        merged[name] = config                # 2. 用户级覆盖
    for name, config in project_configs.items():
        merged[name] = config                # 3. 项目级覆盖（最终）
    return merged
```

### _is_agent_allowed() — Agent 类型过滤

```python
def _is_agent_allowed(self, config):
    if not config.enabled:
        return False
    if config.scope == SkillScope.ALL_AGENTS:
        return True
    return self.agent_name in config.selected_agents
```

### skills-config.json 格式

```json
{
  "skills": [
    {
      "name": "api-tester",
      "enabled": true,
      "scope": "selected",
      "selectedAgents": ["developer_agent"],
      "description": "Test REST APIs"
    }
  ]
}
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 配置存储 | 文件系统 JSON 文件 | 内存 dict |
| 配置加载 | 读取 skills-config.json + 缓存 | 直接设置 |
| Skill 指令 | 从配置文件或 DB 加载完整 prompt | 内联字符串 |
| @listen_toolkit | 自动织入 UI 事件 | 无事件织入 |
| Skill 数量 | 10+ 内置 + 用户自定义 | 5 个示例 |
| 验证 | Pydantic 模型校验 | dataclass 无校验 |

**保留的核心**：三层配置优先级（项目 > 用户 > legacy）、合并策略（同名覆盖）、scope + selectedAgents 权限控制、`_is_agent_allowed()` 过滤逻辑。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `backend/app/agent/toolkit/skill_toolkit.py`
