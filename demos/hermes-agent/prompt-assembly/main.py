from __future__ import annotations

from pathlib import Path

from prompt_builder_demo import PromptAssembler, PromptInputs


def main():
    cwd = Path(__file__).resolve().parent / "sample_context"
    assembler = PromptAssembler()
    inputs = PromptInputs(
        cwd=cwd,
        platform="telegram",
        system_message="Be concise, reliable, and prefer tools over guesses.",
        memory_lines=["User likes terse summaries.", "Primary repo path is ~/src/hermes-workbench."],
        user_lines=["Works on macOS.", "Prefers Telegram notifications for nightly reports."],
        skills_index=[
            "python-workflow — run uv, pytest, and lint in that order",
            "incident-triage — summarize the blast radius before proposing fixes",
        ],
        ephemeral_system_prompt="This message came from a thread reply; preserve conversation continuity.",
        session_id="telegram-thread-42",
        model="anthropic/claude-sonnet-4",
    )

    cached = assembler.build_cached_prompt(inputs)
    ephemeral = assembler.build_ephemeral_overlay(inputs)

    print("=" * 72)
    print("Hermes Prompt Assembly Demo")
    print("=" * 72)
    print("\n[Cached system prompt]\n")
    print(cached)
    print("\n[Ephemeral overlay]\n")
    print(ephemeral)


if __name__ == "__main__":
    main()
