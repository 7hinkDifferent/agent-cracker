#!/bin/bash
# Hook: SessionStart — 注入当前分析进度
# 读取 agents.yaml，输出各 agent 的 status，让 Claude 开局就知道项目进展

set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
YAML_FILE="$PROJECT_DIR/agents.yaml"

if [ ! -f "$YAML_FILE" ]; then
  exit 0
fi

# 提取 agent 状态列表
STATUS_LINES=""
while IFS= read -r line; do
  if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*(.*) ]]; then
    current_name="${BASH_REMATCH[1]}"
  fi
  if [[ "$line" =~ ^[[:space:]]*status:[[:space:]]*(.*) ]]; then
    current_status="${BASH_REMATCH[1]}"
    STATUS_LINES="$STATUS_LINES\n  - $current_name: $current_status"
  fi
done < "$YAML_FILE"

# 统计 demo 数量
DEMO_COUNT=0
if [ -d "$PROJECT_DIR/demos" ]; then
  DEMO_COUNT=$(find "$PROJECT_DIR/demos" -name "main.py" -o -name "repomap.py" | grep -v TEMPLATE | wc -l | tr -d ' ')
fi

CONTEXT="Current project status:${STATUS_LINES}\nTotal demos: $DEMO_COUNT"

# 输出 JSON
printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}' "$CONTEXT"
