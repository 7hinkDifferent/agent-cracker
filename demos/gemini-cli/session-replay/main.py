#!/usr/bin/env python3
"""
Session Replay & Event Streaming — Minimal reproduction of Gemini CLI's session recovery

This demo shows how Gemini CLI implements event-based session recovery:

1. All events are stored with unique IDs
2. A stream can be replayed from any eventId
3. New events are streamed in real-time after replay
4. Supports branching (create new stream from history point)

Key insights:
- Event-based approach enables fine-grained control
- Unlike conversation-based recovery, events preserve exact execution state
- Seamlessly switches from replaying history to receiving live events
- Enables non-linear navigation (undo, redo, branching)
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional
import logging


# ============================================================================
# Event Model
# ============================================================================

class EventType(str, Enum):
    """Types of events in agent execution"""
    AGENT_START = "agent_start"
    TEXT_CHUNK = "text_chunk"
    TOOL_CALL_REQUEST = "tool_call_request"
    TOOL_RESPONSE = "tool_response"
    AGENT_END = "agent_end"
    ERROR = "error"


@dataclass
class Event:
    """Single event in agent execution"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType = EventType.TEXT_CHUNK
    stream_id: str = ""  # Which stream does this event belong to?
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    data: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.type}: {self.data}"


# ============================================================================
# Event Store & History
# ============================================================================

class EventHistory:
    """Stores and retrieves events"""

    def __init__(self):
        self.events: list[Event] = []
        self.logger = logging.getLogger("EventHistory")

    def append(self, event: Event) -> None:
        """Add an event to history"""
        self.events.append(event)
        self.logger.debug(f"Recorded event: {event.id} ({event.type})")

    def get_by_id(self, event_id: str) -> Optional[Event]:
        """Get event by ID"""
        return next((e for e in self.events if e.id == event_id), None)

    def get_by_stream_id(self, stream_id: str) -> list[Event]:
        """Get all events for a specific stream"""
        return [e for e in self.events if e.stream_id == stream_id]

    def get_after_event(self, event_id: str, stream_id: str) -> list[Event]:
        """Get all events after a specific event ID (same stream)"""
        event = self.get_by_id(event_id)
        if not event:
            return []
        start_idx = next(
            (i for i, e in enumerate(self.events) if e.id == event_id), -1
        )
        if start_idx == -1:
            return []
        # Return events from this point onward that belong to the stream
        return [
            e
            for e in self.events[start_idx:]
            if e.stream_id == stream_id
        ]

    def all(self) -> list[Event]:
        """Get all events"""
        return self.events[:]

    def count(self) -> int:
        """Get number of events"""
        return len(self.events)


# ============================================================================
# Event Stream & Subscription
# ============================================================================

class EventStream:
    """
    Represents a single stream of execution in the agent.
    Supports replay from history + real-time subscriptions.
    """

    def __init__(self, stream_id: str, history: EventHistory):
        self.stream_id = stream_id
        self.history = history
        self.logger = logging.getLogger(f"EventStream/{stream_id[:8]}")
        self.subscribers: list[Callable[[Event], None]] = []
        self.queue: asyncio.Queue = asyncio.Queue()
        self.done = False

    def subscribe(self, callback: Callable[[Event], None]) -> Callable:
        """
        Subscribe to events from this stream.
        Returns unsubscribe function.
        """
        self.subscribers.append(callback)
        self.logger.info(f"Subscriber added (now {len(self.subscribers)})")

        def unsubscribe():
            if callback in self.subscribers:
                self.subscribers.remove(callback)
                self.logger.info(f"Subscriber removed (now {len(self.subscribers)})")

        return unsubscribe

    def emit_event(self, event: Event) -> None:
        """
        Emit event to all subscribers.
        Thread-safe through queue.
        """
        asyncio.create_task(self.queue.put(event))

    async def stream(
        self, replay_from_event_id: Optional[str] = None
    ) -> asyncio.AsyncGenerator[Event, None]:
        """
        Stream events, optionally replaying from a specific event.

        This is the core stream() method from agent-session.ts:
        1. If replay_from_event_id is set, yield replayed events
        2. Subscribe to new events
        3. Yield new events as they arrive
        4. Stop when stream is done
        """

        # Phase 1: Replay from history (if requested)
        replayed_count = 0
        if replay_from_event_id:
            events_to_replay = self.history.get_after_event(
                replay_from_event_id, self.stream_id
            )
            self.logger.info(f"Replaying {len(events_to_replay)} events")
            for event in events_to_replay:
                replayed_count += 1
                yield event
                # Small delay to simulate streaming
                await asyncio.sleep(0.01)

        # Phase 2: Subscribe to new events
        def on_event(event: Event):
            asyncio.create_task(self.queue.put(event))

        unsub = self.subscribe(on_event)

        try:
            # Yield new events as they arrive
            while not self.done:
                try:
                    event = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    # Check if stream is done
                    if self.done:
                        break
                    continue
        finally:
            unsub()
            self.logger.info(
                f"Stream closed (replayed {replayed_count}, received {self.queue.qsize()})"
            )


# ============================================================================
# Agent Session (Managing Multiple Streams)
# ============================================================================

class AgentSession:
    """
    Manages event history and multiple concurrent streams.
    Mirrors AgentSession class in agent-session.ts.
    """

    def __init__(self):
        self.history = EventHistory()
        self.streams: dict[str, EventStream] = {}
        self.logger = logging.getLogger("AgentSession")

    def create_stream(self) -> EventStream:
        """Create a new execution stream"""
        stream_id = str(uuid.uuid4())[:8]
        stream = EventStream(stream_id, self.history)
        self.streams[stream_id] = stream
        self.logger.info(f"Created stream: {stream_id}")
        return stream

    def record_event(self, event: Event) -> None:
        """Record an event and emit to all streams"""
        self.history.append(event)
        if event.stream_id in self.streams:
            self.streams[event.stream_id].emit_event(event)

    def get_stream(self, stream_id: str) -> Optional[EventStream]:
        """Get a stream by ID"""
        return self.streams.get(stream_id)

    def get_history(self) -> list[Event]:
        """Get all recorded events"""
        return self.history.all()


# ============================================================================
# Example Usage
# ============================================================================

async def simulate_agent_run(session: AgentSession, stream_id: str):
    """
    Simulate an agent execution that records events.
    """
    logger = logging.getLogger("SimulatedAgent")

    # Emit events
    events_to_emit = [
        Event(type=EventType.AGENT_START, stream_id=stream_id, data={"query": "help"}),
        Event(type=EventType.TEXT_CHUNK, stream_id=stream_id, data={"text": "I'll "}),
        Event(type=EventType.TEXT_CHUNK, stream_id=stream_id, data={"text": "help"}),
        Event(
            type=EventType.TOOL_CALL_REQUEST,
            stream_id=stream_id,
            data={"name": "read_file", "path": "main.py"},
        ),
        Event(
            type=EventType.TOOL_RESPONSE,
            stream_id=stream_id,
            data={"output": "File contents..."},
        ),
        Event(
            type=EventType.TEXT_CHUNK,
            stream_id=stream_id,
            data={"text": "Done!"},
        ),
        Event(type=EventType.AGENT_END, stream_id=stream_id, data={"reason": "stop"}),
    ]

    for event in events_to_emit:
        session.record_event(event)
        await asyncio.sleep(0.1)  # Simulate streaming delays
        logger.info(f"Emitted: {event}")


async def consume_stream(
    session: AgentSession,
    stream_id: str,
    replay_from_event_id: Optional[str] = None,
):
    """Subscribe to a stream and consume events"""
    logger = logging.getLogger("StreamConsumer")

    stream = session.get_stream(stream_id)
    if not stream:
        logger.error(f"Stream not found: {stream_id}")
        return

    logger.info(f"Consuming stream {stream_id[:8]}...")
    if replay_from_event_id:
        logger.info(f"  Replaying from event: {replay_from_event_id[:8]}")

    count = 0
    async for event in stream.stream(replay_from_event_id=replay_from_event_id):
        count += 1
        logger.info(f"[{count}] {event}")
        if event.type == EventType.AGENT_END:
            stream.done = True
            break


async def main():
    """Demonstrate session replay"""

    logging.basicConfig(
        level=logging.INFO,
        format="%(name)-20s | %(message)s",
    )

    session = AgentSession()

    print("=" * 70)
    print("SESSION REPLAY & EVENT STREAMING")
    print("=" * 70)

    # Test 1: Normal stream (no replay)
    print("\n[Test 1] Normal execution stream")
    print("-" * 70)

    stream1 = session.create_stream()
    stream1_id = stream1.stream_id

    consumer_task = asyncio.create_task(consume_stream(session, stream1_id))
    producer_task = asyncio.create_task(simulate_agent_run(session, stream1_id))

    await asyncio.gather(producer_task, consumer_task)

    # Test 2: Replay from middle
    print("\n[Test 2] Replay from middle event")
    print("-" * 70)

    all_events = session.get_history()
    middle_event = all_events[2]  # TEXT_CHUNK "help"
    print(f"Replaying from event: {middle_event.type} ({middle_event.id[:8]})")

    stream2 = session.create_stream()
    stream2_id = stream2.stream_id

    consumer_task2 = asyncio.create_task(
        consume_stream(session, stream2_id, replay_from_event_id=middle_event.id)
    )
    await asyncio.sleep(0.5)  # Let replay start
    stream2.done = True
    await consumer_task2

    # Test 3: Event history
    print("\n[Test 3] Event history summary")
    print("-" * 70)

    history = session.get_history()
    print(f"Total events recorded: {len(history)}")
    for i, event in enumerate(history, 1):
        print(f"  {i}. {event.type.value:20s} | {event.id[:8]}")


if __name__ == "__main__":
    asyncio.run(main())
