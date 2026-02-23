#!/bin/bash
# Hook: PostToolUse (Write|Edit) — 对 demos/ 下的源码文件做多语言语法检查
# 编辑后立即验证，防止引入语法错误
# 支持: .py (py_compile) / .ts (tsc --noEmit) / .rs (cargo check)

INPUT=$(cat)

# 提取被编辑的文件路径
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")

# 只检查 demos/ 下的源码文件
if [[ ! "$FILE_PATH" =~ /demos/ ]]; then
  exit 0
fi

# 跳过不存在的文件（可能是 Write 失败）
if [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

# Python 语法检查
if [[ "$FILE_PATH" =~ \.py$ ]]; then
  RESULT=$(python3 -m py_compile "$FILE_PATH" 2>&1 || true)
  EXIT_CODE=$(python3 -m py_compile "$FILE_PATH" 2>/dev/null; echo $?)

  if [ "$EXIT_CODE" != "0" ]; then
    ESCAPED=$(echo "$RESULT" | sed 's/"/\\"/g' | tr '\n' ' ')
    echo "{\"systemMessage\": \"Syntax error in demo file: $ESCAPED\"}"
  fi
fi

# TypeScript 语法检查
if [[ "$FILE_PATH" =~ \.ts$ ]]; then
  if command -v npx >/dev/null 2>&1; then
    DEMO_DIR=$(dirname "$FILE_PATH")
    if [ -f "$DEMO_DIR/tsconfig.json" ]; then
      RESULT=$(cd "$DEMO_DIR" && npx tsc --noEmit 2>&1 || true)
      EXIT_CODE=$?
      if [ "$EXIT_CODE" != "0" ]; then
        ESCAPED=$(echo "$RESULT" | sed 's/"/\\"/g' | tr '\n' ' ')
        echo "{\"systemMessage\": \"TypeScript error in demo file: $ESCAPED\"}"
      fi
    fi
  fi
fi

# Rust 语法检查
if [[ "$FILE_PATH" =~ \.rs$ ]]; then
  if command -v cargo >/dev/null 2>&1; then
    DEMO_DIR=$(dirname "$FILE_PATH")
    # 如果 .rs 在 src/ 下，Cargo.toml 在上一层
    if [ -f "$DEMO_DIR/../Cargo.toml" ]; then
      DEMO_DIR="$DEMO_DIR/.."
    fi
    if [ -f "$DEMO_DIR/Cargo.toml" ]; then
      RESULT=$(cd "$DEMO_DIR" && cargo check 2>&1 || true)
      EXIT_CODE=$?
      if [ "$EXIT_CODE" != "0" ]; then
        ESCAPED=$(echo "$RESULT" | head -20 | sed 's/"/\\"/g' | tr '\n' ' ')
        echo "{\"systemMessage\": \"Rust check error in demo file: $ESCAPED\"}"
      fi
    fi
  fi
fi

exit 0
