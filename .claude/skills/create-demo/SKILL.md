---
name: create-demo
description: Create a minimal reproduction demo for a specific mechanism from an analyzed coding agent
---

# Create Demo

Create a standalone, minimal demo that reproduces a single core mechanism from an analyzed coding agent.

## Trigger

`/create-demo <agent-name> <mechanism>`

Example: `/create-demo aider repomap`

## Prerequisites

1. Analysis doc must exist at `docs/<agent-name>.md` (run `/analyze-agent` first)
2. The mechanism must be identified in the analysis doc's "Key Innovations" or other sections

## Workflow

### Step 1: Read Analysis

Read `docs/<agent-name>.md` and identify the target mechanism:
- What problem does it solve?
- What's the core algorithm/flow?
- What are the key data structures?
- What dependencies does the original use?

### Step 2: Design Simplification

Apply these simplification principles:
- **Single mechanism**: Focus on ONE mechanism only, remove all others
- **Minimal dependencies**: Use the fewest possible libraries
- **No infrastructure**: Remove git integration, database caching, CLI frameworks, config systems
- **Hardcode when possible**: Replace configurable options with sensible defaults
- **语言选择**: 默认 Python。当机制依赖语言特性时用原生语言，README 须含 "为何选择此语言" 节
- **Simple I/O**: Print to stdout, no rich formatting or interactive prompts
- **Inline over import**: If a helper is < 20 lines, inline it rather than importing from another demo

### Step 3: Create File Structure

Create `demos/<agent-name>/<mechanism>/` with the structure matching the chosen language:

**Python:**
```
demos/<agent-name>/<mechanism>/
├── README.md           # From template, filled in
├── requirements.txt    # Only if external deps needed (not for stdlib-only demos)
├── main.py             # Entry point (or split into logical modules)
└── sample_*/           # Sample data/project if needed for demonstration
```

**TypeScript:**
```
demos/<agent-name>/<mechanism>/
├── README.md           # From template, filled in
├── package.json        # Dependencies
├── tsconfig.json       # TypeScript config
├── main.ts             # Entry point
└── sample_*/           # Sample data/project if needed for demonstration
```

**Rust:**
```
demos/<agent-name>/<mechanism>/
├── README.md           # From template, filled in
├── Cargo.toml          # Project config & dependencies
├── src/
│   └── main.rs         # Entry point
└── sample_*/           # Sample data/project if needed for demonstration
```

### Step 4: Write README

Use the template from `demos/TEMPLATE/README.md` and fill in:
- **Goal**: One sentence describing what this demo reproduces
- **原理**: How the mechanism works in the original agent (2-3 paragraphs)
- **运行**: Exact commands to run the demo
- **文件结构**: Actual file tree
- **关键代码解读**: Core algorithm with inline comments
- **与原实现的差异**: What was simplified and what was preserved
- **相关文档**: Must include `基于 commit: <short-sha>` and `核心源码: <原项目中对应的文件路径>` (the source path is used by `/check-updates` to match changes)

### Step 5: Implement Core Logic

Guidelines:
- Target ~100-200 lines of core logic per demo
- LLM 调用按语言选择对应库和运行方式：

| 语言 | LLM 库 | 运行方式 | 模型变量 |
|------|--------|---------|---------|
| Python | litellm | `uv run --with <deps> python main.py` | `DEMO_MODEL` |
| TypeScript | openai SDK | `npx tsx main.ts` | `DEMO_MODEL` |
| Rust | reqwest | `cargo run` | `DEMO_MODEL` |

- Each demo must be independently runnable
- Include sample data/projects so the demo works out of the box
- Add clear print statements showing what's happening at each step

### Step 5.5: Complete Integration Demo (mini-agent)

When all MVP component demos for an agent are complete, create a combined integration demo:

- **目录**: `demos/<agent>/mini-<agent>/`
- **目标**: 串联所有 MVP 组件为一个最简可运行 agent
- **行数**: 200-400 行，可 import 兄弟 MVP demo 目录
- **前提**: 所有 MVP 组件 demo 已完成
- **语言**: 与多数 MVP 组件一致（混合则用 Python）

### Step 6: Verify

Run the demo and confirm:
- It executes without errors
- It demonstrates the core mechanism clearly
- Output is understandable to someone learning the mechanism

## Code Style

- Use type hints for function signatures
- Add docstrings for the main functions explaining the mechanism
- Keep classes minimal — prefer functions unless state management is essential
- Name variables to match the original codebase's terminology where possible

## Output

The completed demo directory at `demos/<agent-name>/<mechanism>/`.

## After Creating Demo

1. Update the agent's overview at `demos/<agent-name>/README.md`: mark the mechanism as `[x]` and update the progress line to format `MVP: X/N | 进阶: Y/M | 总计: Z/K`
2. Update `agents.yaml` status if needed (e.g. `pending` → `in-progress`)
3. Run `npm run progress` to update the CLAUDE.md progress section (or it will auto-update on next commit)
4. Confirm the demo README's "相关文档" section includes `基于 commit: <short-sha>` (read from `agents.yaml` `analyzed_commit`). This provides a baseline for `/check-updates` demo impact assessment.
