# Agent Cracker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-≥3.10-blue.svg)](https://www.python.org/)
[![Agents](https://img.shields.io/badge/Agents-15-green.svg)](agents.yaml)
[![Demos](https://img.shields.io/badge/Demos-73-orange.svg)](demos/)

> **Disassemble AI Agents, from source code to minimal reproduction.**
>
> Systematically study 11 open-source AI Agents through 8+4 dimensional deep analysis, extract key mechanisms, and reproduce each in 100-200 lines of code. Finally, compose them into runnable mini-agents so you truly understand how AI coding assistants work. Covers both pure Coding Agents and platform-level Agents (multi-channel, memory, scheduling, security).

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
| [aider](https://github.com/Aider-AI/aider) | Python | CLI | done | `Aider-AI/aider` |
| [openhands](https://github.com/All-Hands-AI/OpenHands) | Python | Platform | pending | `All-Hands-AI/OpenHands` |
| [cline](https://github.com/cline/cline) | TypeScript | IDE Plugin | pending | `cline/cline` |
| [continue](https://github.com/continuedev/continue) | TypeScript | IDE Plugin | pending | `continuedev/continue` |
| [goose](https://github.com/block/goose) | Rust | CLI | pending | `block/goose` |
| [codex-cli](https://github.com/openai/codex) | Rust | CLI | done | `openai/codex` |
| [swe-agent](https://github.com/SWE-agent/SWE-agent) | Python | Research | pending | `SWE-agent/SWE-agent` |
| [bolt.new](https://github.com/stackblitz/bolt.new) | TypeScript | Web | pending | `stackblitz/bolt.new` |
| [devika](https://github.com/stitionai/devika) | Python | Autonomous | pending | `stitionai/devika` |
| [gpt-engineer](https://github.com/gpt-engineer-org/gpt-engineer) | Python | CLI | pending | `gpt-engineer-org/gpt-engineer` |
| [pi-agent](https://github.com/badlogic/pi-mono) | TypeScript | CLI | done | `badlogic/pi-mono` |
| [openclaw](https://github.com/openclaw/openclaw) | TypeScript | Platform | done | `openclaw/openclaw` |
| [nanoclaw](https://github.com/qwibitai/nanoclaw) | TypeScript | Platform | done | `qwibitai/nanoclaw` |
| [eigent](https://github.com/eigent-ai/eigent) | TypeScript/Python | 桌面平台 | done | `eigent-ai/eigent` |
| [gemini-cli](https://github.com/google-gemini/gemini-cli) | Python | CLI | done | `google-gemini/gemini-cli` |

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
├── AGENTS.md                # Context file for Codex / pi (symlink to CLAUDE.md)
├── CLAUDE.md                # Project workflow, conventions, automation notes
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
├── .agents/
│   └── skills -> ../.claude/skills   # Shared skills entry for Codex / pi / Claude
├── .codex/
│   ├── README.md             # Codex usage notes
│   └── skills/               # Codex-specific repository workflow skill
├── .pi/
│   ├── prompts/              # pi slash-command templates
│   └── extensions/           # pi compatibility layer for Claude-style hooks
└── .claude/
    ├── skills/               # Claude Code skills (primary source)
    ├── hooks/                # Claude Code hooks
    └── settings.json
```

## Automation

- **Git pre-commit hook**: Changes to agents.yaml → auto-update README table + CLAUDE.md progress; lint consistency check on every commit
- **Claude hooks**: Native support for session status injection, post-edit checks, pre-commit checks, and end-of-turn reminders
- **pi extension**: `.pi/extensions/claude-compat.ts` reproduces key hook behaviors in pi (session status, demo syntax checks, `agents.yaml` validation, pre-commit checks)
- **Codex**: Reuses context and skills through `AGENTS.md` + `.agents/skills`, and adds a repository workflow helper via `.codex/skills/agent-cracker-codex/`; it still does not have a fully equivalent automatic hook layer

## Analysis Dimensions

Each agent analysis covers 8 core dimensions + 4 optional platform dimensions:

**Core Dimensions (all agents):**

1. **Overview & Architecture** — Project positioning, tech stack, architecture diagram
2. **Agent Loop** — Main loop mechanism (input → think → act → observe)
3. **Tool/Action System** — Tool registration, invocation, execution
4. **Prompt Engineering** — System prompt, dynamic assembly
5. **Context Management** — Context window strategy, file selection
6. **Error Handling & Recovery** — Parse errors, retry mechanisms
7. **Key Innovations** — Unique designs, reusable patterns
8. **Cross-Agent Comparison** — Horizontal comparative analysis

**Platform Dimensions (for agents beyond pure coding, optional):**

9. **Channels & Gateway** — Multi-channel routing, message normalization, multi-modal interaction
10. **Memory & Persistence** — Cross-session memory, vector/keyword retrieval
11. **Security Model & Autonomy** — Trust levels, sandboxing, autonomous scheduling
12. **Other Notable Mechanisms** — Skills ecosystem, companion apps, and other unique designs outside D9-D11

## Working with Claude Code / Codex / pi

This repository was originally designed for Claude Code, and now includes a lightweight multi-harness compatibility layer.

### Compatibility Matrix

| Capability | Claude Code | Codex | pi |
|------------|-------------|-------|----|
| Project context | `CLAUDE.md` | `AGENTS.md` (symlink) | `AGENTS.md` / `CLAUDE.md` |
| Skill discovery | `.claude/skills` | `.agents/skills` + `.codex/skills` | `.agents/skills` |
| Slash commands | Native skill commands | Skill-trigger based | `.pi/prompts/*.md` provides `/analyze-agent`-style aliases |
| Session-start status injection | Native hooks | No native equivalent yet | `.pi/extensions/claude-compat.ts` |
| Post-edit validation | Native hooks | No native equivalent yet | `.pi/extensions/claude-compat.ts` |
| Pre-commit guard | Native hooks | No native equivalent yet | `.pi/extensions/claude-compat.ts` |

### Available Skills / Commands

| Command | Purpose |
|---------|---------|
| `/analyze-agent <name>` | 8+4 dimensional deep analysis of agent source code (platform dimensions auto-detected) |
| `/create-demo <agent> <mechanism>` | Create mechanism reproduction demo |
| `/audit-coverage [agent]` | Check MVP coverage gaps |
| `/check-updates [agent]` | Check upstream changes, assess analysis drift |
| `/guide <query>` | Learning guide: recommend relevant docs/demos/source |
| `/sync-comparisons` | Sync cross-agent comparisons |
| `/translate-doc <file>` | Translate between Chinese and English |
| `/update-repo` | Update submodules, README tables, and related metadata |

### Recommended Per-Harness Workflow

#### Claude Code

1. Open the repo and let it load `CLAUDE.md`
2. Main workflow: `/guide` → `/analyze-agent` → `/create-demo`
3. `.claude/settings.json` triggers hooks automatically

#### Codex

1. Enter the repo so Codex loads `AGENTS.md`
2. Shared project skills are discovered via `.agents/skills`, and `.codex/skills/agent-cracker-codex/` provides Codex-specific workflow guidance
3. Good for reusing analysis and learning skills, but **Claude hooks do not auto-run**
4. For non-trivial edits, explicitly ask Codex to use the `agent-cracker-codex` skill
5. Before committing, manually run `npm run lint` and, if needed, `npm run progress`

#### pi

1. Enter the repo so pi loads `AGENTS.md` / `CLAUDE.md`
2. Skills come from `.agents/skills`, and `.pi/prompts` adds Claude-style slash commands
3. `.pi/extensions/claude-compat.ts` restores the key automations:
   - session-start status notice
   - project status snapshot injected before turns
   - pre-`git commit` checks
   - syntax checks after editing `demos/`
   - structural validation after editing `agents.yaml`

### Limits and Conventions

- `agents.yaml` remains the single source of truth in every harness
- The Claude Stop prompt behavior is still only natively available in Claude Code
- Codex currently reuses context, shared skills, and a repository workflow skill, but not full Claude-style automatic checks
- Cross-harness safety net still comes from `scripts/githooks/*`, `npm run lint`, and `npm run progress`

## How to Learn

### Choose Your Path

**"I want to understand how a specific agent works"**
→ Read `docs/<agent>.md` (8-dimensional analysis), run demos in `demos/<agent>/`

**"I want to compare a mechanism across different agents"**
→ Read the same dimension across docs (e.g., D3 Tool System), or use `/guide how do agents handle <topic>`

**"I want to build my own coding agent"**
→ Refer to `docs/<agent>.md` Section 7.5 (MVP Component List), learn demos in MVP → Advanced → Integration order

**"I want to understand the difference between platform agents (e.g., OpenClaw) and pure coding agents"**
→ Read platform agent's D9-D12 (Channels, Memory, Security, Notable Mechanisms), compare with the pure coding agent analysis of the same core engine

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
