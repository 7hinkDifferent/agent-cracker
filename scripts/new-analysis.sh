#!/usr/bin/env bash
# new-analysis.sh — 从模板生成新的分析文档
# 用法: ./scripts/new-analysis.sh <agent-name>

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <agent-name>"
  echo "Example: $0 aider"
  exit 1
fi

AGENT_NAME="$1"
TEMPLATE="docs/TEMPLATE.md"
OUTPUT="docs/${AGENT_NAME}.md"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Error: Template not found at $TEMPLATE" >&2
  exit 1
fi

if [[ -f "$OUTPUT" ]]; then
  echo "Error: $OUTPUT already exists. Delete it first to regenerate." >&2
  exit 1
fi

# 从 agents.yaml 提取 repo URL
REPO_URL=""
name=""
while IFS= read -r line; do
  if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*(.*) ]]; then
    name="${BASH_REMATCH[1]}"
    name="${name%"${name##*[![:space:]]}"}"
  elif [[ "$line" =~ ^[[:space:]]*repo:[[:space:]]*(.*) ]]; then
    if [[ "$name" == "$AGENT_NAME" ]]; then
      REPO_URL="${BASH_REMATCH[1]}"
      REPO_URL="${REPO_URL%"${REPO_URL##*[![:space:]]}"}"
      break
    fi
  fi
done < agents.yaml

if [[ -z "$REPO_URL" ]]; then
  echo "Warning: $AGENT_NAME not found in agents.yaml, using placeholder repo URL"
  REPO_URL="https://github.com/UNKNOWN/UNKNOWN"
fi

DATE=$(date +%Y-%m-%d)

# 从 submodule 读取 HEAD SHA
COMMIT_SHA=""
COMMIT_SHORT=""
if [[ -d "projects/$AGENT_NAME" ]]; then
  COMMIT_SHA=$(git -C "projects/$AGENT_NAME" rev-parse HEAD 2>/dev/null || echo "")
  COMMIT_SHORT="${COMMIT_SHA:0:7}"
fi
COMMIT_DATE="$DATE"

# 替换模板中的占位符
sed -e "s/{{AGENT_NAME}}/${AGENT_NAME}/g" \
    -e "s|{{REPO_URL}}|${REPO_URL}|g" \
    -e "s/{{DATE}}/${DATE}/g" \
    -e "s/{{COMMIT_SHA}}/${COMMIT_SHA}/g" \
    -e "s/{{COMMIT_SHORT}}/${COMMIT_SHORT}/g" \
    -e "s/{{COMMIT_DATE}}/${COMMIT_DATE}/g" \
    "$TEMPLATE" > "$OUTPUT"

echo "Created: $OUTPUT"
