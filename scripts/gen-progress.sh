#!/usr/bin/env bash
# gen-progress.sh — 从 agents.yaml + 文件系统自动生成 CLAUDE.md 进度段落
# 用法: ./scripts/gen-progress.sh 或 npm run progress

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

AGENTS_FILE="agents.yaml"
CLAUDE_MD="CLAUDE.md"
START_MARKER="<!-- PROGRESS_START -->"
END_MARKER="<!-- PROGRESS_END -->"

# ── 从 agents.yaml 解析并分类 ──
done_list=""
in_progress_list=""
pending_list=""

current_name=""
while IFS= read -r line; do
  if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*(.*) ]]; then
    current_name="${BASH_REMATCH[1]}"
    current_name="${current_name%"${current_name##*[![:space:]]}"}"
  elif [[ "$line" =~ ^[[:space:]]*status:[[:space:]]*(.*) ]]; then
    status="${BASH_REMATCH[1]}"
    status="${status%"${status##*[![:space:]]}"}"
    case "$status" in
      done)        done_list="$done_list, $current_name" ;;
      in-progress) in_progress_list="$in_progress_list, $current_name" ;;
      *)           pending_list="$pending_list, $current_name" ;;
    esac
  fi
done < "$AGENTS_FILE"

done_list="${done_list#, }"
in_progress_list="${in_progress_list#, }"
pending_list="${pending_list#, }"

# ── 扫描 demos 目录（从 overview README 读取进度）──
demo_lines=""
for agent_dir in demos/*/; do
  agent=$(basename "$agent_dir")
  [ "$agent" = "TEMPLATE" ] && continue

  overview="$agent_dir/README.md"
  if [ -f "$overview" ]; then
    # 从 overview 读取 done/total 计数
    done_count=$(grep -c '^\- \[x\]' "$overview" 2>/dev/null) || done_count=0
    total_count=$(grep -c '^\- \[.\]' "$overview" 2>/dev/null) || total_count=0
    # 收集已完成的 mechanism 名称
    mechanisms=""
    while IFS= read -r mline; do
      mname=$(echo "$mline" | sed 's/.*\*\*\(.*\)\*\*.*/\1/')
      mechanisms="$mechanisms, $mname"
    done < <(grep '^\- \[x\]' "$overview" 2>/dev/null || true)
    mechanisms="${mechanisms#, }"
    if [ "$total_count" -gt 0 ]; then
      demo_lines="${demo_lines}
- **${agent}**: ${done_count}/${total_count} (${mechanisms})"
    fi
  else
    # 没有 overview，回退到目录扫描
    mechanisms=""
    for demo_dir in "$agent_dir"*/; do
      [ ! -d "$demo_dir" ] && continue
      mechanisms="$mechanisms, $(basename "$demo_dir")"
    done
    mechanisms="${mechanisms#, }"
    if [ -n "$mechanisms" ]; then
      demo_lines="${demo_lines}
- **${agent}**: ${mechanisms}"
    fi
  fi
done

# ── 生成进度内容 ──
PROGRESS=""
[ -n "$done_list" ] && PROGRESS="${PROGRESS}- **已完成**: ${done_list}
"
[ -n "$in_progress_list" ] && PROGRESS="${PROGRESS}- **进行中**: ${in_progress_list}
"
[ -n "$pending_list" ] && PROGRESS="${PROGRESS}- **待分析**: ${pending_list}
"
[ -n "$demo_lines" ] && PROGRESS="${PROGRESS}
Demo 覆盖:${demo_lines}
"

# ── 替换 CLAUDE.md 中 marker 之间的内容 ──
tmpfile=$(mktemp)
in_section=false
while IFS= read -r line; do
  if [[ "$line" == *"$START_MARKER"* ]]; then
    echo "$line" >> "$tmpfile"
    echo "$PROGRESS" >> "$tmpfile"
    in_section=true
  elif [[ "$line" == *"$END_MARKER"* ]]; then
    echo "$line" >> "$tmpfile"
    in_section=false
  elif [[ "$in_section" == false ]]; then
    echo "$line" >> "$tmpfile"
  fi
done < "$CLAUDE_MD"

mv "$tmpfile" "$CLAUDE_MD"
echo "Updated CLAUDE.md progress section"
