#!/usr/bin/env python3
"""
Context Window Management Demo

Reproduces Gemini CLI's context window management strategy for the 1M token limit.
Implements JIT file loading, token estimation, overflow detection, and history compression.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Set
import hashlib


class OverflowStrategy(Enum):
    """Strategy for handling context overflow."""
    STOP = "stop"          # Stop immediately
    COMPRESS = "compress"  # Compress history
    PRUNE = "prune"        # Remove oldest events


@dataclass
class TokenMetrics:
    """Token usage metrics."""
    estimated_tokens: int = 0
    max_tokens: int = 10000  # Simulated smaller window for demo
    buffer_tokens: int = 500  # Reserve for response

    @property
    def available_tokens(self) -> int:
        """Available tokens for context."""
        return self.max_tokens - self.buffer_tokens - self.estimated_tokens

    @property
    def usage_ratio(self) -> float:
        """Usage as percentage of max."""
        return self.estimated_tokens / (self.max_tokens - self.buffer_tokens)

    def will_overflow(self, additional_tokens: int) -> bool:
        """Check if adding tokens would overflow."""
        return (self.estimated_tokens + additional_tokens) > (self.max_tokens - self.buffer_tokens)


class TokenEstimator:
    """
    Estimate token counts for text and data structures.
    Using simple heuristic (4 chars ≈ 1 token) instead of calling API.
    """

    @staticmethod
    def estimate_text(text: str) -> int:
        """Estimate tokens in text (rough heuristic)."""
        return max(1, len(text) // 4)

    @staticmethod
    def estimate_file(file_path: str, content: str) -> int:
        """Estimate tokens for file with metadata."""
        # File header + content
        header = f"FILE: {file_path}\n```\n"
        footer = "\n```\n"
        return TokenEstimator.estimate_text(header + content + footer)

    @staticmethod
    def estimate_event(event: Dict) -> int:
        """Estimate tokens for an event."""
        event_str = str(event)
        return TokenEstimator.estimate_text(event_str)


class FileContext:
    """Represents a file loaded into context."""

    def __init__(self, path: str, content: str):
        self.path = path
        self.content = content
        self.tokens = TokenEstimator.estimate_file(path, content)
        self.loaded_at_event: int = -1
        self.last_accessed_event: int = -1

    def __repr__(self) -> str:
        return f"FileContext({self.path}, {self.tokens} tokens)"


@dataclass
class EventEntry:
    """Represents an event in the context history."""
    event_id: int
    event_type: str  # "user_query", "llm_response", "tool_call", etc.
    content: str
    tokens: int = 0

    def __post_init__(self):
        if not self.tokens:
            self.tokens = TokenEstimator.estimate_event({"type": self.event_type, "content": self.content})


class ContextWindowManager:
    """
    Manages context window with token budgeting, JIT file loading,
    and overflow detection.
    """

    def __init__(self, max_tokens: int = 10000):
        self.metrics = TokenMetrics(max_tokens=max_tokens)
        self.loaded_files: Dict[str, FileContext] = {}
        self.events: List[EventEntry] = []
        self.event_counter = 0
        self.system_prompt_tokens = TokenEstimator.estimate_text(
            "You are a helpful AI assistant. You have access to tools for reading files, "
            "executing shell commands, and more."
        )

        # Initialize with system prompt
        self.metrics.estimated_tokens = self.system_prompt_tokens

    def add_event(self, event_type: str, content: str) -> int:
        """Add event to history and track tokens."""
        tokens = TokenEstimator.estimate_text(content)

        if self.metrics.will_overflow(tokens):
            return -1  # Would overflow

        event_id = self.event_counter
        self.event_counter += 1

        event = EventEntry(
            event_id=event_id,
            event_type=event_type,
            content=content,
            tokens=tokens,
        )
        self.events.append(event)
        self.metrics.estimated_tokens += tokens

        return event_id

    def load_file(self, file_path: str, content: str) -> Optional[FileContext]:
        """
        Load file into context (JIT loading).
        Returns FileContext if successful, None if would overflow.
        """
        if file_path in self.loaded_files:
            file_ctx = self.loaded_files[file_path]
            file_ctx.last_accessed_event = self.event_counter
            return file_ctx

        file_ctx = FileContext(file_path, content)

        if self.metrics.will_overflow(file_ctx.tokens):
            return None  # Cannot load

        self.loaded_files[file_path] = file_ctx
        self.metrics.estimated_tokens += file_ctx.tokens
        file_ctx.loaded_at_event = self.event_counter

        return file_ctx

    def unload_file(self, file_path: str):
        """Remove file from context to free tokens."""
        if file_path in self.loaded_files:
            file_ctx = self.loaded_files[file_path]
            self.metrics.estimated_tokens -= file_ctx.tokens
            del self.loaded_files[file_path]

    def compress_history(self, keep_recent_events: int = 10) -> Dict:
        """
        Compress history by summarizing old events.
        Returns compression report.
        """
        if len(self.events) <= keep_recent_events:
            return {"compressed": False, "reason": "History too short"}

        # Keep only recent events
        old_events = self.events[:-keep_recent_events]
        new_events = self.events[-keep_recent_events:]

        # Calculate tokens saved
        old_tokens = sum(e.tokens for e in old_events)
        summary_tokens = TokenEstimator.estimate_text(
            f"[{len(old_events)} previous interactions summarized]"
        )

        # Create summary event
        summary_event = EventEntry(
            event_id=self.event_counter,
            event_type="history_summary",
            content=f"Previous {len(old_events)} interactions summarized",
            tokens=summary_tokens,
        )

        self.events = [summary_event] + new_events
        tokens_freed = old_tokens - summary_tokens
        self.metrics.estimated_tokens -= tokens_freed

        return {
            "compressed": True,
            "events_removed": len(old_events),
            "tokens_freed": tokens_freed,
            "new_history_size": len(self.events),
        }

    def prune_old_files(self, keep_count: int = 3) -> Dict:
        """
        Remove least recently accessed files to free tokens.
        """
        if len(self.loaded_files) <= keep_count:
            return {"pruned": False, "reason": "File count below threshold"}

        # Sort by last access
        sorted_files = sorted(
            self.loaded_files.items(),
            key=lambda x: x[1].last_accessed_event,
        )

        files_to_remove = sorted_files[:-keep_count]
        tokens_freed = 0

        for path, file_ctx in files_to_remove:
            tokens_freed += file_ctx.tokens
            del self.loaded_files[path]

        self.metrics.estimated_tokens -= tokens_freed

        return {
            "pruned": True,
            "files_removed": len(files_to_remove),
            "tokens_freed": tokens_freed,
            "remaining_files": len(self.loaded_files),
        }

    def get_status(self) -> Dict:
        """Get detailed context window status."""
        return {
            "tokens_used": self.metrics.estimated_tokens,
            "tokens_available": self.metrics.available_tokens,
            "usage_ratio": f"{self.metrics.usage_ratio:.1%}",
            "will_overflow": self.metrics.usage_ratio >= 0.95,
            "event_count": len(self.events),
            "loaded_files": list(self.loaded_files.keys()),
            "loaded_files_count": len(self.loaded_files),
        }


class JITContextLoader:
    """
    Just-In-Time context loader that dynamically loads files based on queries.
    """

    def __init__(self, context_manager: ContextWindowManager):
        self.context_manager = context_manager
        # Simulated file database
        self.available_files = {
            "main.py": "def main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()",
            "utils.py": "def helper():\n    return 'helper result'\n\ndef another():\n    pass",
            "config.json": '{"api_key": "***", "timeout": 30, "retries": 3}',
            "README.md": "# Project README\n\nThis is a sample project.\n\n## Features\n- Feature 1\n- Feature 2",
            "tests/test_main.py": "import unittest\n\nclass TestMain(unittest.TestCase):\n    def test_main(self):\n        pass",
        }

    async def search_files(self, query: str) -> List[str]:
        """
        Simulate file search based on query pattern.
        """
        matches = []
        query_lower = query.lower()

        for file_path in self.available_files.keys():
            if query_lower in file_path.lower():
                matches.append(file_path)

        return matches

    async def load_recommended_files(self, query: str) -> Dict:
        """
        Recommend and load files relevant to query.
        """
        # Simple heuristic: search for matching files
        matches = await self.search_files(query)

        loaded = []
        failed = []

        for file_path in matches[:3]:  # Limit to 3 files
            content = self.available_files[file_path]
            file_ctx = self.context_manager.load_file(file_path, content)

            if file_ctx:
                loaded.append((file_path, file_ctx.tokens))
            else:
                failed.append((file_path, "Would overflow"))

        return {
            "query": query,
            "matches_found": len(matches),
            "loaded": loaded,
            "failed_to_load": failed,
        }


async def main():
    """
    Demo: Context window management strategies.
    """
    print("\n" + "="*70)
    print("Gemini CLI: Context Window Management Demo")
    print("="*70)

    context_manager = ContextWindowManager(max_tokens=10000)
    jit_loader = JITContextLoader(context_manager)

    # Demo 1: Initial state
    print("\n[DEMO 1] Initial Context Window State")
    print("-" * 70)
    status = context_manager.get_status()
    print(f"Token budget: {status['tokens_used']} / {context_manager.metrics.max_tokens}")
    print(f"Available: {status['tokens_available']} tokens")
    print(f"Usage: {status['usage_ratio']}")
    print(f"Will overflow: {status['will_overflow']}")

    # Demo 2: Adding events (user interaction)
    print("\n[DEMO 2] Adding Events to Context")
    print("-" * 70)
    user_queries = [
        "Help me debug this Python script",
        "What does the error mean?",
        "Show me the implementation",
    ]

    for i, query in enumerate(user_queries, 1):
        event_id = context_manager.add_event("user_query", query)
        status = context_manager.get_status()
        print(f"Event {event_id}: {query}")
        print(f"  → {status['tokens_used']} / {context_manager.metrics.max_tokens} tokens used")
        print()

    # Demo 3: JIT file loading
    print("[DEMO 3] Just-In-Time File Loading")
    print("-" * 70)
    print("Available files:")
    for path in jit_loader.available_files.keys():
        print(f"  - {path}")
    print()

    result = await jit_loader.load_recommended_files("python")
    print(f"Search for 'python':")
    print(f"  Found: {result['matches_found']} files")
    print(f"  Loaded: {len(result['loaded'])} files")
    for path, tokens in result['loaded']:
        print(f"    • {path} ({tokens} tokens)")
    if result['failed_to_load']:
        print(f"  Failed to load: {len(result['failed_to_load'])} files")

    # Demo 4: Overflow detection
    print("\n[DEMO 4] Overflow Detection & Handling")
    print("-" * 70)
    print(f"Current usage: {context_manager.metrics.usage_ratio:.1%}")

    # Try adding large event
    large_content = "x" * 50000  # 12,500 tokens
    status_before = context_manager.get_status()

    event_id = context_manager.add_event("large_response", large_content)

    if event_id >= 0:
        status_after = context_manager.get_status()
        print(f"✓ Large event added")
        print(f"  Before: {status_before['tokens_used']} tokens")
        print(f"  After: {status_after['tokens_used']} tokens")
    else:
        print(f"✗ Large event would overflow")
        print(f"  Would need {TokenEstimator.estimate_text(large_content)} tokens")
        print(f"  Available: {context_manager.metrics.available_tokens} tokens")

    # Demo 5: History compression
    print("\n[DEMO 5] History Compression")
    print("-" * 70)
    print(f"Before compression: {len(context_manager.events)} events")
    print(f"Tokens before: {context_manager.metrics.estimated_tokens}")

    compress_result = context_manager.compress_history(keep_recent_events=3)
    print(f"\nAfter compression:")
    print(f"  {compress_result.get('events_removed', 0)} events removed")
    print(f"  {compress_result.get('tokens_freed', 0)} tokens freed")
    print(f"  {len(context_manager.events)} events remaining")
    print(f"  {context_manager.metrics.estimated_tokens} tokens used")

    # Demo 6: File pruning
    print("\n[DEMO 6] File Pruning (LRU)")
    print("-" * 70)
    status = context_manager.get_status()
    print(f"Before pruning:")
    print(f"  Files loaded: {status['loaded_files_count']}")
    print(f"  Tokens used: {status['tokens_used']}")

    # Simulate loading more files
    for file_path in list(jit_loader.available_files.keys())[:4]:
        content = jit_loader.available_files[file_path]
        context_manager.load_file(file_path, content)

    status = context_manager.get_status()
    print(f"\nAfter loading 4 files:")
    print(f"  Files loaded: {status['loaded_files_count']}")
    print(f"  Tokens used: {status['tokens_used']}")

    prune_result = context_manager.prune_old_files(keep_count=2)
    print(f"\nAfter pruning (keep 2 most recent):")
    print(f"  Files removed: {prune_result.get('files_removed', 0)}")
    print(f"  Tokens freed: {prune_result.get('tokens_freed', 0)}")
    print(f"  Files remaining: {prune_result.get('remaining_files', 0)}")

    # Final status
    print("\n" + "="*70)
    print("Final Context Window Status")
    print("="*70)
    status = context_manager.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
