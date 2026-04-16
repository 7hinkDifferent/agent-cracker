from __future__ import annotations

from terminal_backends import TerminalManager


COMMANDS = [
    ("local", "printf 'workspace ok'"),
    ("docker", "pytest -q"),
    ("ssh", "git status --short"),
    ("modal", "python batch_job.py"),
    ("daytona", "npm test"),
    ("singularity", "python train.py --epochs 1"),
]


def main():
    manager = TerminalManager()

    print("=" * 72)
    print("Hermes Terminal Multi-Backend Demo")
    print("=" * 72)
    print("同一个 terminal 工具，根据配置切换不同执行后端。\n")

    for backend, command in COMMANDS:
        result = manager.run(backend, command)
        print(f"[{result.backend}] $ {result.command}")
        print(f"  {result.output}")


if __name__ == "__main__":
    main()
