"""
OpenClaw — Docker Sandbox 机制复现

复现 OpenClaw 的 Docker 容器沙箱隔离：
- 容器生命周期管理（create → start → exec → stop）
- Workspace mount + 安全校验（禁止父目录逃逸）
- Config hash 变更检测（配置变化自动重建容器）
- Elevated exec 审批（ask / auto-approve）
- 热容器窗口（复用最近使用的容器）

对应源码: src/agents/sandbox/docker.ts, validate-sandbox-security.ts
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Optional


# ── 数据模型 ──────────────────────────────────────────────────────

class WorkspaceAccess(str, Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class ElevatedExecPolicy(str, Enum):
    ASK = "ask"              # 需要用户确认
    AUTO_APPROVE = "auto-approve"


@dataclass
class SandboxConfig:
    """沙箱配置"""
    image: str = "ubuntu:22.04"
    workspace_path: str = "/home/user/project"
    container_workspace: str = "/agent/workspace"
    workspace_access: WorkspaceAccess = WorkspaceAccess.WRITE
    elevated_exec: ElevatedExecPolicy = ElevatedExecPolicy.ASK
    env_vars: dict[str, str] = field(default_factory=dict)
    extra_mounts: list[str] = field(default_factory=list)
    browser_bridge: bool = False
    hot_window_seconds: int = 300  # 5 分钟热容器窗口

    def config_hash(self) -> str:
        """配置 hash，用于检测变更"""
        parts = [
            self.image,
            self.workspace_path,
            self.container_workspace,
            self.workspace_access.value,
            str(sorted(self.env_vars.items())),
            str(sorted(self.extra_mounts)),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


@dataclass
class Container:
    """容器实例"""
    container_id: str
    config_hash: str
    created_at: float
    last_used: float
    running: bool = False
    exec_history: list[str] = field(default_factory=list)


# ── 安全校验 ──────────────────────────────────────────────────────

DANGEROUS_MOUNTS = {"/", "/etc", "/var", "/root", "/home", "/proc", "/sys", "/dev"}


class SecurityValidator:
    """沙箱安全校验器"""

    @staticmethod
    def validate_mount(host_path: str, container_path: str) -> tuple[bool, str]:
        """校验挂载路径安全性"""
        # 禁止父目录逃逸（路径遍历）
        normalized = str(PurePosixPath(host_path))
        if ".." in normalized:
            return False, f"Path traversal detected: {host_path}"

        # 禁止危险目录
        for dangerous in DANGEROUS_MOUNTS:
            if normalized == dangerous:
                return False, f"Mounting dangerous directory: {host_path}"

        # 容器内路径不能是根
        if container_path in ("/", ""):
            return False, f"Cannot mount to container root"

        return True, "OK"

    @staticmethod
    def validate_config(config: SandboxConfig) -> list[str]:
        """全面校验沙箱配置"""
        errors = []

        # 校验 workspace mount
        ok, msg = SecurityValidator.validate_mount(
            config.workspace_path, config.container_workspace
        )
        if not ok:
            errors.append(f"Workspace mount: {msg}")

        # 校验额外挂载
        for mount in config.extra_mounts:
            parts = mount.split(":")
            if len(parts) < 2:
                errors.append(f"Invalid mount format: {mount}")
                continue
            ok, msg = SecurityValidator.validate_mount(parts[0], parts[1])
            if not ok:
                errors.append(f"Extra mount: {msg}")

        return errors


# ── Docker 沙箱管理器 ────────────────────────────────────────────

class DockerSandbox:
    """
    OpenClaw Docker Sandbox 复现

    核心机制：
    1. 配置 hash 变更检测 — 配置变化时自动重建容器
    2. 热容器窗口 — 5 分钟内复用已有容器
    3. Workspace mount — 受控挂载 + 安全校验
    4. Elevated exec — 危险命令需要审批
    5. 安全基线 — cap-drop, no-new-privileges
    """

    def __init__(self):
        self.containers: dict[str, Container] = {}  # session_key → Container
        self._id_counter = 0

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"sandbox-{self._id_counter:04d}"

    def ensure_container(self, session_key: str, config: SandboxConfig) -> tuple[Container, str]:
        """
        确保容器可用

        返回 (container, action):
        - action: "created" / "reused" / "recreated"
        """
        now = time.time()
        new_hash = config.config_hash()

        # 安全校验
        errors = SecurityValidator.validate_config(config)
        if errors:
            raise ValueError(f"Security validation failed: {'; '.join(errors)}")

        existing = self.containers.get(session_key)

        # 检查是否可复用
        if existing and existing.running:
            # 配置变更 → 重建
            if existing.config_hash != new_hash:
                self._stop_container(existing)
                container = self._create_container(session_key, config, new_hash, now)
                return container, "recreated"

            # 热窗口内 → 复用
            if now - existing.last_used < config.hot_window_seconds:
                existing.last_used = now
                return existing, "reused"

            # 过期 → 重建
            self._stop_container(existing)

        container = self._create_container(session_key, config, new_hash, now)
        return container, "created"

    def exec_command(
        self,
        container: Container,
        command: str,
        elevated: bool = False,
        config: Optional[SandboxConfig] = None,
    ) -> tuple[bool, str]:
        """
        在容器内执行命令

        elevated 命令需要根据策略审批
        """
        if not container.running:
            return False, "Container not running"

        if elevated and config:
            if config.elevated_exec == ElevatedExecPolicy.ASK:
                return False, f"Elevated command requires approval: {command}"

        # 模拟执行
        container.exec_history.append(command)
        return True, f"Executed: {command}"

    def build_docker_args(self, config: SandboxConfig) -> list[str]:
        """构建 docker create 参数"""
        args = [
            "docker", "create",
            "--name", f"openclaw-{config.config_hash()[:8]}",
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
        ]

        # Workspace mount
        ro_suffix = ":ro" if config.workspace_access == WorkspaceAccess.READ else ""
        args.extend(["-v", f"{config.workspace_path}:{config.container_workspace}{ro_suffix}"])

        # 环境变量
        for key, val in config.env_vars.items():
            args.extend(["-e", f"{key}={val}"])

        # 额外挂载
        for mount in config.extra_mounts:
            args.extend(["-v", mount])

        # Label
        args.extend(["--label", f"openclaw.configHash={config.config_hash()}"])

        args.append(config.image)
        return args

    def _create_container(
        self, session_key: str, config: SandboxConfig, config_hash: str, now: float
    ) -> Container:
        container = Container(
            container_id=self._next_id(),
            config_hash=config_hash,
            created_at=now,
            last_used=now,
            running=True,
        )
        self.containers[session_key] = container
        return container

    def _stop_container(self, container: Container):
        container.running = False


# ── Demo ──────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("OpenClaw Docker Sandbox Demo")
    print("=" * 64)

    sandbox = DockerSandbox()

    # ── 1. 安全校验 ──
    print("\n── 1. 安全校验 ──")

    test_mounts = [
        ("/home/user/project", "/agent/workspace", True),
        ("/../etc/passwd", "/data", False),
        ("/", "/root-mount", False),
        ("/etc", "/config", False),
        ("/home/user/docs", "/agent/docs", True),
    ]

    for host, container, expected_ok in test_mounts:
        ok, msg = SecurityValidator.validate_mount(host, container)
        status = "✓" if ok == expected_ok else "✗"
        print(f"  {status} {host:25s} → {container:20s} {'OK' if ok else msg}")

    # ── 2. 容器生命周期 ──
    print("\n── 2. 容器生命周期 ──")

    config = SandboxConfig(
        image="node:22-slim",
        workspace_path="/home/user/project",
        env_vars={"NODE_ENV": "development"},
    )

    container, action = sandbox.ensure_container("session-1", config)
    print(f"  首次创建: id={container.container_id}, action={action}, hash={container.config_hash}")

    container2, action2 = sandbox.ensure_container("session-1", config)
    print(f"  热窗口复用: id={container2.container_id}, action={action2}")

    # 配置变更 → 自动重建
    config_updated = SandboxConfig(
        image="node:22-slim",
        workspace_path="/home/user/project",
        env_vars={"NODE_ENV": "production"},  # 变了
    )
    container3, action3 = sandbox.ensure_container("session-1", config_updated)
    print(f"  配置变更重建: id={container3.container_id}, action={action3}, new_hash={container3.config_hash}")

    # ── 3. 命令执行 ──
    print("\n── 3. 命令执行 ──")

    ok, msg = sandbox.exec_command(container3, "npm test")
    print(f"  普通命令: {msg}")

    ok, msg = sandbox.exec_command(container3, "rm -rf /", elevated=True, config=config_updated)
    print(f"  Elevated (ask): {msg}")

    config_auto = SandboxConfig(elevated_exec=ElevatedExecPolicy.AUTO_APPROVE)
    ok, msg = sandbox.exec_command(container3, "apt install -y git", elevated=True, config=config_auto)
    print(f"  Elevated (auto): {msg}")

    # ── 4. Docker args 构建 ──
    print("\n── 4. Docker create 参数 ──")
    args = sandbox.build_docker_args(config)
    print(f"  {' '.join(args)}")

    # 只读挂载
    ro_config = SandboxConfig(workspace_access=WorkspaceAccess.READ)
    args_ro = sandbox.build_docker_args(ro_config)
    mount_arg = [a for a in args_ro if "/agent/workspace" in a]
    print(f"  只读挂载: {mount_arg}")


if __name__ == "__main__":
    main()
