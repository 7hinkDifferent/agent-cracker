#!/usr/bin/env bash
# update-stars.sh — 通过 GitHub API 更新 agents.yaml 中的 star 数
# 用法: ./scripts/update-stars.sh
# 需要: curl, 可选设置 GITHUB_TOKEN 避免 rate limit

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

AGENTS_FILE="agents.yaml"

if [[ ! -f "$AGENTS_FILE" ]]; then
  echo "Error: $AGENTS_FILE not found" >&2
  exit 1
fi

AUTH_HEADER=""
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  AUTH_HEADER="Authorization: token $GITHUB_TOKEN"
fi

echo "Fetching star counts from GitHub API..."
echo ""

# 提取 repo URL 并查询 star 数
while IFS= read -r line; do
  if [[ "$line" =~ ^[[:space:]]*repo:[[:space:]]*(.*) ]]; then
    repo_url="${BASH_REMATCH[1]}"
    repo_url="${repo_url%"${repo_url##*[![:space:]]}"}"
    # 从 URL 提取 owner/repo
    repo_path="${repo_url#https://github.com/}"
    repo_path="${repo_path%.git}"

    if [[ -n "$AUTH_HEADER" ]]; then
      stars=$(curl -s -H "$AUTH_HEADER" "https://api.github.com/repos/${repo_path}" | grep -m1 '"stargazers_count"' | grep -o '[0-9]*')
    else
      stars=$(curl -s "https://api.github.com/repos/${repo_path}" | grep -m1 '"stargazers_count"' | grep -o '[0-9]*')
    fi

    if [[ -n "$stars" ]]; then
      printf "  %-20s %s stars\n" "$repo_path" "$stars"
    else
      printf "  %-20s (failed to fetch)\n" "$repo_path"
    fi
  fi
done < "$AGENTS_FILE"

echo ""
echo "Done. Star counts displayed above (not written to agents.yaml)."
echo "To persist, manually add 'stars: N' fields to agents.yaml."
