#!/usr/bin/env bash
# lint.sh — mono repo 一致性检查
# 检查各模块之间的数据一致性，防止"改了 A 忘了 B"
# 用法: ./scripts/lint.sh 或 npm run lint

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

ERRORS=0
WARNINGS=0

error() { echo "  ❌ $1"; ERRORS=$((ERRORS + 1)); }
warn()  { echo "  ⚠️  $1"; WARNINGS=$((WARNINGS + 1)); }
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
    for f in main.py repomap.py index.js index.ts main.ts; do
      [ -f "$demo_dir/$f" ] && has_entry=true && break
    done
    if ! $has_entry && [ -f "$demo_dir/Cargo.toml" ] && [ -f "$demo_dir/src/main.rs" ]; then
      has_entry=true
    fi
    if ! $has_entry; then
      error "$prefix: no entry file (main.py / main.ts / index.js / Cargo.toml+src/main.rs)"
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

  # 检查 overview 进度行格式（应包含串联统计）
  if grep -q '^MVP:' "$overview" 2>/dev/null; then
    if ! grep -q '串联' "$overview" 2>/dev/null; then
      warn "$agent: overview 进度行缺少串联统计 — 格式应为 MVP: X/N | 进阶: Y/M | 串联: Z/1 | 总计: A/B"
    fi
  fi

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
  ok "README.md table ($readme_agents) matches agents.yaml ($yaml_agents)"
else
  warn "README.md table has $readme_agents agents, agents.yaml has $yaml_agents → run 'npm run readme'"
fi

# README.en.md 表格同步检查
if [ -f "README.en.md" ]; then
  readme_en_agents=$(sed -n '/AGENT_TABLE_START/,/AGENT_TABLE_END/p' README.en.md | grep -c '^|.*\[.*\](http' 2>/dev/null || echo 0)
  if [ "$readme_en_agents" -eq "$yaml_agents" ]; then
    ok "README.en.md table ($readme_en_agents) matches agents.yaml ($yaml_agents)"
  else
    warn "README.en.md table has $readme_en_agents agents, agents.yaml has $yaml_agents → run 'npm run readme'"
  fi
fi
echo ""

# ─── 6. 跨 Agent 对比覆盖 ─────────────────────────────
echo "6. 跨 Agent 对比覆盖"

# 收集已分析的 agent（status 为 in-progress 或 done 且有 docs/<name>.md）
ANALYZED_AGENTS=()
for name in "${AGENT_NAMES[@]}"; do
  status=$(grep -A5 "name: $name" agents.yaml | grep "status:" | head -1 | sed 's/.*status:[[:space:]]*//' | tr -d '[:space:]')
  if [[ "$status" == "in-progress" || "$status" == "done" ]] && [ -f "docs/$name.md" ]; then
    ANALYZED_AGENTS+=("$name")
  fi
done

if [ "${#ANALYZED_AGENTS[@]}" -lt 2 ]; then
  ok "跳过（已分析 agent 不足 2 个）"
else
  for name in "${ANALYZED_AGENTS[@]}"; do
    # 提取 Dimension 8 部分（从 ## 8. 到文件末尾或下一个 ## ）
    dim8=$(sed -n '/^## 8\./,/^## [0-9]/p' "docs/$name.md" | sed '$d')
    if [ -z "$dim8" ]; then
      # 如果没有下一个 ##，取到文件末尾
      dim8=$(sed -n '/^## 8\./,$p' "docs/$name.md")
    fi

    missing=()
    total=0
    for other in "${ANALYZED_AGENTS[@]}"; do
      [ "$other" = "$name" ] && continue
      total=$((total + 1))
      if ! echo "$dim8" | grep -qi "$other"; then
        missing+=("$other")
      fi
    done

    if [ "${#missing[@]}" -gt 0 ]; then
      warn "$name: Dimension 8 未引用 ${missing[*]} → 运行 /sync-comparisons"
    else
      ok "$name: 对比覆盖 $total/$total agents"
    fi
  done
fi
echo ""

# ─── 7. Commit 跟踪一致性 ────────────────────────────
echo "7. Commit 跟踪一致性"

for name in "${AGENT_NAMES[@]}"; do
  status=$(grep -A8 "name: $name" agents.yaml | grep "status:" | head -1 | sed 's/.*status:[[:space:]]*//' | tr -d '[:space:]')
  if [[ "$status" != "in-progress" && "$status" != "done" ]]; then
    continue
  fi

  analyzed_commit=$(grep -A8 "name: $name" agents.yaml | grep "analyzed_commit:" | head -1 | sed 's/.*analyzed_commit:[[:space:]]*//' | tr -d '[:space:]')

  if [ -z "$analyzed_commit" ]; then
    warn "$name: in-progress/done but no analyzed_commit in agents.yaml"
    continue
  fi

  if [ -d "projects/$name" ]; then
    submodule_head=$(git -C "projects/$name" rev-parse HEAD 2>/dev/null || echo "")
    if [ -n "$submodule_head" ]; then
      if [ "$analyzed_commit" = "$submodule_head" ]; then
        ok "$name: analyzed_commit matches submodule HEAD (${analyzed_commit:0:7})"
      else
        warn "$name: DRIFT — analyzed ${analyzed_commit:0:7} ≠ submodule ${submodule_head:0:7}"
      fi
    else
      ok "$name: has analyzed_commit (submodule HEAD unreadable)"
    fi
  else
    ok "$name: has analyzed_commit ${analyzed_commit:0:7} (no local submodule)"
  fi
done
echo ""

# ─── 8. MVP 覆盖一致性（warning 级别）─────────────────
echo "8. MVP 覆盖一致性"

for agent_dir in demos/*/; do
  agent=$(basename "$agent_dir")
  [ "$agent" = "TEMPLATE" ] && continue

  overview="$agent_dir/README.md"
  if [ ! -f "$overview" ]; then
    continue
  fi

  if grep -q '^## MVP 组件' "$overview" 2>/dev/null; then
    # 新格式：检查 MVP 完成度和 mini-agent
    mvp_done=$(sed -n '/^## MVP 组件/,/^## /p' "$overview" | grep -c '^\- \[x\]' 2>/dev/null) || mvp_done=0
    mvp_total=$(sed -n '/^## MVP 组件/,/^## /p' "$overview" | grep -c '^\- \[.\]' 2>/dev/null) || mvp_total=0

    if [ "$mvp_done" -eq "$mvp_total" ] && [ "$mvp_total" -gt 0 ]; then
      # 检查串联 demo：查找 mini-* 目录（如 mini-aider, mini-pi）
      mini_dir=$(find "${agent_dir}" -maxdepth 1 -type d -name 'mini-*' 2>/dev/null | head -1)
      if [ -z "$mini_dir" ]; then
        warn "$agent: all MVP components done ($mvp_done/$mvp_total) but no mini-* integration demo"
      else
        ok "$agent: MVP complete with integration demo"
      fi
    else
      ok "$agent: MVP $mvp_done/$mvp_total"
    fi
  else
    warn "$agent: overview uses old format, consider migrating to three-tier (MVP/进阶/串联)"
  fi
done
echo ""

# ─── Summary ───────────────────────────────────────────
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
