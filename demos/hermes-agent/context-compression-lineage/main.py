from __future__ import annotations

from compression import ContextCompressor, LineageStore, SessionNode


MESSAGES = [
    "user: investigate why nightly digests stop after compaction",
    "assistant: I will inspect session_search and memory injection",
    "tool: read_file -> session_search_tool.py excerpt about FTS5 recall and summarization",
    "tool: read_file -> prompt_builder.py excerpt about MEMORY.md and USER.md",
    "assistant: I found that older middle messages can be summarized while keeping head and tail intact",
]


def main():
    compressor = ContextCompressor(threshold_chars=150)
    store = LineageStore()
    root = SessionNode("session-root", None, "original session before compaction")
    store.add(root)

    print("=" * 72)
    print("Hermes Context Compression Lineage Demo")
    print("=" * 72)

    if compressor.should_compress(MESSAGES):
        compacted, child = compressor.compress("session-root", MESSAGES)
        store.add(child)
        print("Compacted messages:")
        for message in compacted:
            print(f"- {message}")
        print("\nLineage:")
        for node in store.lineage(child.session_id):
            print(f"- {node.session_id} <- {node.parent_session_id} :: {node.summary}")
    else:
        print("No compression needed")


if __name__ == "__main__":
    main()
