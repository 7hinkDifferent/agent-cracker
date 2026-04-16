from __future__ import annotations

from approval_sandbox import ApprovalState, SandboxExecutor


def fake_backend(command: str) -> str:
    return f"executed safely -> {command}"


def main():
    approvals = ApprovalState()
    executor = SandboxExecutor(fake_backend, approvals)

    safe = "pytest -q"
    dangerous = "git reset --hard"

    print("=" * 72)
    print("Hermes Approval + Sandbox Demo")
    print("=" * 72)
    print(f"safe command: {executor.execute(safe)}")
    print(f"dangerous before approval: {executor.execute(dangerous)}")

    approvals.approve("git hard reset")
    print(f"dangerous after approval:  {executor.execute(dangerous)}")


if __name__ == "__main__":
    main()
