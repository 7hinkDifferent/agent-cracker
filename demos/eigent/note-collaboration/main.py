"""
Eigent — 跨 Agent 笔记协作 Demo

复现 eigent 的 NoteTakingToolkit 机制：
1. NoteTakingToolkit：list_note(), read_note(), create_note(), append_note()
2. shared_files 约定：Agent 注册自己创建的文件
3. 多 Agent 在同一任务中共享笔记
4. 基于 dict 的简单存储（模拟文件系统）

原实现: backend/app/agent/toolkit/note_taking_toolkit.py
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


# ─── 笔记存储 ─────────────────────────────────────────────────

@dataclass
class NoteEntry:
    """单条笔记。"""
    filename: str
    content: str
    created_by: str          # 创建者 Agent 名称
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class NoteStorage:
    """任务级笔记存储 — 模拟 eigent 的文件系统存储。

    原实现中笔记存储在任务工作目录的 notes/ 子目录，
    通过 shared_files 注册让其他 Agent 可发现。
    """

    def __init__(self) -> None:
        self._notes: dict[str, NoteEntry] = {}

    def create(self, filename: str, content: str, author: str) -> NoteEntry:
        entry = NoteEntry(filename=filename, content=content, created_by=author)
        self._notes[filename] = entry
        return entry

    def read(self, filename: str) -> NoteEntry | None:
        return self._notes.get(filename)

    def append(self, filename: str, content: str, author: str) -> NoteEntry | None:
        entry = self._notes.get(filename)
        if entry:
            entry.content += f"\n{content}"
            entry.updated_at = time.time()
        return entry

    def list_all(self) -> list[str]:
        return list(self._notes.keys())

    def get_all(self) -> dict[str, NoteEntry]:
        return dict(self._notes)


# ─── shared_files 注册表 ─────────────────────────────────────

class SharedFiles:
    """跨 Agent 文件共享注册表。

    原实现: Agent 执行 Toolkit 后，将产出文件注册到 shared_files。
    其他 Agent 可通过 shared_files 发现并读取这些文件。

    设计要点:
    - 文件按 Agent 分组注册
    - 同一任务内所有 Agent 共享同一个注册表
    - NoteTakingToolkit 的 create_note 自动注册
    """

    def __init__(self) -> None:
        self._registry: dict[str, list[str]] = {}  # agent_name -> [filenames]

    def register(self, agent_name: str, filename: str) -> None:
        if agent_name not in self._registry:
            self._registry[agent_name] = []
        if filename not in self._registry[agent_name]:
            self._registry[agent_name].append(filename)

    def get_by_agent(self, agent_name: str) -> list[str]:
        return self._registry.get(agent_name, [])

    def get_all(self) -> dict[str, list[str]]:
        return dict(self._registry)

    def all_files(self) -> list[str]:
        return [f for files in self._registry.values() for f in files]


# ─── NoteTakingToolkit ──────────────────────────────────────

class NoteTakingToolkit:
    """笔记工具集 — 供 Agent 创建和共享笔记。

    原实现: backend/app/agent/toolkit/note_taking_toolkit.py

    方法:
    - list_note(): 列出所有笔记文件名
    - read_note(filename): 读取笔记内容
    - create_note(filename, content): 创建笔记 + 注册 shared_files
    - append_note(filename, content): 追加内容到已有笔记
    """

    def __init__(self, agent_name: str, storage: NoteStorage,
                 shared_files: SharedFiles) -> None:
        self.agent_name = agent_name
        self._storage = storage
        self._shared_files = shared_files

    def list_note(self) -> str:
        """列出所有可用笔记。"""
        notes = self._storage.list_all()
        if not notes:
            return "No notes found."
        return "Available notes:\n" + "\n".join(f"  - {n}" for n in notes)

    def read_note(self, filename: str) -> str:
        """读取笔记内容。"""
        entry = self._storage.read(filename)
        if not entry:
            return f"Note '{filename}' not found."
        return (f"=== {filename} (by {entry.created_by}) ===\n"
                f"{entry.content}")

    def create_note(self, filename: str, content: str) -> str:
        """创建笔记并注册到 shared_files。"""
        if self._storage.read(filename):
            return f"Note '{filename}' already exists. Use append_note() instead."

        self._storage.create(filename, content, self.agent_name)
        # 关键：注册到 shared_files，让其他 Agent 可发现
        self._shared_files.register(self.agent_name, filename)
        return f"Created note '{filename}' and registered to shared_files."

    def append_note(self, filename: str, content: str) -> str:
        """追加内容到已有笔记。"""
        entry = self._storage.append(filename, content, self.agent_name)
        if not entry:
            return f"Note '{filename}' not found. Use create_note() first."
        return f"Appended to '{filename}' (now {len(entry.content)} chars)."

    def get_tools(self) -> list[dict]:
        """返回工具定义（供 Agent 注册）。"""
        return [
            {"name": "list_note", "func": self.list_note},
            {"name": "read_note", "func": self.read_note},
            {"name": "create_note", "func": self.create_note},
            {"name": "append_note", "func": self.append_note},
        ]


# ─── Demo ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Eigent 跨 Agent 笔记协作 Demo")
    print("=" * 60)

    # 共享存储（同一任务的所有 Agent 共享）
    storage = NoteStorage()
    shared_files = SharedFiles()

    # 创建不同 Agent 的 NoteTakingToolkit 实例
    researcher = NoteTakingToolkit("browser_agent", storage, shared_files)
    developer = NoteTakingToolkit("developer_agent", storage, shared_files)
    documenter = NoteTakingToolkit("document_agent", storage, shared_files)

    # 1. Browser Agent 搜索后创建调研笔记
    print("\n--- Browser Agent: 创建调研笔记 ---\n")
    research_content = (
        "# API Research\n\n"
        "- REST vs GraphQL comparison\n"
        "- FastAPI recommended for Python\n"
        "- Rate limiting: token bucket algorithm"
    )
    result = researcher.create_note("research.md", research_content)
    print(f"  {result}")

    # 2. Developer Agent 读取调研笔记，创建实现笔记
    print("\n--- Developer Agent: 读取调研 + 创建实现笔记 ---\n")
    print(f"  list: {developer.list_note()}")
    print(f"  read: {developer.read_note('research.md')}")
    impl_content = (
        "# Implementation Plan\n\n"
        "1. Setup FastAPI project\n"
        "2. Add rate limiting middleware\n"
        "3. Write tests"
    )
    result = developer.create_note("implementation.md", impl_content)
    print(f"  {result}")

    # 3. Developer Agent 追加实现进度
    print("\n--- Developer Agent: 追加实现进度 ---\n")
    progress_content = (
        "\n## Progress\n"
        "- [x] FastAPI setup\n"
        "- [x] Rate limiting\n"
        "- [ ] Tests"
    )
    result = developer.append_note("implementation.md", progress_content)
    print(f"  {result}")

    # 4. Document Agent 汇总所有笔记
    print("\n--- Document Agent: 读取所有笔记并创建总结 ---\n")
    all_notes = storage.list_all()
    summaries = []
    for note_name in all_notes:
        content = documenter.read_note(note_name)
        summaries.append(f"From {note_name}: {len(content)} chars")
        print(f"  read: {note_name}")

    summary_content = (
        "# Task Summary\n\n"
        "Research completed. Implementation in progress.\n"
        "All findings documented in shared notes."
    )
    result = documenter.create_note("summary.md", summary_content)
    print(f"  {result}")

    # 5. 查看 shared_files 注册表
    print(f"\n{'─' * 40}")
    print("--- shared_files 注册表 ---\n")
    for agent, files in shared_files.get_all().items():
        print(f"  {agent}: {files}")

    # 6. 最终笔记状态
    print(f"\n{'─' * 40}")
    print("--- 最终笔记状态 ---\n")
    for name, entry in storage.get_all().items():
        lines = entry.content.count("\n") + 1
        print(f"  {name:25s} by {entry.created_by:20s} ({lines} lines, {len(entry.content)} chars)")

    # 7. 尝试重复创建
    print(f"\n{'─' * 40}")
    print("--- 边界情况 ---\n")
    print(f"  duplicate: {developer.create_note('research.md', 'overwrite attempt')}")
    print(f"  missing:   {developer.read_note('nonexistent.md')}")
    print(f"  append missing: {developer.append_note('nonexistent.md', 'data')}")

    print(f"\nDemo 完成")


if __name__ == "__main__":
    main()
