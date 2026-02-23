# Agent Cracker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-≥3.10-blue.svg)](https://www.python.org/)
[![Agents](https://img.shields.io/badge/Agents-11-green.svg)](agents.yaml)
[![Demos](https://img.shields.io/badge/Demos-16-orange.svg)](demos/)

> **Disassemble Coding Agents, from source code to minimal reproduction.**
>
> Systematically study 11 open-source Coding Agents through 8-dimensional deep analysis, extract key mechanisms, and reproduce each in 100-200 lines of code. Finally, compose them into runnable mini-agents so you truly understand how AI coding assistants work.

[中文版](README.md)

<p align="center">
  <img src="demo.gif" alt="Agent Cracker Demo" width="700">
</p>

## Cross-Agent Comparison Highlights

Side-by-side comparison of core mechanisms across 3 analyzed agents (continuously updated):

| Dimension | aider | codex-cli | pi-agent |
|-----------|-------|-----------|----------|
| **Language** | Python | Rust + TypeScript | TypeScript |
| **Agent Loop** | 3-layer nested (mode switch + REPL + reflection) | tokio multiplex + turn loop | Dual loop + steering queue |
| **Edit Strategy** | 12+ edit format polymorphism | apply_patch (unified diff) | edit tool (exact + fuzzy match) |
| **Context Strategy** | tree-sitter AST + PageRank RepoMap | bytes/4 estimate + head-tail truncation | chars/4 estimate + structured compaction |
| **Security Model** | Git integration (auto-commit + undo) | 3-tier approval + platform sandbox + network proxy | No built-in sandbox |
| **Error Handling** | Multi-tier fault tolerance + reflection loop | Retryability classification + exponential backoff | Overflow detection + auto-compact |
| **Extensibility** | No formal extension system | Hooks + MCP + Skills | Deep extension (full lifecycle hooks) |

> Full comparisons in each agent's [Dimension 8 analysis](docs/). Every demo is a 100-200 line minimal reproduction you can run directly.

## Agent List

<!-- AGENT_TABLE_START -->

| Agent | Language | Category | Status | Repo |
|-------|----------|----------|--------|------|
| [aider](https://github.com/Aider-AI/aider) | Python | CLI | in-progress | `Aider-AI/aider` |
| [openhands](https://github.com/All-Hands-AI/OpenHands) | Python | Platform | pending | `All-Hands-AI/OpenHands` |
| [cline](https://github.com/cline/cline) | TypeScript | IDE Plugin | pending | `cline/cline` |
| [continue](https://github.com/continuedev/continue) | TypeScript | IDE Plugin | pending | `continuedev/continue` |
| [goose](https://github.com/block/goose) | Rust | CLI | pending | `block/goose` |
| [codex-cli](https://github.com/openai/codex) | Rust | CLI | in-progress | `openai/codex` |
| [swe-agent](https://github.com/SWE-agent/SWE-agent) | Python | Research | pending | `SWE-agent/SWE-agent` |
| [bolt.new](https://github.com/stackblitz/bolt.new) | TypeScript | Web | pending | `stackblitz/bolt.new` |
| [devika](https://github.com/stitionai/devika) | Python | Autonomous | pending | `stitionai/devika` |
| [gpt-engineer](https://github.com/gpt-engineer-org/gpt-engineer) | Python | CLI | pending | `gpt-engineer-org/gpt-engineer` |
| [pi-agent](https://github.com/badlogic/pi-mono) | TypeScript | CLI | in-progress | `badlogic/pi-mono` |

<!-- AGENT_TABLE_END -->

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| [Node.js](https://nodejs.org/) ≥18 | npm scripts, TypeScript demos | `brew install node` |
| [uv](https://docs.astral.sh/uv/) | Python package management & runner (auto-manages Python ≥3.10) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Git](https://git-scm.com/) | Source control, submodules | Pre-installed |
| [Rust](https://www.rust-lang.org/) (optional) | Rust demos | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |

**Demo Toolchain**:

| Language | Run Command | Notes |
|----------|-------------|-------|
| Python | `uv run --with <deps> python main.py` | uv auto-resolves Python ≥3.10 and dependencies |
| TypeScript | `npx tsx main.ts` | Runs via npx, no global install needed |
| Rust | `cargo run` | Standard Rust toolchain |

## Quick Start

```bash
# Clone the project
git clone https://github.com/7hinkDifferent/agent-cracker.git
cd agent-cracker
npm run setup                # Install git hooks

# Initialize submodules (shallow clone, code only)
npm run init

# Add a single agent's source code
npm run add -- aider

# Check submodule status
npm run status

# Create analysis doc for an agent
npm run new-doc -- aider

# Run consistency checks
npm run lint

# Update CLAUDE.md progress section
npm run progress

# Update star counts / README table
npm run stars
npm run readme
```

## Project Structure

```
agent-cracker/
├── agents.yaml              # Agent registry (single source of truth)
├── package.json             # npm scripts entry point
├── projects/                 # Agent source code (git submodule, shallow clone)
│   └── <agent>/
├── docs/                     # Analysis docs (8-dimensional deep analysis)
│   ├── TEMPLATE.md
│   └── <agent>.md
├── demos/                    # Mechanism reproduction demos (grouped by agent)
│   ├── TEMPLATE/
│   └── <agent>/
│       ├── README.md         # Demo overview (mechanism checklist + progress)
│       └── <mechanism>/      # Each demo is independently runnable
├── scripts/                  # Helper scripts (invoked via npm run)
│   ├── manage-submodules.sh
│   ├── new-analysis.sh
│   ├── gen-readme.sh
│   ├── gen-progress.sh
│   ├── update-stars.sh
│   ├── lint.sh
│   └── githooks/pre-commit
└── .claude/
    ├── skills/               # Claude Code skills
    ├── hooks/                # Automation hooks
    └── settings.json
```

## Automation

- **Git pre-commit hook**: Changes to agents.yaml → auto-update README table + CLAUDE.md progress; lint consistency check on every commit
- **Claude hooks**: Auto-inject progress on session start, syntax check demo files, validate agents.yaml format, remind about doc updates on session end

## Analysis Dimensions

Each agent analysis covers 8 dimensions:

1. **Overview & Architecture** — Project positioning, tech stack, architecture diagram
2. **Agent Loop** — Main loop mechanism (input → think → act → observe)
3. **Tool/Action System** — Tool registration, invocation, execution
4. **Prompt Engineering** — System prompt, dynamic assembly
5. **Context Management** — Context window strategy, file selection
6. **Error Handling & Recovery** — Parse errors, retry mechanisms
7. **Key Innovations** — Unique designs, reusable patterns
8. **Cross-Agent Comparison** — Horizontal comparative analysis

## Using with Claude Code

This project includes built-in Claude Code skills and hooks. Recommended workflow:

### Available Skills

| Command | Purpose |
|---------|---------|
| `/analyze-agent <name>` | 8-dimensional deep analysis of agent source code |
| `/create-demo <agent> <mechanism>` | Create mechanism reproduction demo |
| `/audit-coverage [agent]` | Check MVP coverage gaps |
| `/check-updates [agent]` | Check upstream changes, assess analysis drift |
| `/guide <query>` | Learning guide: recommend relevant docs/demos/source |
| `/sync-comparisons` | Sync cross-agent comparisons |
| `/translate-doc <file>` | Translate between Chinese and English |

### Automation Hooks

- **Session start**: Auto-inject project status (agent progress, drift detection)
- **Edit demo**: Auto syntax check (Python/TypeScript/Rust)
- **Commit code**: Auto-check for missing companion doc updates
- **Session end**: Check for overlooked doc updates

### Recommended Usage

1. Start a Claude Code session — project status is auto-injected
2. Use `/guide` to explore mechanisms or get learning paths
3. Use `/analyze-agent` to analyze a new agent
4. Use `/create-demo` to reproduce specific mechanisms
5. Use `/audit-coverage` to check which MVP components still need demos

## How to Learn

### Choose Your Path

**"I want to understand how a specific agent works"**
→ Read `docs/<agent>.md` (8-dimensional analysis), run demos in `demos/<agent>/`

**"I want to compare a mechanism across different agents"**
→ Read the same dimension across docs (e.g., D3 Tool System), or use `/guide how do agents handle <topic>`

**"I want to build my own coding agent"**
→ Refer to `docs/<agent>.md` Section 7.5 (MVP Component List), learn demos in MVP → Advanced → Integration order

**"I want to learn agent fundamentals from scratch"**
→ Start with any agent's `docs/<agent>.md` D1-D2 to understand the core agent loop pattern, then explore other dimensions

### Recommended Reading Order

1. **Getting Started**: Pick a familiar agent (e.g., aider), read `docs/aider.md` D1 (Overview) and D2 (Main Loop)
2. **Hands-on**: Run `demos/aider/search-replace/`, compare with original source paths in README
3. **Compare**: Read a second agent's docs (e.g., codex-cli), observe different design choices
4. **Deep Dive**: Follow D7.5 MVP Component List, run each demo to understand what building a complete agent requires
5. **Practice**: Reference `demos/<agent>/mini-<agent>/` integration demo (composed by importing sibling MVP demo modules), try assembling your own mini agent

### Demo-to-Source Relationship

Each demo README includes:
- **Based on commit**: Source version at time of analysis
- **Core source**: Original file paths in the agent repo (viewable in `projects/<agent>/`)
- **Differences from original**: What was simplified, what was preserved
