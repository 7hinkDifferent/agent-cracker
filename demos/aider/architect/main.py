"""
Aider Architect Mode Demo — Two-Model Collaboration

Reproduces Aider's Architect mode:
  Phase 1: Architect model analyzes the request and produces a plan
  Phase 2: Editor model implements the plan using SEARCH/REPLACE blocks

This two-phase approach leverages different model strengths:
  - Architect: big-picture thinking, design decisions, change planning
  - Editor: precise code generation in SEARCH/REPLACE format

Requires: OPENAI_API_KEY or other LLM API key configured for litellm
Run: pip install -r requirements.txt && python main.py
"""

import os
import sys
import re
from dataclasses import dataclass

try:
    import litellm
except ImportError:
    print("Missing dependency. Run: pip install -r requirements.txt")
    sys.exit(1)


# ── Inline SEARCH/REPLACE parser (from Demo 2) ──────────────────────

@dataclass
class EditBlock:
    filename: str
    search_text: str
    replace_text: str


HEAD_PAT = re.compile(r"^<{5,9} SEARCH\s*$")
DIVIDER_PAT = re.compile(r"^={5,9}\s*$")
UPDATED_PAT = re.compile(r"^>{5,9} REPLACE\s*$")


def find_edit_blocks(text: str) -> list[EditBlock]:
    """Parse SEARCH/REPLACE blocks from LLM output."""
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if not HEAD_PAT.match(lines[i].strip()):
            i += 1
            continue
        filename = None
        for j in range(i - 1, max(i - 4, -1), -1):
            line = lines[j].strip().strip("`").strip("*").strip("#").strip()
            if line:
                filename = line
                break
        i += 1
        search_lines = []
        while i < len(lines) and not DIVIDER_PAT.match(lines[i].strip()):
            search_lines.append(lines[i])
            i += 1
        if i >= len(lines):
            break
        i += 1
        replace_lines = []
        while i < len(lines) and not UPDATED_PAT.match(lines[i].strip()):
            replace_lines.append(lines[i])
            i += 1
        if i >= len(lines):
            break
        i += 1
        blocks.append(EditBlock(
            filename=filename or "<unknown>",
            search_text="\n".join(search_lines),
            replace_text="\n".join(replace_lines),
        ))
    return blocks


def apply_edit(filepath: str, search_text: str, replace_text: str) -> bool:
    """Apply a SEARCH/REPLACE edit to a file."""
    with open(filepath, "r") as f:
        content = f.read()
    if search_text in content:
        with open(filepath, "w") as f:
            f.write(content.replace(search_text, replace_text, 1))
        return True
    return False


# ── Prompts (extracted from Aider's architect_prompts.py) ────────────

ARCHITECT_SYSTEM = """Act as an expert software architect.

Study the provided code and the user's request. Describe the changes needed to fulfill the request.

Guidelines:
- Describe WHICH files need to change and WHAT changes to make
- Explain the reasoning behind your design decisions
- Be specific: mention function names, class names, and line numbers
- Do NOT write actual code or SEARCH/REPLACE blocks
- Focus on the high-level plan and architecture
"""

EDITOR_SYSTEM = """Act as an expert coder. Apply the changes described by the architect.

Output your changes using SEARCH/REPLACE blocks:

path/to/file.py
<<<<<<< SEARCH
exact existing code to find
=======
replacement code
>>>>>>> REPLACE

Rules:
- SEARCH text must EXACTLY match the existing code (including whitespace)
- Only output blocks for code that needs to change
- Keep changes minimal — don't rewrite unchanged code
"""


# ── Core Architect Mode ─────────────────────────────────────────────

def architect_mode(
    user_request: str,
    files: dict[str, str],
    architect_model: str = "openai/gpt-4o-mini",
    editor_model: str = "openai/gpt-4o-mini",
) -> list[EditBlock]:
    """Two-phase architect mode: plan → implement.

    Phase 1: Architect model produces a natural-language plan
    Phase 2: Editor model converts the plan into SEARCH/REPLACE blocks

    Args:
        user_request: What the user wants to change
        files: Dict of {filename: content} for current project files
        architect_model: Model for architecture planning
        editor_model: Model for code implementation

    Returns list of parsed EditBlocks.
    """
    file_context = ""
    for name, content in files.items():
        file_context += f"\n--- {name} ---\n{content}\n"

    # Phase 1: Architecture
    print(f"\n  Phase 1: Architect ({architect_model})")
    print(f"  {'─' * 40}")

    architect_response = litellm.completion(
        model=architect_model,
        messages=[
            {"role": "system", "content": ARCHITECT_SYSTEM},
            {"role": "user", "content": f"Files:\n{file_context}\n\nRequest: {user_request}"},
        ],
        temperature=0,
    )
    plan = architect_response.choices[0].message.content
    print(f"  Plan ({len(plan)} chars):")
    # Print first few lines of the plan
    for line in plan.splitlines()[:10]:
        print(f"    {line}")
    if len(plan.splitlines()) > 10:
        print(f"    ... ({len(plan.splitlines()) - 10} more lines)")

    # Phase 2: Editor
    print(f"\n  Phase 2: Editor ({editor_model})")
    print(f"  {'─' * 40}")

    editor_response = litellm.completion(
        model=editor_model,
        messages=[
            {"role": "system", "content": EDITOR_SYSTEM},
            {"role": "user", "content": (
                f"Files:\n{file_context}\n\n"
                f"The architect has planned these changes:\n\n{plan}\n\n"
                f"Implement the architect's plan using SEARCH/REPLACE blocks."
            )},
        ],
        temperature=0,
    )
    editor_output = editor_response.choices[0].message.content
    print(f"  Editor output ({len(editor_output)} chars)")

    blocks = find_edit_blocks(editor_output)
    print(f"  Parsed {len(blocks)} edit blocks")

    return blocks


# ── Demo ─────────────────────────────────────────────────────────────

SAMPLE_APP = '''\
class TaskManager:
    def __init__(self):
        self.tasks = []

    def add_task(self, title):
        self.tasks.append({"title": title, "done": False})

    def complete_task(self, index):
        self.tasks[index]["done"] = True

    def list_tasks(self):
        for i, task in enumerate(self.tasks):
            status = "x" if task["done"] else " "
            print(f"[{status}] {i}. {task['title']}")


if __name__ == "__main__":
    tm = TaskManager()
    tm.add_task("Buy groceries")
    tm.add_task("Write report")
    tm.complete_task(0)
    tm.list_tasks()
'''


def main():
    print("=" * 60)
    print("Aider Architect Mode Demo")
    print("Two-model collaboration: Architect plans, Editor implements")
    print("=" * 60)

    # Check for API key
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n⚠  No API key found.")
        print("  Set OPENAI_API_KEY or ANTHROPIC_API_KEY to run with a real LLM.")
        print("  Example: export OPENAI_API_KEY=sk-...")
        print("\n  Running in demo mode with simulated output instead.\n")
        demo_without_llm()
        return

    architect_model = os.environ.get("DEMO_ARCHITECT_MODEL", "openai/gpt-4o-mini")
    editor_model = os.environ.get("DEMO_EDITOR_MODEL", "openai/gpt-4o-mini")
    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        architect_model = os.environ.get("DEMO_ARCHITECT_MODEL", "anthropic/claude-sonnet-4-6")
        editor_model = os.environ.get("DEMO_EDITOR_MODEL", "anthropic/claude-haiku-4-5-20251001")

    files = {"app.py": SAMPLE_APP}
    request = "Add due dates and priority levels to tasks. Add a method to sort tasks by priority."

    print(f"\nArchitect model: {architect_model}")
    print(f"Editor model:    {editor_model}")
    print(f"\nUser request: {request}")

    # Run architect mode
    try:
        blocks = architect_mode(request, files, architect_model, editor_model)
    except Exception as e:
        print(f"\n  LLM call failed: {e}")
        print("  Falling back to demo mode.\n")
        demo_without_llm()
        return

    # Apply edits
    print(f"\n{'=' * 60}")
    print("Applying edits...")
    print("=" * 60)

    # Work on in-memory copy
    current_files = dict(files)
    for block in blocks:
        if block.filename in current_files:
            content = current_files[block.filename]
            if block.search_text in content:
                current_files[block.filename] = content.replace(
                    block.search_text, block.replace_text, 1
                )
                print(f"  ✓ Applied edit to {block.filename}")
            else:
                print(f"  ✗ Could not match in {block.filename}")
        else:
            current_files[block.filename] = block.replace_text
            print(f"  + Created {block.filename}")

    # Show results
    print(f"\n{'=' * 60}")
    print("Final code:")
    print("=" * 60)
    for name, content in sorted(current_files.items()):
        print(f"\n── {name} ──")
        for lineno, line in enumerate(content.splitlines(), 1):
            print(f"  {lineno:3d} │ {line}")

    print("\n✓ Demo complete!")


def demo_without_llm():
    """Demonstrate the architect mode concept without an actual LLM."""
    print("── Simulated Architect Mode ──\n")
    print("The two-phase collaboration works as follows:\n")
    print("  Phase 1 — Architect (e.g., Claude Sonnet):")
    print("    Input:  User request + file contents")
    print("    Output: Natural language plan describing changes")
    print("    Example: 'Add a priority field to the Task class,")
    print("             modify add_task to accept priority parameter,")
    print("             add sort_by_priority method using sorted()'\n")
    print("  Phase 2 — Editor (e.g., Claude Haiku):")
    print("    Input:  Architect's plan + file contents")
    print("    Output: SEARCH/REPLACE blocks implementing the plan")
    print("    The editor follows the architect's design decisions\n")
    print("Benefits of this approach:")
    print("  - Architect can be a stronger model (better reasoning)")
    print("  - Editor can be a faster/cheaper model (mechanical task)")
    print("  - Separation of concerns: design vs implementation")
    print("  - Architect never needs to learn SEARCH/REPLACE format")
    print("\nSet an API key to see it work with real LLMs.")


if __name__ == "__main__":
    main()
