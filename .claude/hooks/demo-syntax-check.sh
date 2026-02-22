#!/bin/bash
# Hook: PostToolUse (Write|Edit) — 对 demos/ 下的 .py 文件做语法检查
# 编辑后立即用 py_compile 验证，防止引入语法错误

INPUT=$(cat)

# 提取被编辑的文件路径
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")

# 只检查 demos/ 下的 .py 文件
if [[ ! "$FILE_PATH" =~ /demos/ ]] || [[ ! "$FILE_PATH" =~ \.py$ ]]; then
  exit 0
fi

# 跳过不存在的文件（可能是 Write 失败）
if [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

# 语法检查（不能用 set -e，否则 py_compile 失败会直接退出）
RESULT=$(python3 -m py_compile "$FILE_PATH" 2>&1 || true)
EXIT_CODE=$(python3 -m py_compile "$FILE_PATH" 2>/dev/null; echo $?)

if [ "$EXIT_CODE" != "0" ]; then
  ESCAPED=$(echo "$RESULT" | sed 's/"/\\"/g' | tr '\n' ' ')
  echo "{\"systemMessage\": \"Syntax error in demo file: $ESCAPED\"}"
fi

exit 0
