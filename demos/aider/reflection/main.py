"""
Aider Reflection Loop Demo

Reproduces Aider's core reflection mechanism:
  edit → lint/test → if errors, feed them back to LLM → retry (max 3 times)

This is the inner loop from Aider's BaseCoder.run_one():
  1. Call LLM to generate code edits
  2. Parse and apply SEARCH/REPLACE blocks
  3. Run lint (py_compile) and tests (pytest)
  4. If errors found, compose an error message and send it back to LLM
  5. Repeat until success or max_reflections reached

Requires: OPENAI_API_KEY or other LLM API key configured for litellm
Run: pip install -r requirements.txt && python main.py
"""

import os
import sys
import re
import subprocess
import tempfile
import shutil
from dataclasses import dataclass

try:
    import litellm
except ImportError:
    print("Missing dependency. Run: pip install -r requirements.txt")
    sys.exit(1)


# ── Inline SEARCH/REPLACE parser (simplified from Demo 2) ───────────

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

        # Find filename above HEAD
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
    """Apply a SEARCH/REPLACE edit to a file (exact match only for simplicity)."""
    with open(filepath, "r") as f:
        content = f.read()
    if search_text in content:
        with open(filepath, "w") as f:
            f.write(content.replace(search_text, replace_text, 1))
        return True
    return False


# ── LLM Integration ─────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Python programmer. When asked to modify code, output changes using SEARCH/REPLACE blocks.

Format:
filename.py
<<<<<<< SEARCH
original code
=======
modified code
>>>>>>> REPLACE

Rules:
- SEARCH must exactly match existing code
- Only output the blocks that need to change
- Keep changes minimal and focused
"""


def call_llm(message: str, files: dict[str, str], model: str = "openai/gpt-4o-mini") -> str:
    """Call LLM with the current file contents and a message."""
    file_context = ""
    for name, content in files.items():
        file_context += f"\n--- {name} ---\n{content}\n"

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Files:\n{file_context}\n\nRequest: {message}"},
        ],
        temperature=0,
    )
    return response.choices[0].message.content


# ── Lint & Test ──────────────────────────────────────────────────────

def run_lint(filepath: str) -> str | None:
    """Run py_compile on a file. Returns error message or None."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", filepath],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return result.stderr.strip()
    return None


def run_tests(test_dir: str) -> str | None:
    """Run pytest in a directory. Returns error output or None."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_dir, "-x", "--tb=short", "-q"],
        capture_output=True, text=True,
        cwd=test_dir,
    )
    if result.returncode != 0:
        output = result.stdout + result.stderr
        return output.strip()
    return None


# ── Core Reflection Loop ────────────────────────────────────────────

def reflection_loop(
    user_request: str,
    work_dir: str,
    filenames: list[str],
    model: str = "openai/gpt-4o-mini",
    max_reflections: int = 3,
) -> bool:
    """Aider's reflection loop: edit → check → fix → repeat.

    Args:
        user_request: What the user wants to change
        work_dir: Directory containing the files
        filenames: List of filenames to edit
        model: LLM model to use via litellm
        max_reflections: Maximum number of fix attempts after initial edit

    Returns True if the code compiles and tests pass, False otherwise.
    """
    message = user_request

    for attempt in range(max_reflections + 1):
        phase = "Initial edit" if attempt == 0 else f"Reflection #{attempt}"
        print(f"\n{'─' * 50}")
        print(f"  {phase}")
        print(f"{'─' * 50}")

        # Read current file contents
        files = {}
        for name in filenames:
            filepath = os.path.join(work_dir, name)
            with open(filepath, "r") as f:
                files[name] = f.read()

        # Step 1: Call LLM
        print(f"  Calling LLM ({model})...")
        response = call_llm(message, files, model)
        print(f"  LLM response ({len(response)} chars)")

        # Step 2: Parse and apply edits
        blocks = find_edit_blocks(response)
        print(f"  Found {len(blocks)} edit blocks")
        for block in blocks:
            filepath = os.path.join(work_dir, block.filename)
            if os.path.exists(filepath):
                success = apply_edit(filepath, block.search_text, block.replace_text)
                status = "applied" if success else "FAILED to match"
                print(f"    {block.filename}: {status}")
            else:
                # New file
                with open(filepath, "w") as f:
                    f.write(block.replace_text)
                print(f"    {block.filename}: created")

        # Step 3: Run lint
        errors = []
        for name in filenames:
            filepath = os.path.join(work_dir, name)
            lint_error = run_lint(filepath)
            if lint_error:
                errors.append(f"Lint error in {name}:\n{lint_error}")
                print(f"  ✗ Lint failed: {name}")

        # Step 4: Run tests (only if lint passes)
        if not errors:
            test_error = run_tests(work_dir)
            if test_error:
                errors.append(f"Test failures:\n{test_error}")
                print(f"  ✗ Tests failed")

        # Step 5: Check results
        if not errors:
            print(f"  ✓ All checks passed!")
            return True

        if attempt < max_reflections:
            # Compose reflection message
            error_text = "\n\n".join(errors)
            message = f"The code has errors. Fix them:\n\n{error_text}"
            print(f"  → Reflecting on errors, will retry...")
        else:
            print(f"  ✗ Max reflections reached, giving up.")

    return False


# ── Demo ─────────────────────────────────────────────────────────────

SAMPLE_CODE = '''\
def fibonacci(n):
    """Return the nth Fibonacci number."""
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    else:
        return fibonacci(n-1) + fibonacci(n-2)


def is_prime(n):
    """Check if n is prime."""
    if n < 2:
        return False
    for i in range(2, n):
        if n % i == 0:
            return False
    return True
'''

SAMPLE_TEST = '''\
from sample import fibonacci, is_prime

def test_fibonacci():
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(10) == 55

def test_is_prime():
    assert is_prime(2) == True
    assert is_prime(17) == True
    assert is_prime(4) == False
    assert is_prime(1) == False
'''


def main():
    print("=" * 60)
    print("Aider Reflection Loop Demo")
    print("Reproduces the edit → lint → test → reflect → retry loop")
    print("=" * 60)

    # Check for API key
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n⚠  No API key found.")
        print("  Set OPENAI_API_KEY or ANTHROPIC_API_KEY to run with a real LLM.")
        print("  Example: export OPENAI_API_KEY=sk-...")
        print("\n  Running in demo mode with simulated output instead.\n")
        demo_without_llm()
        return

    model = os.environ.get("DEMO_MODEL", "openai/gpt-4o-mini")
    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("DEMO_MODEL", "anthropic/claude-haiku-4-5-20251001")

    # Create temp workspace
    work_dir = tempfile.mkdtemp(prefix="aider-reflect-")
    try:
        # Write sample files
        with open(os.path.join(work_dir, "sample.py"), "w") as f:
            f.write(SAMPLE_CODE)
        with open(os.path.join(work_dir, "test_sample.py"), "w") as f:
            f.write(SAMPLE_TEST)

        print(f"\nWorkspace: {work_dir}")
        print(f"Model: {model}")

        # Run reflection loop
        request = "Optimize the fibonacci function to use memoization, and optimize is_prime to only check up to sqrt(n)."
        print(f"\nUser request: {request}")

        try:
            success = reflection_loop(
                user_request=request,
                work_dir=work_dir,
                filenames=["sample.py"],
                model=model,
                max_reflections=3,
            )
        except Exception as e:
            print(f"\n  LLM call failed: {e}")
            print("  Falling back to demo mode.\n")
            demo_without_llm()
            return

        # Show final result
        print(f"\n{'=' * 60}")
        print("Final code:")
        print("=" * 60)
        with open(os.path.join(work_dir, "sample.py"), "r") as f:
            for lineno, line in enumerate(f.readlines(), 1):
                print(f"  {lineno:3d} │ {line}", end="")

        print(f"\n\nResult: {'SUCCESS' if success else 'FAILED after max reflections'}")

    finally:
        shutil.rmtree(work_dir)


def demo_without_llm():
    """Demonstrate the reflection loop concept without an actual LLM call."""
    print("── Simulated Reflection Loop ──\n")
    print("The reflection loop works as follows:\n")
    print("  1. User: 'Add input validation to fibonacci'")
    print("  2. LLM generates SEARCH/REPLACE blocks")
    print("  3. Apply edits to sample.py")
    print("  4. Run py_compile → syntax check")
    print("  5. Run pytest → functional check")
    print("  6. If errors found:")
    print("     → Send errors back to LLM: 'Fix these errors: ...'")
    print("     → LLM generates new SEARCH/REPLACE blocks")
    print("     → Apply and check again (up to 3 retries)")
    print("  7. Success or give up after max retries\n")
    print("This is Aider's 'auto-fix' mechanism from BaseCoder.run_one().")
    print("Set an API key to see it work with a real LLM.")


if __name__ == "__main__":
    main()
