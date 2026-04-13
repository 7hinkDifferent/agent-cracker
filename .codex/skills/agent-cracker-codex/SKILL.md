---
name: agent-cracker-codex
description: Codex workflow adapter for this repository. Use when working in agent-cracker to translate Claude-style slash workflows into skill usage, remember manual checks that Claude hooks would normally perform, and keep docs/config/progress files in sync.
---

# Agent Cracker Codex Workflow

Use this skill whenever you are making changes in this repository, especially when the user asks with Claude-style commands such as `/analyze-agent`, `/create-demo`, `/guide`, `/check-updates`, or when you touch `agents.yaml`, `docs/`, `demos/`, `.claude/`, `.pi/`, `.codex/`, or project automation files.

## Goals

1. Make Codex behave as close as possible to the repository's original Claude Code workflow
2. Reuse existing project skills instead of inventing parallel workflows
3. Manually compensate for missing Claude hook automation

## Step 1: Reuse existing project skills

This repo already exposes shared skills through `.agents/skills`.

When the user says any of the following, treat it as a request to use the matching project skill:

- `/analyze-agent <name>` → use `analyze-agent`
- `/create-demo <agent> <mechanism>` → use `create-demo`
- `/audit-coverage <name>` → use `audit-coverage`
- `/check-updates <name>` → use `check-updates`
- `/guide <query>` → use `guide`
- `/sync-comparisons` → use `sync-comparisons`
- `/translate-doc ...` → use `translate-doc`
- `/update-repo` → use `update-repo`

If a slash-style request is ambiguous, ask a short clarifying question instead of guessing.

## Step 2: Apply repository invariants

Always preserve these rules:

- `agents.yaml` is the single source of truth
- docs and comments use Chinese; code identifiers stay English
- demo directories follow `demos/<agent>/<mechanism>/`
- each agent overview lives in `demos/<agent>/README.md`
- analysis/demo progress must stay aligned with `CLAUDE.md` progress and README tables via repo scripts

## Step 3: Manually emulate missing Claude hooks

Codex does not auto-run Claude hooks in this repo, so you must remember the checks yourself.

### A. Before `git commit`

Run these when relevant:

```bash
npm run lint
npm run progress
```

Block or warn if obvious follow-up files were skipped.

### B. If `agents.yaml` changed

Check whether related files also need updates:

- `README.md`
- `README.en.md`
- `CLAUDE.md`
- any affected `docs/<agent>.md`
- any affected `demos/<agent>/README.md`

### C. If `docs/<agent>.md` changed

Check whether `agents.yaml` also needs:

- `status`
- `analyzed_commit`
- `analyzed_date`

Also consider whether `demos/<agent>/README.md` should be updated.

### D. If `demos/<agent>/<mechanism>/` changed

Check whether:

- `demos/<agent>/README.md` overview was updated
- `agents.yaml` status should change
- `npm run progress` should be run
- the demo README includes `基于 commit`

### E. If `scripts/`, `.claude/`, `.pi/`, or `.codex/` changed

Check whether `CLAUDE.md`, `README.md`, and `README.en.md` still accurately describe:

- project structure
- commands
- automation
- harness compatibility

## Step 4: Prefer the repo's official commands

Use the project scripts instead of inventing ad hoc workflows when possible:

- `npm run lint`
- `npm run progress`
- `npm run readme`
- `npm run stars`
- `npm run status`
- `npm run new-doc -- <agent>`
- `npm run add -- <agent>`
- `npm run update -- <agent>`

## Step 5: Be explicit in the final response

When you finish a Codex task in this repo, briefly report:

- which project skill/workflow you followed
- which follow-up checks you ran
- whether any Claude-only automation is still not reproducible in Codex
