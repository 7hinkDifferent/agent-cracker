#!/usr/bin/env bash
# gen-readme.sh — 从 agents.yaml 自动更新 README.md 和 README.en.md 中的 agent 表格和徽章
# 用法: ./scripts/gen-readme.sh

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

AGENTS_FILE="agents.yaml"
README="README.md"
README_EN="README.en.md"
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

# 中文 category → 英文 category 翻译
translate_category() {
  case "$1" in
    平台)    echo "Platform" ;;
    IDE插件) echo "IDE Plugin" ;;
    研究)    echo "Research" ;;
    自治)    echo "Autonomous" ;;
    *)       echo "$1" ;;  # CLI, Web 等英文原样保留
  esac
}

# 生成表格内容
# 参数 $1: "zh" (原样) 或 "en" (翻译 category)
generate_table() {
  local lang="${1:-zh}"
  echo "| Agent | Language | Category | Status | Repo |"
  echo "|-------|----------|----------|--------|------|"

  local name="" language="" category="" status="" repo="" description=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*(.*) ]]; then
      # 输出上一个 agent（如果有）
      if [[ -n "$name" ]]; then
        local display_cat="$category"
        [[ "$lang" == "en" ]] && display_cat=$(translate_category "$category")
        local repo_short="${repo#https://github.com/}"
        echo "| [${name}](${repo}) | ${language} | ${display_cat} | ${status} | \`${repo_short}\` |"
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
    local display_cat="$category"
    [[ "$lang" == "en" ]] && display_cat=$(translate_category "$category")
    local repo_short="${repo#https://github.com/}"
    echo "| [${name}](${repo}) | ${language} | ${display_cat} | ${status} | \`${repo_short}\` |"
  fi
}

# 替换指定文件中 marker 之间的表格内容
replace_table() {
  local target_file="$1"
  local table_content="$2"
  local tmpfile
  tmpfile=$(mktemp)
  local in_table=false
  while IFS= read -r line; do
    if [[ "$line" == *"$START_MARKER"* ]]; then
      echo "$line" >> "$tmpfile"
      echo "" >> "$tmpfile"
      echo "$table_content" >> "$tmpfile"
      echo "" >> "$tmpfile"
      in_table=true
    elif [[ "$line" == *"$END_MARKER"* ]]; then
      echo "$line" >> "$tmpfile"
      in_table=false
    elif [[ "$in_table" == false ]]; then
      echo "$line" >> "$tmpfile"
    fi
  done < "$target_file"
  mv "$tmpfile" "$target_file"
}

# ── 更新表格 ──

TABLE_ZH=$(generate_table zh)
replace_table "$README" "$TABLE_ZH"
echo "Updated agent table in $README"

if [[ -f "$README_EN" ]]; then
  TABLE_EN=$(generate_table en)
  replace_table "$README_EN" "$TABLE_EN"
  echo "Updated agent table in $README_EN"
fi

# ── 更新徽章 ──

DEMO_COUNT=$(find demos -mindepth 2 -maxdepth 2 -type d ! -name TEMPLATE 2>/dev/null | wc -l | tr -d ' ')
AGENT_COUNT=$(grep -c '^[[:space:]]*- name:' "$AGENTS_FILE")

for f in "$README" "$README_EN"; do
  [[ ! -f "$f" ]] && continue
  sed -i '' "s/Demos-[0-9]*/Demos-${DEMO_COUNT}/" "$f"
  sed -i '' "s/Agents-[0-9]*/Agents-${AGENT_COUNT}/" "$f"
done
echo "Updated badges: Agents=${AGENT_COUNT}, Demos=${DEMO_COUNT}"
