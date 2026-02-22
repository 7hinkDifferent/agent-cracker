#!/bin/bash
# Hook: PreToolUse (Bash) — 提交前任务完成检查
# 在 git commit 执行前拦截，检查可自动验证的遗漏项。
# 发现问题则输出警告并阻断（exit 1），没有问题则静默放行（exit 0）。

INPUT=$(cat)

# 提取命令
COMMAND=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('tool_input', {}).get('command', ''))
" 2>/dev/null || echo "")

# 只拦截 git commit 命令
if [[ "$COMMAND" != *"git commit"* ]]; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
cd "$REPO_ROOT"

ISSUES=()

# 检查 1: 有未暂存的文档/配置变更
UNSTAGED_DOCS=$(git diff --name-only -- \
  docs/ CLAUDE.md README.md agents.yaml \
  'demos/*/README.md' .claude/ package.json 2>/dev/null || true)
if [ -n "$UNSTAGED_DOCS" ]; then
  ISSUES+=("未暂存的文档/配置变更（可能需要一起提交）: $UNSTAGED_DOCS")
fi

# 检查 2: 暂存了 scripts/ 或 .claude/ 但没暂存 CLAUDE.md
STAGED=$(git diff --cached --name-only 2>/dev/null || true)
if echo "$STAGED" | grep -qE '^(scripts/|\.claude/)'; then
  if ! echo "$STAGED" | grep -q '^CLAUDE.md$'; then
    ISSUES+=("修改了 scripts/ 或 .claude/ 但未更新 CLAUDE.md — 检查项目结构/命令/自动化是否需要同步")
  fi
fi

# 检查 3: 暂存了 docs/<agent>.md 但没更新 agents.yaml
if echo "$STAGED" | grep -E '^docs/[^/]+\.md$' | grep -qv TEMPLATE; then
  if ! echo "$STAGED" | grep -q '^agents.yaml$'; then
    ISSUES+=("新增/修改了分析文档但未更新 agents.yaml — 检查 status 是否需要变更")
  fi
fi

# 检查 4: 暂存了 demos/ 内容但没更新对应 overview
for demo_change in $(echo "$STAGED" | grep -E '^demos/[^/]+/[^/]+/' | \
  sed 's|^demos/\([^/]*\)/.*|\1|' | sort -u); do
  if ! echo "$STAGED" | grep -q "^demos/$demo_change/README.md$"; then
    ISSUES+=("修改了 demos/$demo_change/ 下的 demo 但未更新 demos/$demo_change/README.md overview")
  fi
done

# 检查 5: 暂存了新分析文档但未更新 analyzed_commit
for doc_change in $(echo "$STAGED" | grep -E '^docs/[^/]+\.md$' | grep -v TEMPLATE); do
  agent_name=$(basename "$doc_change" .md)
  if echo "$STAGED" | grep -q '^agents.yaml$'; then
    # agents.yaml 已暂存，检查是否包含 analyzed_commit 变更
    if ! git diff --cached agents.yaml 2>/dev/null | grep -q "analyzed_commit"; then
      ISSUES+=("暂存了 docs/$agent_name.md 和 agents.yaml，但 agents.yaml 中未更新 analyzed_commit — 检查是否需要 stamp commit")
    fi
  fi
done

if [ ${#ISSUES[@]} -gt 0 ]; then
  MSG="提交前检查发现以下可能遗漏："
  for issue in "${ISSUES[@]}"; do
    MSG="$MSG\n  - $issue"
  done
  MSG="$MSG\n请确认是否需要处理后再提交。"
  echo "$MSG"
  exit 1
fi

exit 0
