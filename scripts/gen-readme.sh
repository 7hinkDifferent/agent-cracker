#!/usr/bin/env bash
# gen-readme.sh — 从 agents.yaml 自动更新 README.md 中的 agent 表格
# 用法: ./scripts/gen-readme.sh

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

AGENTS_FILE="agents.yaml"
README="README.md"
START_MARKER="<!-- AGENT_TABLE_START -->"
END_MARKER="<!-- AGENT_TABLE_END -->"

if [[ ! -f "$AGENTS_FILE" ]]; then
  echo "Error: $AGENTS_FILE not found" >&2
  exit 1
fi

if [[ ! -f "$README" ]]; then
  echo "Error: $README not found" >&2
  exit 1
fi

# 生成表格内容
generate_table() {
  echo "| Agent | Language | Category | Status | Repo |"
  echo "|-------|----------|----------|--------|------|"

  local name="" language="" category="" status="" repo="" description=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*(.*) ]]; then
      # 输出上一个 agent（如果有）
      if [[ -n "$name" ]]; then
        local repo_short="${repo#https://github.com/}"
        echo "| [${name}](${repo}) | ${language} | ${category} | ${status} | \`${repo_short}\` |"
      fi
      name="${BASH_REMATCH[1]}"
      name="${name%"${name##*[![:space:]]}"}"
      language="" category="" status="" repo=""
    elif [[ "$line" =~ ^[[:space:]]*language:[[:space:]]*(.*) ]]; then
      language="${BASH_REMATCH[1]}"
      language="${language%"${language##*[![:space:]]}"}"
    elif [[ "$line" =~ ^[[:space:]]*category:[[:space:]]*(.*) ]]; then
      category="${BASH_REMATCH[1]}"
      category="${category%"${category##*[![:space:]]}"}"
    elif [[ "$line" =~ ^[[:space:]]*status:[[:space:]]*(.*) ]]; then
      status="${BASH_REMATCH[1]}"
      status="${status%"${status##*[![:space:]]}"}"
    elif [[ "$line" =~ ^[[:space:]]*repo:[[:space:]]*(.*) ]]; then
      repo="${BASH_REMATCH[1]}"
      repo="${repo%"${repo##*[![:space:]]}"}"
    fi
  done < "$AGENTS_FILE"
  # 输出最后一个 agent
  if [[ -n "$name" ]]; then
    local repo_short="${repo#https://github.com/}"
    echo "| [${name}](${repo}) | ${language} | ${category} | ${status} | \`${repo_short}\` |"
  fi
}

TABLE=$(generate_table)

# 替换 README 中 marker 之间的内容
tmpfile=$(mktemp)
in_table=false
while IFS= read -r line; do
  if [[ "$line" == *"$START_MARKER"* ]]; then
    echo "$line" >> "$tmpfile"
    echo "" >> "$tmpfile"
    echo "$TABLE" >> "$tmpfile"
    echo "" >> "$tmpfile"
    in_table=true
  elif [[ "$line" == *"$END_MARKER"* ]]; then
    echo "$line" >> "$tmpfile"
    in_table=false
  elif [[ "$in_table" == false ]]; then
    echo "$line" >> "$tmpfile"
  fi
done < "$README"

mv "$tmpfile" "$README"
echo "Updated agent table in $README"
