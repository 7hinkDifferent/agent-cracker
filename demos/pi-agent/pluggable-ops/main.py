"""
Pi-Agent Pluggable Operations Demo

演示同一 tool 代码在 3 种执行环境中透明切换：
  1. LocalOps — 真实本地文件 I/O
  2. MockSSHOps — 模拟 SSH 远程执行
  3. MockDockerOps — 模拟 Docker 容器执行

核心思想：Tool 逻辑不变，只替换 Operations 实现

原实现: packages/coding-agent/src/core/tools/ (read.ts, bash.ts)
运行: python main.py
"""

import os
import tempfile
import shutil
from tools import (
    LocalOps, MockSSHOps, MockDockerOps,
    create_read_tool, create_bash_tool,
)


def run_tools_with_ops(label: str, cwd: str, file_ops, shell_ops):
    """用指定的 operations 运行 read 和 bash 工具"""
    print(f"\n{'─' * 50}")
    print(f"  环境: {label}")
    print(f"  FileOps: {file_ops}")
    print(f"  ShellOps: {shell_ops}")
    print(f"{'─' * 50}")

    # 创建工具（注入 operations）
    read_tool = create_read_tool(cwd, operations=file_ops)
    bash_tool = create_bash_tool(cwd, operations=shell_ops)

    # 1. 读取文件
    print(f"\n  [read] 读取 hello.py:")
    result = read_tool["execute"]("hello.py")
    if "error" in result:
        print(f"    错误: {result['error']}")
    else:
        print(f"    行数: {result['lines']}")
        for line in result["content"].split("\n")[:5]:
            print(f"    │ {line}")

    # 2. 执行命令
    print(f"\n  [bash] 执行 'echo Hello from agent':")
    result = bash_tool["execute"]("echo Hello from agent")
    print(f"    exit_code: {result['exit_code']}")
    for line in result["output"].split("\n"):
        print(f"    │ {line}")


def main():
    print("=" * 60)
    print("Pi-Agent Pluggable Operations Demo")
    print("同一 Tool 代码，3 种执行环境透明切换")
    print("=" * 60)

    # 创建临时工作目录，写入测试文件
    work_dir = tempfile.mkdtemp(prefix="pluggable-ops-")
    test_file = os.path.join(work_dir, "hello.py")
    with open(test_file, "w") as f:
        f.write('def greet(name):\n    return f"Hello, {name}!"\n\nprint(greet("Agent"))\n')

    try:
        # ── 环境 1：本地执行（真实 I/O）──────────────────────
        local = LocalOps()
        run_tools_with_ops("Local（本地文件系统）", work_dir, local, local)

        # ── 环境 2：SSH 远程执行（模拟）──────────────────────
        ssh = MockSSHOps(host="prod-server.example.com")
        run_tools_with_ops("SSH（远程服务器）", "/home/dev/project", ssh, ssh)

        # ── 环境 3：Docker 容器执行（模拟）───────────────────
        docker = MockDockerOps(container="python-sandbox-01")
        run_tools_with_ops("Docker（容器沙箱）", "/workspace", docker, docker)

        # ── 对比总结 ─────────────────────────────────────────

        print(f"\n{'=' * 60}")
        print("核心要点:")
        print("  1. Tool 工厂: create_read_tool(cwd, operations=None)")
        print("     → operations=None 时用 LocalOps（默认本地）")
        print("     → 传入 SSHOps/DockerOps 切换执行环境")
        print("  2. Operations Protocol: 定义抽象接口 (read_file, run_command)")
        print("     → Tool 只依赖接口，不依赖具体实现")
        print("  3. 零修改切换: Tool 逻辑完全不变，只替换底层操作")
        print(f"{'=' * 60}")

    finally:
        shutil.rmtree(work_dir)


if __name__ == "__main__":
    main()
