---
name: audit-coverage
description: Audit MVP component and mechanism coverage for analyzed agents, identifying gaps and suggesting next steps
---

# Audit Coverage

Check MVP component and mechanism coverage for analyzed agents. Identifies which demos exist, which are missing, and recommends next steps.

## Trigger

`/audit-coverage [agent-name]`

- With `agent-name`: audit that specific agent
- Without arguments: audit all agents with status `in-progress` or `done`

## Prerequisites

1. The agent must have an analysis doc at `docs/<agent-name>.md`
2. Ideally the doc includes section 7.5 (MVP Component Map); if not, components are inferred from D2-D6

## Workflow

### Step 1: Read Analysis Doc

Read `docs/<agent-name>.md` and extract:
- D2-D7 findings (architecture, tools, prompt, context, error handling, innovations)
- D7.5 MVP component table (if present)

### Step 2: Determine MVP Components

- **If 7.5 section exists**: use the table directly as the MVP component list
- **If 7.5 section is missing**: infer MVP components from D2-D6:
  1. 主循环 (from D2)
  2. Tool 注册与分发 (from D3, if applicable)
  3. Prompt 组装 (from D4)
  4. LLM 调用与响应解析 (from D2/D6)
  5. 编辑应用 (from D3, if applicable)
  Adjust based on agent architecture.

### Step 3: Check Demo Coverage

Read `demos/<agent-name>/README.md` (overview):
- Parse MVP section: which components have `[x]` (done) vs `[ ]` (missing)
- Parse 进阶 section: which mechanisms have `[x]` vs `[ ]`
- Check if `mini-<agent>` directory exists (complete integration)

If overview uses old format (flat list without MVP/进阶 sections):
- Map existing demos to MVP vs 进阶 categories
- Note that overview needs migration

### Step 4: Check Document Freshness

Read `agents.yaml` for `analyzed_date`:
- If more than 30 days old → warn and suggest running `/check-updates` first
- If missing → warn about no timestamp

### Step 5: Generate Report

Output a structured report:

```
## <agent> — MVP Coverage Audit

### MVP 组件覆盖
| 组件 | Demo 状态 | 建议语言 | 建议操作 |
|------|-----------|----------|----------|
| core-loop | ❌ 缺失 | Python | /create-demo <agent> core-loop |
| edit-apply | ✅ 已覆盖 (search-replace) | — | — |

### 进阶机制覆盖
| 机制 | 状态 |
|------|------|
| repomap | ✅ |
| fuzzy-match | ❌ |

### 完整串联
- mini-<agent>: ❌ 未创建（需先完成所有 MVP 组件）

### 文档状态
- analyzed_date: YYYY-MM-DD (N 天前)
- 7.5 节: ✅ 存在 / ❌ 缺失（建议补充）

### 总结
- MVP: 2/5 (40%) | 进阶: 4/8 (50%) | 总计: 6/14
- 下一步: 创建 core-loop demo
```

## Relationship with /check-updates

These two skills are complementary:
- `/audit-coverage` → 查覆盖缺口（有什么没有什么）
- `/check-updates` → 查内容时效（现有的还准不准）

When `/audit-coverage` discovers freshness issues (analyzed_date > 30 days), it recommends running `/check-updates` first.
