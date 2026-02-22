---
name: analyze-agent
description: Systematically analyze a coding agent's source code across 8 dimensions and output structured analysis to docs/<agent>.md
---

# Analyze Agent

Deep-dive analysis of a coding agent's implementation. Reads the agent's source code from `projects/<agent>/` and fills `docs/<agent>.md` using the 8-dimension template.

## Trigger

`/analyze-agent <agent-name>`

## Prerequisites

1. The agent's source code must exist at `projects/<agent-name>/`（run `./scripts/manage-submodules.sh add <agent-name>` if not present）
2. The analysis doc `docs/<agent-name>.md` should exist（run `./scripts/new-analysis.sh <agent-name>` if not present）

## Analysis Framework

Analyze the agent across these 8 dimensions, in order:

### Dimension 1: Overview & Architecture

- **Goal**: Understand what this agent is, its tech stack, and high-level architecture
- **Strategy**: Read `README.md`, `setup.py`/`pyproject.toml`/`package.json`, entry point files (`main.py`, `__main__.py`, `index.ts`, `cli.ts`)
- **Output**: Project positioning, tech stack, architecture diagram (ASCII/Mermaid), key files table

### Dimension 2: Agent Loop

- **Goal**: Understand the main event loop: input → think → act → observe → ...
- **Strategy**: Find the main loop by searching for patterns: `while`, `loop`, `run()`, `run_one()`, `step()`, `execute()`. Trace from entry point to the core loop.
- **Output**: Loop flow description, termination conditions, key code snippet

### Dimension 3: Tool/Action System

- **Goal**: Understand how tools are defined, registered, and invoked
- **Strategy**: Search for tool registration patterns: decorators (`@tool`, `@command`), registries, command maps. List all available tools/commands.
- **Output**: Registration mechanism, tool list table, tool invocation flow

### Dimension 4: Prompt Engineering

- **Goal**: Understand system prompt structure and dynamic assembly
- **Strategy**: Search for files named `*prompt*`, `*system*`, `*template*`. Find where prompts are assembled and sent to LLM.
- **Output**: System prompt structure, dynamic parts, template file paths

### Dimension 5: Context Management

- **Goal**: Understand how the agent manages limited context window
- **Strategy**: Search for context/window/token management, file selection strategies, history truncation/compression. Look for `repomap`, `summary`, `compress`, `truncat`.
- **Output**: Context window strategy, file/code context strategy, conversation history management

### Dimension 6: Error Handling & Recovery

- **Goal**: Understand how the agent handles LLM output parsing errors, tool failures, and retries
- **Strategy**: Search for `retry`, `error`, `exception`, `fallback`, `recover`. Check how malformed LLM output is handled.
- **Output**: LLM output parsing errors, tool execution failures, retry mechanism

### Dimension 7: Key Innovations

- **Goal**: Identify unique designs and patterns worth borrowing
- **Strategy**: Based on findings from dimensions 1-6, highlight what makes this agent special. Check README for claimed features.
- **Output**: Unique designs, reusable patterns

### Dimension 8: Cross-Agent Comparison

- **Goal**: Compare with other analyzed agents
- **Strategy**: Reference existing docs in `docs/` directory. If this is the first agent analyzed, note "first agent" and compare with general patterns.
- **Output**: Comparison table, summary paragraph

## Key File Discovery Strategy

For each language ecosystem, use these heuristics to find critical files:

**Python agents:**
- Entry: `**/main.py`, `**/__main__.py`, `**/cli.py`
- Config: `setup.py`, `pyproject.toml`, `setup.cfg`
- Core: `**/agent.py`, `**/coder*.py`, `**/runner.py`

**TypeScript/JavaScript agents:**
- Entry: `**/index.ts`, `**/main.ts`, `**/cli.ts`
- Config: `package.json`, `tsconfig.json`
- Core: `**/agent.ts`, `**/core/**`, `**/lib/**`

**Rust agents:**
- Entry: `**/main.rs`, `**/lib.rs`
- Config: `Cargo.toml`
- Core: `**/agent/**`, `**/core/**`

## Output Requirements

1. Fill all 8 sections in `docs/<agent-name>.md`
2. Include actual code snippets (key fragments, not entire files)
3. Architecture diagram should be ASCII or Mermaid
4. Tool list should be comprehensive
5. Write in Chinese (matching the template style), code/identifiers stay in English
6. Remove all `<!-- comment -->` placeholders and replace with actual content

## After Analysis

Update `agents.yaml`: change the agent's `status` from `pending` to `done`.
