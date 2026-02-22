#!/bin/bash
# Hook: PostToolUse (Write|Edit) — 验证 agents.yaml 格式
# 编辑 agents.yaml 后自动校验基本结构，防止破坏这个单一数据源

set -e

INPUT=$(cat)

# 提取被编辑的文件路径
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")

# 只检查 agents.yaml
if [[ "$FILE_PATH" != *"agents.yaml" ]]; then
  exit 0
fi

if [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

ERRORS=""

# 检查 1: 文件必须包含 "agents:" 顶层 key
if ! grep -q "^agents:" "$FILE_PATH"; then
  ERRORS="Missing top-level 'agents:' key"
fi

# 检查 2: 统计各字段数量
AGENT_COUNT=$(grep -c "\- name:" "$FILE_PATH" 2>/dev/null || echo 0)
REPO_COUNT=$(grep -c "repo:" "$FILE_PATH" 2>/dev/null || echo 0)
STATUS_COUNT=$(grep -c "status:" "$FILE_PATH" 2>/dev/null || echo 0)

# 去除空白
AGENT_COUNT=$(echo "$AGENT_COUNT" | tr -d '[:space:]')
REPO_COUNT=$(echo "$REPO_COUNT" | tr -d '[:space:]')
STATUS_COUNT=$(echo "$STATUS_COUNT" | tr -d '[:space:]')

if [ "$AGENT_COUNT" -eq 0 ]; then
  ERRORS="${ERRORS} No agents found."
elif [ "$REPO_COUNT" -lt "$AGENT_COUNT" ]; then
  ERRORS="${ERRORS} Some agents missing 'repo:' field."
elif [ "$STATUS_COUNT" -lt "$AGENT_COUNT" ]; then
  ERRORS="${ERRORS} Some agents missing 'status:' field."
fi

# 检查 3: status 值必须是已知值
BAD_STATUS=$(grep "status:" "$FILE_PATH" | grep -v -E "pending|in-progress|done" || true)
if [ -n "$BAD_STATUS" ]; then
  ERRORS="${ERRORS} Unknown status values found."
fi

if [ -n "$ERRORS" ]; then
  ESCAPED=$(echo "$ERRORS" | sed 's/"/\\"/g')
  echo "{\"systemMessage\": \"agents.yaml validation FAILED: $ESCAPED\"}"
else
  echo "{\"systemMessage\": \"agents.yaml OK: $AGENT_COUNT agents validated\"}"
fi

exit 0
