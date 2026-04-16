from __future__ import annotations

"""Session memory + SQLite FTS5 demo core for Hermes."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SessionHit:
    session_id: str
    score: float
    summary: str


class SessionMemoryStore:
    def __init__(self, db_path: Path, memory_dir: Path):
        self.db_path = db_path
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, parent_session_id TEXT, title TEXT)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, content TEXT)"
        )
        self.conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, content='messages', content_rowid='id')"
        )
        self.conn.execute(
            "CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN "
            "INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content); END"
        )
        self.conn.commit()

    def write_memory_file(self, name: str, lines: list[str]):
        (self.memory_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def memory_snapshot(self) -> str:
        parts = []
        for name in ("MEMORY.md", "USER.md"):
            path = self.memory_dir / name
            if path.exists():
                parts.append(f"## {name}\n{path.read_text(encoding='utf-8').strip()}")
        return "\n\n".join(parts)

    def add_session(self, session_id: str, title: str, parent_session_id: str | None = None):
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions(id, parent_session_id, title) VALUES (?, ?, ?)",
            (session_id, parent_session_id, title),
        )
        self.conn.commit()

    def add_message(self, session_id: str, role: str, content: str):
        self.conn.execute(
            "INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        self.conn.commit()

    def _session_messages(self, session_id: str) -> list[sqlite3.Row]:
        cursor = self.conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        return list(cursor.fetchall())

    def search(self, query: str, limit: int = 3) -> list[SessionHit]:
        cursor = self.conn.execute(
            "SELECT messages.session_id, bm25(messages_fts) AS score "
            "FROM messages_fts JOIN messages ON messages_fts.rowid = messages.id "
            "WHERE messages_fts MATCH ? ORDER BY score LIMIT 20",
            (query,),
        )
        seen: set[str] = set()
        hits: list[SessionHit] = []
        for row in cursor.fetchall():
            session_id = row[0]
            if session_id in seen:
                continue
            seen.add(session_id)
            raw_score = abs(float(row[1]))
            relevance = 1.0 / (1.0 + raw_score)
            hits.append(SessionHit(session_id, relevance, self.summarize_session(session_id, query)))
            if len(hits) >= limit:
                break
        return hits

    def summarize_session(self, session_id: str, query: str) -> str:
        rows = self._session_messages(session_id)
        matched = [r for r in rows if query.lower() in r["content"].lower()]
        interesting = matched[:2] or rows[:2]
        pieces = [f"{row['role']}: {row['content']}" for row in interesting]
        title = self.conn.execute("SELECT title FROM sessions WHERE id = ?", (session_id,)).fetchone()[0]
        return f"{title} -> " + " | ".join(pieces)


def seed_demo_data(store: SessionMemoryStore):
    store.write_memory_file("MEMORY.md", [
        "User prefers nightly Telegram digests.",
        "Keep summaries short unless debugging incidents.",
    ])
    store.write_memory_file("USER.md", [
        "Platform owner: zheng.",
        "Primary stack: Python + SQLite.",
    ])

    store.add_session("session-a", "Nightly digest setup")
    store.add_message("session-a", "user", "Please schedule a nightly digest for Telegram.")
    store.add_message("session-a", "assistant", "Configured a cron job that posts a digest every morning.")

    store.add_session("session-b", "SQLite memory debugging", parent_session_id="session-a")
    store.add_message("session-b", "user", "Why is session_search missing my old digest conversation?")
    store.add_message("session-b", "assistant", "The FTS query was too narrow; widening around 'digest' fixed the recall.")
