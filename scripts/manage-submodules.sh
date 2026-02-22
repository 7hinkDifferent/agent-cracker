#!/usr/bin/env bash
# manage-submodules.sh — 管理 projects/ 下的 agent repo (git submodule)
# 用法: ./scripts/manage-submodules.sh <command> [agent-name]
# 命令: add | update | init | status

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

AGENTS_FILE="agents.yaml"

if [[ ! -f "$AGENTS_FILE" ]]; then
  echo "Error: $AGENTS_FILE not found" >&2
  exit 1
fi

# 从 agents.yaml 提取 agent 信息（name 和 repo）
# 使用纯 bash 解析，避免依赖 yq
parse_agents() {
  local name="" repo=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*name:[[:space:]]*(.*) ]]; then
      name="${BASH_REMATCH[1]}"
      name="${name%"${name##*[![:space:]]}"}"  # trim trailing whitespace
    elif [[ "$line" =~ ^[[:space:]]*repo:[[:space:]]*(.*) ]]; then
      repo="${BASH_REMATCH[1]}"
      repo="${repo%"${repo##*[![:space:]]}"}"  # trim trailing whitespace
      if [[ -n "$name" && -n "$repo" ]]; then
        echo "$name|$repo"
      fi
      name="" repo=""
    fi
  done < "$AGENTS_FILE"
}

get_agent_repo() {
  local target="$1"
  parse_agents | while IFS='|' read -r name repo; do
    if [[ "$name" == "$target" ]]; then
      echo "$repo"
      return
    fi
  done
}

cmd_add() {
  local filter="${1:-}"
  parse_agents | while IFS='|' read -r name repo; do
    if [[ -n "$filter" && "$name" != "$filter" ]]; then
      continue
    fi
    local path="projects/$name"
    if [[ -d "$path" ]]; then
      echo "Skip: $name already exists at $path"
    else
      echo "Adding submodule (shallow): $name -> $path"
      git submodule add --depth=1 "$repo" "$path"
    fi
  done
}

cmd_update() {
  local filter="${1:-}"
  if [[ -n "$filter" ]]; then
    local path="projects/$filter"
    if [[ -d "$path" ]]; then
      echo "Updating: $filter"
      git submodule update --remote "$path"
    else
      echo "Error: $filter not found in projects/" >&2
      exit 1
    fi
  else
    echo "Updating all submodules..."
    git submodule update --remote
  fi
}

cmd_init() {
  echo "Initializing all submodules (shallow)..."
  git submodule update --init --depth=1
}

cmd_status() {
  echo "=== Submodule Status ==="
  git submodule status
  echo ""
  echo "=== agents.yaml vs submodules ==="
  parse_agents | while IFS='|' read -r name repo; do
    if [[ -d "projects/$name" ]]; then
      echo "  [ok] $name"
    else
      echo "  [--] $name (not added)"
    fi
  done
}

# Main
command="${1:-}"
agent="${2:-}"

case "$command" in
  add)    cmd_add "$agent" ;;
  update) cmd_update "$agent" ;;
  init)   cmd_init ;;
  status) cmd_status ;;
  *)
    echo "Usage: $0 <add|update|init|status> [agent-name]"
    echo ""
    echo "Commands:"
    echo "  add [name]     Add agent(s) as git submodule"
    echo "  update [name]  Update submodule(s) to latest commit"
    echo "  init           Initialize and clone all submodules"
    echo "  status         Show submodule status"
    exit 1
    ;;
esac
