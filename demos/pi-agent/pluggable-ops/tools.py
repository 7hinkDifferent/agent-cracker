"""
Pluggable Operations — 可插拔操作层

复现 pi-agent 的 Pluggable Operations 模式：
  工具通过 Protocol 抽象底层操作，工厂函数注入实现，
  同一 tool 代码透明切换执行环境

核心设计：
  - Operations Protocol 定义抽象接口（read_file, run_command）
  - 默认实现用本地 I/O，可替换为 SSH/Docker 等远程实现
  - Tool 工厂函数接受 operations 参数，None 时用默认实现
  - Tool 逻辑与执行环境完全解耦

原实现: packages/coding-agent/src/core/tools/ (read.ts, bash.ts, write.ts)
"""

import os
from typing import Protocol, runtime_checkable


# ── Operations Protocol ───────────────────────────────────────

@runtime_checkable
class FileOperations(Protocol):
    """文件操作抽象接口（对应 ReadOperations + WriteOperations）"""
    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> None: ...
    def file_exists(self, path: str) -> bool: ...


@runtime_checkable
class ShellOperations(Protocol):
    """Shell 操作抽象接口（对应 BashOperations）"""
    def run_command(self, command: str, cwd: str) -> tuple[int, str]: ...


# ── 3 种实现 ──────────────────────────────────────────────────

class LocalOps:
    """本地实现：真实文件 I/O 和 shell 执行"""

    def read_file(self, path: str) -> str:
        with open(path, "r") as f:
            return f.read()

    def write_file(self, path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def run_command(self, command: str, cwd: str) -> tuple[int, str]:
        import subprocess
        result = subprocess.run(
            command, shell=True, cwd=cwd,
            capture_output=True, text=True,
        )
        output = result.stdout + result.stderr
        return result.returncode, output.strip()

    def __repr__(self) -> str:
        return "LocalOps(本地文件系统)"


class MockSSHOps:
    """模拟 SSH 远程实现：打印操作但不真正执行"""

    def __init__(self, host: str = "dev-server"):
        self.host = host

    def read_file(self, path: str) -> str:
        return f"[SSH {self.host}] 读取远程文件: {path}\n# 远程文件内容（模拟）"

    def write_file(self, path: str, content: str) -> None:
        print(f"    [SSH {self.host}] scp 写入: {path} ({len(content)} bytes)")

    def file_exists(self, path: str) -> bool:
        return True  # 模拟：假设文件存在

    def run_command(self, command: str, cwd: str) -> tuple[int, str]:
        return 0, f"[SSH {self.host}] ssh {self.host} 'cd {cwd} && {command}'\n# 远程执行成功（模拟）"

    def __repr__(self) -> str:
        return f"MockSSHOps(host={self.host})"


class MockDockerOps:
    """模拟 Docker 容器实现"""

    def __init__(self, container: str = "agent-sandbox"):
        self.container = container

    def read_file(self, path: str) -> str:
        return f"[Docker {self.container}] cat {path}\n# 容器内文件内容（模拟）"

    def write_file(self, path: str, content: str) -> None:
        print(f"    [Docker {self.container}] 写入容器: {path} ({len(content)} bytes)")

    def file_exists(self, path: str) -> bool:
        return True

    def run_command(self, command: str, cwd: str) -> tuple[int, str]:
        return 0, f"[Docker {self.container}] docker exec {self.container} bash -c 'cd {cwd} && {command}'\n# 容器执行成功（模拟）"

    def __repr__(self) -> str:
        return f"MockDockerOps(container={self.container})"


# ── Tool 工厂函数 ─────────────────────────────────────────────

def create_read_tool(cwd: str, operations: FileOperations | None = None):
    """创建 read 工具，注入 operations 实现

    对应原实现: createReadTool(cwd, options?)
    """
    ops = operations or LocalOps()

    def read_file(path: str) -> dict:
        abs_path = os.path.join(cwd, path) if not os.path.isabs(path) else path
        if not ops.file_exists(abs_path):
            return {"error": f"文件不存在: {path}"}
        content = ops.read_file(abs_path)
        lines = content.split("\n")
        return {
            "content": content,
            "lines": len(lines),
            "truncated": False,
        }

    return {
        "name": "read",
        "description": "读取文件内容",
        "execute": read_file,
        "operations": ops,
    }


def create_bash_tool(cwd: str, operations: ShellOperations | None = None):
    """创建 bash 工具，注入 operations 实现

    对应原实现: createBashTool(cwd, options?)
    """
    ops = operations or LocalOps()

    def run_command(command: str) -> dict:
        exit_code, output = ops.run_command(command, cwd)
        return {
            "exit_code": exit_code,
            "output": output,
        }

    return {
        "name": "bash",
        "description": "执行 shell 命令",
        "execute": run_command,
        "operations": ops,
    }
