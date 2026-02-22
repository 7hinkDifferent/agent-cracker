"""
Aider RepoMap Demo — Repository Syntax Map

Reproduces Aider's core repo-map mechanism:
1. tree-sitter parses all .py files → extracts Tags (definitions & references)
2. Builds a dependency graph: file A references identifier defined in file B
3. Runs PageRank to rank files/identifiers by importance
4. Outputs the top-ranked definitions within a token budget

Run: pip install -r requirements.txt && python repomap.py
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser
    import networkx as nx
except ImportError:
    print("Missing dependencies. Run: pip install -r requirements.txt")
    sys.exit(1)


@dataclass
class Tag:
    """A code symbol extracted by tree-sitter."""
    file: str
    name: str
    kind: str  # "def" or "ref"
    line: int


# Node types that represent definitions in Python AST
DEF_PARENT_TYPES = {"function_definition", "class_definition"}
ASSIGNMENT_TYPE = "assignment"


def get_parser() -> Parser:
    """Create a tree-sitter parser for Python."""
    PY_LANGUAGE = Language(tspython.language())
    parser = Parser(PY_LANGUAGE)
    return parser


def _walk_tree(node):
    """Yield all nodes in the tree via depth-first traversal."""
    yield node
    for child in node.children:
        yield from _walk_tree(child)


def extract_tags(filepath: str, parser: Parser) -> list[Tag]:
    """Extract definition and reference tags from a Python file using tree-sitter.

    Uses AST walking instead of query API for compatibility across tree-sitter versions.
    Definition heuristic: an identifier node whose parent is a function_definition,
    class_definition (as the 'name' field), or assignment (as the left side).
    Everything else is a reference.
    """
    with open(filepath, "rb") as f:
        source = f.read()

    tree = parser.parse(source)

    tags = []
    defined_positions: set[tuple[str, int]] = set()

    # Pass 1: Find definitions
    for node in _walk_tree(tree.root_node):
        if node.type != "identifier":
            continue

        parent = node.parent
        if parent is None:
            continue

        is_def = False

        # function/class name
        if parent.type in DEF_PARENT_TYPES:
            name_node = parent.child_by_field_name("name")
            if name_node is not None and name_node.id == node.id:
                is_def = True

        # assignment target (left side)
        if parent.type == ASSIGNMENT_TYPE:
            left_node = parent.child_by_field_name("left")
            if left_node is not None and left_node.id == node.id:
                is_def = True

        if is_def:
            name = node.text.decode("utf-8")
            line = node.start_point[0] + 1
            tags.append(Tag(file=filepath, name=name, kind="def", line=line))
            defined_positions.add((name, line))

    # Pass 2: Find references (all identifiers not at definition sites)
    for node in _walk_tree(tree.root_node):
        if node.type != "identifier":
            continue
        name = node.text.decode("utf-8")
        line = node.start_point[0] + 1
        if (name, line) not in defined_positions:
            tags.append(Tag(file=filepath, name=name, kind="ref", line=line))

    return tags


def build_repo_map(directory: str, chat_files: list[str] | None = None, max_tokens: int = 1024) -> str:
    """Build a repository map showing the most important definitions.

    This is the core algorithm from Aider's repomap.py:
    1. Parse all .py files with tree-sitter → extract Tags
    2. Build defines{ident→files} and references{ident→files}
    3. Build a networkx MultiDiGraph with edges: ref_file → def_file (weighted)
    4. Run PageRank to rank files
    5. Output top-ranked definitions until token budget is exhausted

    Args:
        directory: Root directory to scan
        chat_files: Files currently in the chat context (get 50x reference weight)
        max_tokens: Approximate token budget (estimated as chars / 4)
    """
    chat_files_abs = set(os.path.abspath(f) for f in (chat_files or []))
    parser = get_parser()

    # Step 1: Collect all .py files and extract tags
    print(f"Scanning {directory} for Python files...")
    all_tags_flat: list[Tag] = []
    py_files = sorted(Path(directory).rglob("*.py"))

    for py_file in py_files:
        filepath = str(py_file)
        try:
            tags = extract_tags(filepath, parser)
            all_tags_flat.extend(tags)
        except Exception as e:
            print(f"  Warning: could not parse {filepath}: {e}")

    print(f"  Found {len(py_files)} files, {len(all_tags_flat)} tags")

    # Step 2: Build defines and references mappings
    defines: dict[str, set[str]] = {}  # ident → set of files that define it
    references: dict[str, set[str]] = {}  # ident → set of files that reference it

    for tag in all_tags_flat:
        if tag.kind == "def":
            defines.setdefault(tag.name, set()).add(tag.file)
        else:
            references.setdefault(tag.name, set()).add(tag.file)

    # Step 3: Build dependency graph
    print("Building dependency graph...")
    G = nx.MultiDiGraph()

    for ident, ref_files in references.items():
        def_files = defines.get(ident, set())
        if not def_files:
            continue
        for ref_file in ref_files:
            for def_file in def_files:
                if ref_file == def_file:
                    continue
                # Chat files get 50x weight — Aider's key insight for relevance
                weight = 50.0 if os.path.abspath(ref_file) in chat_files_abs else 1.0
                G.add_edge(ref_file, def_file, weight=weight, ident=ident)

    if not G.nodes():
        return "(No cross-file references found)"

    print(f"  Graph: {len(G.nodes())} nodes, {len(G.edges())} edges")

    # Step 4: PageRank
    print("Running PageRank...")
    try:
        ranked = nx.pagerank(G, weight="weight")
    except nx.NetworkXException:
        ranked = {node: 1.0 / len(G.nodes()) for node in G.nodes()}

    ranked_files = sorted(ranked.items(), key=lambda x: -x[1])

    # Step 5: Build output within token budget
    # Collect definitions per file, sorted by line number
    file_defs: dict[str, list[Tag]] = {}
    for tag in all_tags_flat:
        if tag.kind == "def":
            file_defs.setdefault(tag.file, []).append(tag)
    for defs in file_defs.values():
        defs.sort(key=lambda t: t.line)

    output_lines = []
    char_budget = max_tokens * 4  # rough estimate: 1 token ≈ 4 chars
    chars_used = 0

    for filepath, score in ranked_files:
        defs = file_defs.get(filepath, [])
        if not defs:
            continue

        # Relativize path for display
        try:
            rel_path = os.path.relpath(filepath, directory)
        except ValueError:
            rel_path = filepath

        file_header = f"\n{rel_path}:"
        file_lines = [file_header]
        for tag in defs:
            file_lines.append(f"  {tag.line:4d} │ {tag.name}")

        section = "\n".join(file_lines)
        section_chars = len(section)

        if chars_used + section_chars > char_budget:
            if output_lines:
                output_lines.append(f"\n... (truncated, {max_tokens} token budget)")
                break

        output_lines.append(section)
        chars_used += section_chars

    return "\n".join(output_lines)


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Use sample_project/ as the default target
    demo_dir = os.path.dirname(os.path.abspath(__file__))
    sample_dir = os.path.join(demo_dir, "sample_project")

    if not os.path.isdir(sample_dir):
        print(f"Error: sample_project/ not found at {sample_dir}")
        sys.exit(1)

    print("=" * 60)
    print("Aider RepoMap Demo")
    print("Reproduces the repository syntax map mechanism")
    print("=" * 60)

    # Demo 1: Basic repo map
    print("\n── Demo 1: Basic repo map ──")
    repo_map = build_repo_map(sample_dir, max_tokens=2048)
    print("\nRepository Map:")
    print(repo_map)

    # Demo 2: With chat files (simulating user editing app.py)
    print("\n\n── Demo 2: With chat context (app.py in chat) ──")
    chat_file = os.path.join(sample_dir, "app.py")
    repo_map_chat = build_repo_map(sample_dir, chat_files=[chat_file], max_tokens=2048)
    print("\nRepository Map (app.py in chat, references weighted 50x):")
    print(repo_map_chat)

    print("\n✓ Demo complete!")
