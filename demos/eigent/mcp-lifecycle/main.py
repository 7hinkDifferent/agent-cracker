"""
Eigent — MCP Server Lifecycle Demo

复现 eigent 的 MCP 服务器全生命周期管理：
- 安装流程: validate_config → pre_instantiate → connect → get_tools → disconnect
- Auth 目录管理: ~/.mcp-auth
- 连接重试: 3 次尝试, 2 秒间隔
- 工具发现: 从 MCP server 获取可用工具列表
- Server 配置: command/args/env

对应源码: server/app/controller/mcp/mcp_controller.py
         backend/app/agent/toolkit/notion_mcp_toolkit.py
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ── MCP 配置与状态 ────────────────────────────────────────────────

class ServerState(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class McpServerConfig:
    """MCP 服务器配置 — 对应 mcpServers 配置格式。

    原实现: 从 mcp_config JSON 读取，包含 command, args, env。
    示例:
    {
        "notion": {
            "command": "npx",
            "args": ["-y", "@notionhq/notion-mcp-server"],
            "env": {"OPENAPI_MCP_HEADERS": "..."}
        }
    }
    """
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class McpTool:
    """MCP 工具描述"""
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


# ── Auth 目录管理 ─────────────────────────────────────────────────

class AuthManager:
    """
    MCP Auth 目录管理 — 对应原实现的 auth_dir 管理。

    原实现: mcp_controller.py 中确保 ~/.mcp-auth 目录存在，
    用于存储 OAuth token 等认证信息。
    """

    def __init__(self, auth_dir: Optional[str] = None):
        self.auth_dir = Path(auth_dir or os.path.expanduser("~/.mcp-auth"))

    def ensure_auth_dir(self) -> Path:
        """确保 auth 目录存在"""
        # Demo 不真正创建目录，仅模拟
        print(f"    [auth] 检查 auth 目录: {self.auth_dir}")
        if self.auth_dir.exists():
            print(f"    [auth] 目录已存在")
        else:
            print(f"    [auth] 目录不存在, 将创建 (模拟)")
        return self.auth_dir

    def get_token_path(self, server_name: str) -> Path:
        """获取指定 server 的 token 存储路径"""
        return self.auth_dir / f"{server_name}.json"


# ── MCP Server 生命周期管理 ───────────────────────────────────────

class McpServerManager:
    """
    MCP Server 全生命周期管理器。

    对应源码:
    - server/app/controller/mcp/mcp_controller.py: 安装 + 连接管理
    - backend/app/agent/toolkit/notion_mcp_toolkit.py: 工具注入

    生命周期:
    1. validate_config() — 校验配置合法性
    2. pre_instantiate() — 预初始化（auth 目录、环境变量）
    3. connect()         — 建立连接（支持重试）
    4. get_tools()       — 发现可用工具
    5. disconnect()      — 断开连接
    """

    MAX_RETRIES = 3
    RETRY_DELAY = 2.0  # 秒

    def __init__(self):
        self.auth_manager = AuthManager(auth_dir="/tmp/mcp-auth-demo")
        self._servers: dict[str, ServerState] = {}
        self._tools: dict[str, list[McpTool]] = {}

    def install(self, config: McpServerConfig) -> bool:
        """
        完整安装流程 — validate → pre_instantiate → connect → get_tools。

        原实现: mcp_controller.py 的 install 端点
        """
        print(f"\n  === 安装 MCP Server: {config.name} ===")

        # Step 1: 校验配置
        if not self._validate_config(config):
            return False

        # Step 2: 预初始化
        self._pre_instantiate(config)

        # Step 3: 连接（带重试）
        if not self._connect_with_retry(config):
            return False

        # Step 4: 发现工具
        tools = self._discover_tools(config)
        self._tools[config.name] = tools

        print(f"\n  [OK] {config.name} 安装完成, 发现 {len(tools)} 个工具")
        return True

    def _validate_config(self, config: McpServerConfig) -> bool:
        """Step 1: 校验配置合法性"""
        print(f"\n  [1/4] 校验配置...")

        if not config.command:
            print(f"    [FAIL] command 不能为空")
            self._servers[config.name] = ServerState.ERROR
            return False

        if not config.name:
            print(f"    [FAIL] name 不能为空")
            return False

        print(f"    command: {config.command}")
        print(f"    args: {config.args}")
        print(f"    env: {list(config.env.keys())}")
        print(f"    [OK] 配置有效")
        return True

    def _pre_instantiate(self, config: McpServerConfig) -> None:
        """Step 2: 预初始化 — auth 目录 + 环境变量注入"""
        print(f"\n  [2/4] 预初始化...")

        # 确保 auth 目录
        self.auth_manager.ensure_auth_dir()

        # 模拟环境变量注入
        for key, value in config.env.items():
            masked = value[:8] + "..." if len(value) > 8 else value
            print(f"    [env] {key}={masked}")

        self._servers[config.name] = ServerState.IDLE
        print(f"    [OK] 预初始化完成")

    def _connect_with_retry(self, config: McpServerConfig) -> bool:
        """Step 3: 建立连接（最多 3 次重试，间隔 2 秒）

        原实现: 使用 stdio transport 连接 MCP server 进程
        """
        print(f"\n  [3/4] 连接 MCP Server...")
        self._servers[config.name] = ServerState.CONNECTING

        for attempt in range(1, self.MAX_RETRIES + 1):
            print(f"    [尝试 {attempt}/{self.MAX_RETRIES}] "
                  f"连接 {config.command} {' '.join(config.args)}...")

            success = self._simulate_connection(config, attempt)

            if success:
                self._servers[config.name] = ServerState.CONNECTED
                print(f"    [OK] 连接成功 (第 {attempt} 次)")
                return True

            print(f"    [FAIL] 连接失败")
            if attempt < self.MAX_RETRIES:
                # Demo 使用极短延迟代替真实的 2 秒
                print(f"    等待 {self.RETRY_DELAY}s 后重试 (模拟)...")
                time.sleep(0.1)  # 实际延迟缩短为 0.1s

        self._servers[config.name] = ServerState.ERROR
        print(f"    [!] {self.MAX_RETRIES} 次尝试均失败")
        return False

    def _simulate_connection(self, config: McpServerConfig, attempt: int) -> bool:
        """模拟连接结果（替代真实进程启动）"""
        # 模拟: "bad-server" 始终失败, "flaky-server" 第 3 次成功, 其余首次成功
        if config.name == "bad-server":
            return False
        if config.name == "flaky-server":
            return attempt >= 3
        return True

    def _discover_tools(self, config: McpServerConfig) -> list[McpTool]:
        """Step 4: 工具发现 — 从 MCP server 获取可用工具列表

        原实现: 调用 MCP protocol 的 tools/list 方法
        """
        print(f"\n  [4/4] 发现工具...")

        # 模拟不同 server 的工具列表
        tool_registry: dict[str, list[McpTool]] = {
            "notion": [
                McpTool("notion_search", "Search Notion pages",
                        {"type": "object", "properties": {"query": {"type": "string"}}}),
                McpTool("notion_read_page", "Read a Notion page by ID",
                        {"type": "object", "properties": {"page_id": {"type": "string"}}}),
                McpTool("notion_create_page", "Create a new Notion page",
                        {"type": "object", "properties": {"title": {"type": "string"},
                                                          "content": {"type": "string"}}}),
            ],
            "github": [
                McpTool("github_search_repos", "Search GitHub repositories",
                        {"type": "object", "properties": {"query": {"type": "string"}}}),
                McpTool("github_create_issue", "Create a GitHub issue",
                        {"type": "object", "properties": {"repo": {"type": "string"},
                                                          "title": {"type": "string"}}}),
            ],
            "flaky-server": [
                McpTool("flaky_ping", "Ping the flaky server", {}),
            ],
        }

        tools = tool_registry.get(config.name, [
            McpTool(f"{config.name}_default", f"Default tool for {config.name}", {}),
        ])

        for tool in tools:
            print(f"    - {tool.name}: {tool.description}")

        return tools

    def disconnect(self, server_name: str) -> None:
        """Step 5: 断开连接"""
        if server_name in self._servers:
            self._servers[server_name] = ServerState.DISCONNECTED
            self._tools.pop(server_name, None)
            print(f"  [{server_name}] 已断开连接")

    def get_status(self, server_name: str) -> ServerState:
        return self._servers.get(server_name, ServerState.IDLE)

    def get_tools(self, server_name: str) -> list[McpTool]:
        return self._tools.get(server_name, [])


# ── Demo ─────────────────────────────────────────────────────────

def main():
    print("=" * 68)
    print("Eigent MCP Server Lifecycle Demo")
    print("=" * 68)

    manager = McpServerManager()

    # ── 场景 1: Notion MCP Server 正常安装 ────────────────────
    print("\n" + "-" * 60)
    print("场景 1: Notion MCP Server 正常安装")
    print("-" * 60)

    notion_config = McpServerConfig(
        name="notion",
        command="npx",
        args=["-y", "@notionhq/notion-mcp-server"],
        env={"OPENAPI_MCP_HEADERS": '{"Authorization": "Bearer ntn_xxx"}'},
    )
    manager.install(notion_config)

    # ── 场景 2: 不稳定服务器（第 3 次连接成功）──────────────
    print("\n" + "-" * 60)
    print("场景 2: 不稳定服务器 (第 3 次连接成功)")
    print("-" * 60)

    flaky_config = McpServerConfig(
        name="flaky-server",
        command="node",
        args=["flaky-mcp-server.js"],
    )
    manager.install(flaky_config)

    # ── 场景 3: 始终失败的服务器 ──────────────────────────────
    print("\n" + "-" * 60)
    print("场景 3: 始终失败的服务器 (3 次重试均失败)")
    print("-" * 60)

    bad_config = McpServerConfig(
        name="bad-server",
        command="bad-command",
        args=["--broken"],
    )
    manager.install(bad_config)

    # ── 场景 4: 无效配置 ──────────────────────────────────────
    print("\n" + "-" * 60)
    print("场景 4: 无效配置 (空 command)")
    print("-" * 60)

    invalid_config = McpServerConfig(name="invalid", command="")
    manager.install(invalid_config)

    # ── 状态汇总 ──────────────────────────────────────────────
    print("\n" + "=" * 68)
    print("Server 状态汇总")
    print("=" * 68)

    for name in ["notion", "flaky-server", "bad-server", "invalid"]:
        state = manager.get_status(name)
        tools = manager.get_tools(name)
        tool_names = [t.name for t in tools]
        print(f"  {name:15s} | 状态: {state.value:12s} | 工具: {tool_names}")

    # ── 断开连接 ──────────────────────────────────────────────
    print(f"\n{'─' * 40}")
    print("断开所有连接")
    print("─" * 40)

    for name in ["notion", "flaky-server"]:
        manager.disconnect(name)
    print(f"  最终状态: notion={manager.get_status('notion').value}, "
          f"flaky-server={manager.get_status('flaky-server').value}")


if __name__ == "__main__":
    main()
