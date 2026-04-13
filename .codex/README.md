# Codex Compatibility Notes

This repository was originally designed for Claude Code and now includes a small Codex compatibility layer.

## What Codex can reuse directly

- `AGENTS.md` → project instructions (symlink to `CLAUDE.md`)
- `.agents/skills` → shared project skills originally written for Claude Code
- `.codex/skills/agent-cracker-codex/` → Codex-specific workflow adapter for this repository

## Recommended Codex usage

In Codex, these Claude-style inputs should still work well because the corresponding project skills are discoverable:

- `/guide context management`
- `/analyze-agent openhands`
- `/create-demo pi-agent event-stream`
- `/check-updates openclaw`
- `/audit-coverage aider`

You can also phrase them explicitly:

- `Use the analyze-agent skill for openhands`
- `Use the create-demo skill for pi-agent event-stream`
- `Use the agent-cracker-codex skill before making changes in this repo`

## Current limitations

Codex does **not** automatically reproduce Claude hooks in this project.

That means Codex users should manually remember to run:

```bash
npm run lint
npm run progress
```

Especially after changing:

- `agents.yaml`
- `docs/`
- `demos/`
- `.claude/`, `.pi/`, `.codex/`, `scripts/`
- `README.md` / `README.en.md` / `CLAUDE.md`

## Codex-specific helper skill

See `.codex/skills/agent-cracker-codex/SKILL.md`.

That skill reminds Codex to:

- translate Claude-style slash workflows into project skill usage
- perform manual follow-up checks that Claude hooks would normally cover
- keep `agents.yaml`, docs, demo overview files, and progress metadata in sync
