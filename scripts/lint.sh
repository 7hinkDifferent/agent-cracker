#!/usr/bin/env bash
# lint.sh — mono repo 一致性检查
# 检查各模块之间的数据一致性，防止"改了 A 忘了 B"
# 用法: ./scripts/lint.sh 或 npm run lint

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

ERRORS=0
WARNINGS=0

error() { echo "  ❌ $1"; ((ERRORS++)); }
warn()  { echo "  ⚠️  $1"; ((WARNINGS++)); }
ok()    { echo "  ✅ $1"; }

echo "=== Agent Cracker Mono Repo Lint ==="
echo ""

# ─── 1. agents.yaml 完整性 ─────────────────────────────
echo "1. agents.yaml 完整性"

AGENT_NAMES=()
while IFS= read -r line; do
  if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*(.*) ]]; then
    name="${BASH_REMATCH[1]}"
    name="${name%"${name##*[![:space:]]}"}"
    AGENT_NAMES+=("$name")
  fi
done < agents.yaml

for name in "${AGENT_NAMES[@]}"; do
  has_repo=$(grep -A5 "name: $name" agents.yaml | grep -c "repo:" || true)
  has_status=$(grep -A5 "name: $name" agents.yaml | grep -c "status:" || true)
  if [ "$has_repo" -eq 0 ]; then
    error "$name: missing repo in agents.yaml"
  elif [ "$has_status" -eq 0 ]; then
    error "$name: missing status in agents.yaml"
  else
    ok "$name"
  fi
done
echo ""

# ─── 2. Status vs 实际产物 ─────────────────────────────
echo "2. Status 与实际产物一致性"

for name in "${AGENT_NAMES[@]}"; do
  status=$(grep -A5 "name: $name" agents.yaml | grep "status:" | head -1 | sed 's/.*status:[[:space:]]*//' | tr -d '[:space:]')
  has_doc=false; [ -f "docs/$name.md" ] && has_doc=true
  has_demos=false; [ -d "demos/$name" ] && has_demos=true
  has_submodule=false; [ -d "projects/$name" ] && has_submodule=true

  case "$status" in
    pending)
      if $has_doc; then
        warn "$name: status=pending but docs/$name.md exists → should be in-progress or done?"
      else
        ok "$name: pending (no artifacts yet)"
      fi
      ;;
    in-progress)
      if ! $has_submodule; then
        warn "$name: status=in-progress but projects/$name/ not found"
      elif ! $has_doc; then
        warn "$name: status=in-progress but docs/$name.md not found"
      else
        ok "$name: in-progress (has submodule + doc)"
      fi
      ;;
    done)
      if ! $has_doc; then
        error "$name: status=done but docs/$name.md missing"
      elif ! $has_demos; then
        warn "$name: status=done but no demos/$name/ directory"
      else
        ok "$name: done (has doc + demos)"
      fi
      ;;
  esac
done
echo ""

# ─── 3. Demo 结构检查 ──────────────────────────────────
echo "3. Demo 结构规范"

for agent_dir in demos/*/; do
  agent=$(basename "$agent_dir")
  [ "$agent" = "TEMPLATE" ] && continue

  for demo_dir in "$agent_dir"*/; do
    [ ! -d "$demo_dir" ] && continue
    demo=$(basename "$demo_dir")
    prefix="$agent/$demo"

    # 必须有 README
    if [ ! -f "$demo_dir/README.md" ]; then
      error "$prefix: missing README.md"
    else
      ok "$prefix: has README.md"
    fi

    # 必须有入口文件
    has_entry=false
    for f in main.py repomap.py index.js index.ts; do
      [ -f "$demo_dir/$f" ] && has_entry=true && break
    done
    if ! $has_entry; then
      error "$prefix: no entry file (main.py / index.js)"
    fi
  done
done
echo ""

# ─── 4. Demo Overview 一致性 ───────────────────────────
echo "4. Demo Overview 一致性"

for agent_dir in demos/*/; do
  agent=$(basename "$agent_dir")
  [ "$agent" = "TEMPLATE" ] && continue

  overview="$agent_dir/README.md"
  if [ ! -f "$overview" ]; then
    warn "$agent: demos/$agent/README.md (overview) not found"
    continue
  fi

  # 检查已有的 demo 目录是否都在 overview 中列出
  for demo_dir in "$agent_dir"*/; do
    [ ! -d "$demo_dir" ] && continue
    demo=$(basename "$demo_dir")
    if ! grep -q "\*\*$demo\*\*" "$overview" 2>/dev/null; then
      error "$agent/$demo: demo directory exists but not listed in overview"
    fi
  done

  # 检查 overview 中标记为 [x] 的是否都有对应目录
  while IFS= read -r mline; do
    mname=$(echo "$mline" | sed 's/.*\*\*\(.*\)\*\*.*/\1/')
    if [ ! -d "$agent_dir$mname" ]; then
      error "$agent/$mname: marked done in overview but directory missing"
    fi
  done < <(grep '^\- \[x\]' "$overview" 2>/dev/null || true)

  done_count=$(grep -c '^\- \[x\]' "$overview" 2>/dev/null) || done_count=0
  total_count=$(grep -c '^\- \[.\]' "$overview" 2>/dev/null) || total_count=0
  ok "$agent: overview $done_count/$total_count"
done
echo ""

# ─── 5. README 表格同步 ────────────────────────────────
echo "5. README 表格同步"

readme_agents=$(sed -n '/AGENT_TABLE_START/,/AGENT_TABLE_END/p' README.md | grep -c '^|.*\[.*\](http' 2>/dev/null || echo 0)
yaml_agents=${#AGENT_NAMES[@]}

if [ "$readme_agents" -eq "$yaml_agents" ]; then
  ok "README table ($readme_agents) matches agents.yaml ($yaml_agents)"
else
  warn "README table has $readme_agents agents, agents.yaml has $yaml_agents → run 'npm run readme'"
fi
echo ""

# ─── Summary ──────────���────────────────────────────────
echo "=== Summary ==="
echo "  Errors:   $ERRORS"
echo "  Warnings: $WARNINGS"
echo ""

if [ "$ERRORS" -gt 0 ]; then
  echo "❌ Lint failed. Fix errors above."
  exit 1
else
  echo "✅ Lint passed."
  exit 0
fi
