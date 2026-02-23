#!/usr/bin/env bash
# show-deps.sh — 显示自动化依赖关系图
# 通过解析 pre-commit hook、.claude/settings.json、package.json 生成
# 用法: ./scripts/show-deps.sh 或 npm run deps

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

PRECOMMIT="scripts/githooks/pre-commit"
SETTINGS=".claude/settings.json"

echo "=== Automation Dependency Graph ==="
echo ""

# ── Git pre-commit hooks ──
echo "[git pre-commit] (triggers on commit)"

if [ -f "$PRECOMMIT" ]; then
  # 解析 pre-commit hook 中调用的脚本
  scripts_called=$(grep -oE 'bash "\$REPO_ROOT/scripts/[^"]+' "$PRECOMMIT" 2>/dev/null | \
    sed 's|bash "\$REPO_ROOT/||' | sort -u)

  # agents.yaml 触发的脚本
  echo ""
  echo "  agents.yaml changes:"
  if grep -q 'agents.yaml.*gen-readme' "$PRECOMMIT" 2>/dev/null || \
     grep -B2 'gen-readme' "$PRECOMMIT" 2>/dev/null | grep -q 'agents.yaml'; then
    echo "    ──→ gen-readme.sh ──→ README.md (table + badges)"
    if grep -q 'README.en.md' "$PRECOMMIT" 2>/dev/null; then
      echo "                       ──→ README.en.md (table + badges)"
    fi
  fi

  if grep -q 'gen-progress' "$PRECOMMIT" 2>/dev/null; then
    echo "    ──→ gen-progress.sh ──→ CLAUDE.md (progress)"
  fi

  # demos/ 触发的脚本
  echo ""
  echo "  demos/ changes:"
  if grep -qE 'demos/.*gen-progress' "$PRECOMMIT" 2>/dev/null || \
     grep -B2 'gen-progress' "$PRECOMMIT" 2>/dev/null | grep -q 'demos'; then
    echo "    ──→ gen-progress.sh ──→ CLAUDE.md (progress)"
  fi
  if grep -qE 'demos/.*gen-readme' "$PRECOMMIT" 2>/dev/null || \
     grep -q 'gen-readme' "$PRECOMMIT" 2>/dev/null; then
    echo "    ──→ gen-readme.sh ──→ README.md (badges)"
    echo "                       ──→ README.en.md (badges)"
  fi

  # lint
  echo ""
  echo "  every commit:"
  if grep -q 'lint.sh' "$PRECOMMIT" 2>/dev/null; then
    echo "    ──→ lint.sh ──→ (validate all: agents.yaml/docs/demos/README consistency)"
  fi
else
  echo "  (pre-commit hook not found)"
fi

echo ""

# ── Claude hooks ──
echo "[Claude hooks] (triggers during conversation)"
echo ""

if [ -f "$SETTINGS" ]; then
  python3 - "$SETTINGS" <<'PYEOF'
import json, sys, os

settings_file = sys.argv[1]
with open(settings_file) as f:
    d = json.load(f)

hooks = d.get("hooks", {})

def extract_name(cmd):
    """Extract script name from command path."""
    return cmd.split("/")[-1].strip('"')

for event in ("SessionStart", "PreToolUse", "PostToolUse", "Stop"):
    if event not in hooks:
        continue
    for h in hooks[event]:
        matcher = h.get("matcher", "")
        label = f"{event} [{matcher}]" if matcher else event
        for hook in h.get("hooks", []):
            if hook.get("type") == "command":
                name = extract_name(hook.get("command", ""))
                print(f"  {label} ──→ {name}")
            elif hook.get("type") == "prompt":
                print(f"  {label} ──→ (prompt: file→doc mapping check)")
PYEOF
else
  echo "  (.claude/settings.json not found)"
fi

echo ""

# ── 自动暂存的文件 ──
echo "[Auto-staged files on commit]"
echo ""

if [ -f "$PRECOMMIT" ]; then
  staged_files=$(grep -oE 'git add "\$REPO_ROOT/[^"]+' "$PRECOMMIT" 2>/dev/null | \
    sed 's|git add "\$REPO_ROOT/||' | sort -u)
  if [ -n "$staged_files" ]; then
    while IFS= read -r f; do
      echo "  $f"
    done <<< "$staged_files"
  fi
fi

echo ""

# ── npm scripts ──
echo "[npm scripts] (manual triggers)"
echo ""

if [ -f "package.json" ]; then
  python3 -c "
import json
with open('package.json') as f:
  d = json.load(f)
scripts = d.get('scripts', {})
for name, cmd in scripts.items():
  if name in ('postinstall',):
    continue
  print(f'  npm run {name:12s} ──→ {cmd}')
" 2>/dev/null
fi

echo ""
echo "=== End ==="
