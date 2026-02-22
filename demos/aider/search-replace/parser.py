"""
SEARCH/REPLACE block parser.

Parses LLM output to extract edit blocks in Aider's SEARCH/REPLACE format.
Each block specifies a filename, text to search for, and replacement text.

Format:
    path/to/file.py
    <<<<<<< SEARCH
    original code here
    =======
    replacement code here
    >>>>>>> REPLACE
"""

import re
from dataclasses import dataclass


@dataclass
class EditBlock:
    filename: str
    search_text: str
    replace_text: str


# Core regex patterns (from Aider's editblock_coder.py)
HEAD_PAT = re.compile(r"^<{5,9} SEARCH\s*$")
DIVIDER_PAT = re.compile(r"^={5,9}\s*$")
UPDATED_PAT = re.compile(r"^>{5,9} REPLACE\s*$")


def find_filename(lines: list[str], head_idx: int) -> str | None:
    """Look backwards from HEAD line to find the filename.

    Aider checks the lines immediately before <<<<<<< SEARCH for a filename.
    It also handles fenced code block openers like ```python.
    """
    for i in range(head_idx - 1, max(head_idx - 4, -1), -1):
        line = lines[i].strip()
        # Skip empty lines and code fence openers
        if not line or line.startswith("```"):
            continue
        # Strip common markdown formatting
        line = line.strip("`").strip("*").strip("#").strip()
        if line:
            return line
    return None


def find_edit_blocks(text: str) -> list[EditBlock]:
    """Parse LLM output text to extract SEARCH/REPLACE edit blocks.

    Uses a simple state machine:
      SCANNING → found HEAD → SEARCH_BODY → found DIVIDER → REPLACE_BODY → found UPDATED → emit block

    Returns a list of EditBlock(filename, search_text, replace_text).
    """
    lines = text.splitlines()
    blocks = []

    i = 0
    while i < len(lines):
        # Look for HEAD pattern
        if not HEAD_PAT.match(lines[i].strip()):
            i += 1
            continue

        filename = find_filename(lines, i)
        i += 1  # skip HEAD line

        # Collect SEARCH body until DIVIDER
        search_lines = []
        while i < len(lines) and not DIVIDER_PAT.match(lines[i].strip()):
            search_lines.append(lines[i])
            i += 1

        if i >= len(lines):
            break
        i += 1  # skip DIVIDER

        # Collect REPLACE body until UPDATED
        replace_lines = []
        while i < len(lines) and not UPDATED_PAT.match(lines[i].strip()):
            replace_lines.append(lines[i])
            i += 1

        if i >= len(lines):
            break
        i += 1  # skip UPDATED

        blocks.append(EditBlock(
            filename=filename or "<unknown>",
            search_text="\n".join(search_lines),
            replace_text="\n".join(replace_lines),
        ))

    return blocks
