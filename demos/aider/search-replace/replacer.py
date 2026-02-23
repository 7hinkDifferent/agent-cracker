"""SEARCH/REPLACE block applier with fuzzy matching.

Applies edit blocks to files using two matching tiers:
  Tier 1: Exact string match
  Tier 2: Whitespace-normalized match (strip leading/trailing blank lines,
          normalize indentation)

This mirrors Aider's multi-tier matching strategy from editblock_coder.py,
simplified to the two most important tiers.
"""


def _strip_blank_lines(text: str) -> str:
    """Remove leading and trailing blank lines."""
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace: strip each line's trailing whitespace and remove
    leading/trailing blank lines."""
    lines = [line.rstrip() for line in text.splitlines()]
    result = "\n".join(lines)
    return _strip_blank_lines(result)


def _find_with_normalized_whitespace(content: str, search: str) -> tuple[int, int] | None:
    """Find search text in content using whitespace-normalized comparison.

    Returns (start, end) character positions in the ORIGINAL content,
    or None if not found.
    """
    search_norm = _normalize_whitespace(search)
    search_lines = search_norm.splitlines()
    content_lines = content.splitlines()

    if not search_lines:
        return None

    num_search = len(search_lines)
    for i in range(len(content_lines) - num_search + 1):
        candidate = content_lines[i:i + num_search]
        candidate_stripped = [line.rstrip() for line in candidate]
        # Also strip leading/trailing blank lines for comparison
        if "\n".join(candidate_stripped) == search_norm or \
           _normalize_whitespace("\n".join(candidate)) == search_norm:
            # Calculate character positions
            start = sum(len(line) + 1 for line in content_lines[:i])
            end = sum(len(line) + 1 for line in content_lines[:i + num_search])
            # Adjust: don't include the trailing newline of the last matched line
            if end > 0 and end <= len(content) + 1:
                end = min(end, len(content))
            return start, end

    return None


def _reindent(replace_text: str, search_text: str, matched_text: str) -> str:
    """Adjust replacement text indentation to match the original matched text.

    If the original search_text had different indentation from what was actually
    matched, shift the replacement accordingly.
    """
    search_lines = search_text.splitlines()
    matched_lines = matched_text.splitlines()

    if not search_lines or not matched_lines:
        return replace_text

    # Find indentation difference from first non-empty line
    search_indent = 0
    matched_indent = 0
    for line in search_lines:
        if line.strip():
            search_indent = len(line) - len(line.lstrip())
            break
    for line in matched_lines:
        if line.strip():
            matched_indent = len(line) - len(line.lstrip())
            break

    indent_diff = matched_indent - search_indent
    if indent_diff == 0:
        return replace_text

    result_lines = []
    for line in replace_text.splitlines():
        if not line.strip():
            result_lines.append(line)
        elif indent_diff > 0:
            result_lines.append(" " * indent_diff + line)
        else:
            # Remove indentation (but don't go negative)
            remove = min(-indent_diff, len(line) - len(line.lstrip()))
            result_lines.append(line[remove:])
    return "\n".join(result_lines)


def apply_edit(filepath: str, search_text: str, replace_text: str) -> bool:
    """Apply a single SEARCH/REPLACE edit to a file.

    Matching strategy:
      Tier 1: Exact match — search_text appears literally in the file
      Tier 2: Whitespace-normalized — ignore leading/trailing blanks, trailing whitespace

    Returns True if the edit was applied, False otherwise.
    """
    with open(filepath, "r") as f:
        content = f.read()

    # Tier 1: Exact match
    if search_text in content:
        new_content = content.replace(search_text, replace_text, 1)
        with open(filepath, "w") as f:
            f.write(new_content)
        print(f"  [Tier 1: exact match] Applied edit to {filepath}")
        return True

    # Tier 2: Whitespace-normalized match
    pos = _find_with_normalized_whitespace(content, search_text)
    if pos:
        start, end = pos
        matched_text = content[start:end]
        adjusted_replace = _reindent(replace_text, search_text, matched_text)
        new_content = content[:start] + adjusted_replace + content[end:]
        with open(filepath, "w") as f:
            f.write(new_content)
        print(f"  [Tier 2: whitespace-normalized] Applied edit to {filepath}")
        return True

    print(f"  [FAILED] Could not find match in {filepath}")
    return False
