"""
Aider SEARCH/REPLACE Demo

Demonstrates the core edit format that Aider uses for LLM-driven code editing:
1. LLM outputs SEARCH/REPLACE blocks specifying exact changes
2. Parser extracts structured edit blocks from free-form LLM text
3. Replacer applies edits to files with fuzzy matching fallback

Run: python main.py
"""

import os
import tempfile
import shutil
from parser import find_edit_blocks
from replacer import apply_edit

# ── Sample LLM output containing SEARCH/REPLACE blocks ──────────────

SAMPLE_LLM_OUTPUT = '''
I'll help you improve the `Calculator` class. Here are the changes:

First, let's add input validation to the `divide` method:

calculator.py
<<<<<<< SEARCH
    def divide(self, a, b):
        return a / b
=======
    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
>>>>>>> REPLACE

Next, let's add a new `power` method:

calculator.py
<<<<<<< SEARCH
    def multiply(self, a, b):
        return a * b
=======
    def multiply(self, a, b):
        return a * b

    def power(self, base, exponent):
        """Raise base to the power of exponent."""
        return base ** exponent
>>>>>>> REPLACE

And update the main function to demonstrate the new features:

main.py
<<<<<<< SEARCH
def main():
    calc = Calculator()
    print(calc.add(2, 3))
=======
def main():
    calc = Calculator()
    print(f"2 + 3 = {calc.add(2, 3)}")
    print(f"2 ^ 10 = {calc.power(2, 10)}")

    try:
        calc.divide(1, 0)
    except ValueError as e:
        print(f"Caught: {e}")
>>>>>>> REPLACE
'''

# ── Sample source files ──────────────────────────────────────────────

SAMPLE_FILES = {
    "calculator.py": '''\
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    def multiply(self, a, b):
        return a * b

    def divide(self, a, b):
        return a / b
''',
    "main.py": '''\
from calculator import Calculator

def main():
    calc = Calculator()
    print(calc.add(2, 3))

if __name__ == "__main__":
    main()
''',
}


def demo_parsing():
    """Demo 1: Parse LLM output into structured edit blocks."""
    print("=" * 60)
    print("STEP 1: Parse LLM output into edit blocks")
    print("=" * 60)

    blocks = find_edit_blocks(SAMPLE_LLM_OUTPUT)
    print(f"\nFound {len(blocks)} edit blocks:\n")

    for i, block in enumerate(blocks, 1):
        print(f"  Block {i}:")
        print(f"    File:    {block.filename}")
        print(f"    Search:  {block.search_text[:50]}...")
        print(f"    Replace: {block.replace_text[:50]}...")
        print()

    return blocks


def demo_apply(blocks):
    """Demo 2: Apply edit blocks to actual files."""
    print("=" * 60)
    print("STEP 2: Apply edits to files")
    print("=" * 60)

    # Create temp directory with sample files
    tmpdir = tempfile.mkdtemp(prefix="aider-demo-")
    try:
        for name, content in SAMPLE_FILES.items():
            filepath = os.path.join(tmpdir, name)
            with open(filepath, "w") as f:
                f.write(content)

        print(f"\nCreated sample files in {tmpdir}\n")

        # Apply each edit
        for block in blocks:
            filepath = os.path.join(tmpdir, block.filename)
            apply_edit(filepath, block.search_text, block.replace_text)

        # Show results
        print("\n" + "=" * 60)
        print("STEP 3: Results after applying edits")
        print("=" * 60)

        for name in sorted(SAMPLE_FILES.keys()):
            filepath = os.path.join(tmpdir, name)
            with open(filepath, "r") as f:
                content = f.read()
            print(f"\n── {name} ──")
            for lineno, line in enumerate(content.splitlines(), 1):
                print(f"  {lineno:3d} │ {line}")

    finally:
        shutil.rmtree(tmpdir)


def demo_fuzzy_matching():
    """Demo 3: Show fuzzy matching in action."""
    print("\n" + "=" * 60)
    print("BONUS: Fuzzy whitespace matching")
    print("=" * 60)

    tmpdir = tempfile.mkdtemp(prefix="aider-fuzzy-")
    try:
        # File with tabs and trailing whitespace
        filepath = os.path.join(tmpdir, "messy.py")
        with open(filepath, "w") as f:
            f.write("def hello():   \n    print('hi')  \n    return True\n")

        # Search text with slightly different whitespace
        search = "def hello():\n    print('hi')\n    return True"
        replace = "def hello():\n    print('hello world')\n    return True"

        print(f"\n  File has trailing whitespace, search text does not.")
        print(f"  Exact match will fail, whitespace-normalized match will succeed.\n")

        apply_edit(filepath, search, replace)

        with open(filepath, "r") as f:
            print(f"\n  Result: {f.read().strip()}")

    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    print("Aider SEARCH/REPLACE Demo")
    print("Reproduces the core edit parsing and application mechanism\n")

    blocks = demo_parsing()
    demo_apply(blocks)
    demo_fuzzy_matching()

    print("\n✓ Demo complete!")
