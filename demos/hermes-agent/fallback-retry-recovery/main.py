from __future__ import annotations

from recovery import CredentialPool, ProviderAttempt, RecoveryEngine


VALID_TOOLS = {"read_file", "terminal", "memory"}


def main():
    engine = RecoveryEngine()
    pool = CredentialPool({"openai": ["key-a", "key-b"], "anthropic": ["key-c"]})

    print("=" * 72)
    print("Hermes Fallback / Retry / Recovery Demo")
    print("=" * 72)

    repaired_tool = engine.repair_tool_name("read-file", VALID_TOOLS)
    repaired_args = engine.repair_json_args("{'path': 'README.md',}")
    provider_result = engine.call_with_fallback(
        [
            ProviderAttempt("openai", fail=True),
            ProviderAttempt("openai", fail=True),
            ProviderAttempt("anthropic", scripted_response="final assistant turn"),
        ],
        pool,
    )

    print(f"tool repair: {repaired_tool}")
    print(f"json repair: {repaired_args}")
    print(f"provider fallback: {provider_result}")
    print(f"credential rotations: {pool.rotations}")


if __name__ == "__main__":
    main()
