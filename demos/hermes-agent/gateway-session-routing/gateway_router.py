from __future__ import annotations

"""Gateway session routing demo core for Hermes."""

from dataclasses import dataclass, field


@dataclass
class SessionSource:
    platform: str
    chat_id: str
    chat_type: str = "dm"
    user_id: str | None = None
    thread_id: str | None = None


@dataclass
class MessageEvent:
    platform: str
    chat_id: str
    text: str
    chat_type: str = "dm"
    user_id: str | None = None
    thread_id: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_source(self) -> SessionSource:
        return SessionSource(
            platform=self.platform,
            chat_id=self.chat_id,
            chat_type=self.chat_type,
            user_id=self.user_id,
            thread_id=self.thread_id,
        )


def build_session_key(source: SessionSource, group_sessions_per_user: bool = True) -> str:
    if source.chat_type == "dm":
        if source.thread_id:
            return f"agent:main:{source.platform}:dm:{source.chat_id}:{source.thread_id}"
        return f"agent:main:{source.platform}:dm:{source.chat_id}"

    parts = ["agent", "main", source.platform, source.chat_type, source.chat_id]
    if group_sessions_per_user and source.user_id:
        parts.append(source.user_id)
    if source.thread_id:
        parts.append(source.thread_id)
    return ":".join(parts)


class SessionStore:
    def __init__(self):
        self.messages: dict[str, list[str]] = {}

    def append(self, session_key: str, text: str):
        self.messages.setdefault(session_key, []).append(text)


class GatewayRunner:
    """Normalize external events and route them into per-session histories."""

    def __init__(self, group_sessions_per_user: bool = True):
        self.group_sessions_per_user = group_sessions_per_user
        self.store = SessionStore()

    def handle_message(self, event: MessageEvent) -> str:
        source = event.to_source()
        session_key = build_session_key(source, self.group_sessions_per_user)
        self.store.append(session_key, event.text)
        return session_key
