from __future__ import annotations

from delegation import ChildTask, DelegationError, SubagentDelegator


def main():
    delegator = SubagentDelegator()
    tasks = [
        ChildTask("Inspect failing tests", context="repo root: ./app", depth=0, requested_toolsets=["terminal", "file"]),
        ChildTask("Summarize recent deploy logs", context="logs in ./ops", depth=0, requested_toolsets=["web", "send_message"]),
    ]

    print("=" * 72)
    print("Hermes Subagent Delegation Demo")
    print("=" * 72)
    print("\nParallel children:")
    for line in delegator.run_batch(tasks):
        print(f"- {line}")

    print("\nDepth guard:")
    try:
        delegator.run_child(ChildTask("Nested child should fail", depth=2))
    except DelegationError as exc:
        print(f"- blocked: {exc}")


if __name__ == "__main__":
    main()
