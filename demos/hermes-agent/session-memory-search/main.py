from __future__ import annotations

import tempfile
from pathlib import Path

from memory_store import SessionMemoryStore, seed_demo_data


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = SessionMemoryStore(root / "state.db", root / "memories")
        seed_demo_data(store)

        print("=" * 72)
        print("Hermes Session Memory Search Demo")
        print("=" * 72)
        print("\n[Memory snapshot injected into prompt]\n")
        print(store.memory_snapshot())

        print("\n[session_search query: digest]\n")
        print("解释: MEMORY.md / USER.md 提供稳定事实；session_search 负责召回低频历史细节。\n")
        for rank, hit in enumerate(store.search("digest"), start=1):
            print(f"- rank={rank} session={hit.session_id} relevance={hit.score:.2f}")
            print(f"  {hit.summary}")


if __name__ == "__main__":
    main()
