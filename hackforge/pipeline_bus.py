"""Pipeline Event Bus — real-time streaming of pipeline step events.

Provides a pub/sub mechanism using asyncio queues so that engines can
emit events at each processing step and SSE endpoints can stream them
to the browser in real time.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PipelineEvent:
    """A single event emitted during pipeline processing."""

    event_type: str  # "step" | "progress" | "result" | "error" | "agent"
    engine: str  # "link_intel" | "tool_forge" | "agent" | "video_intel"
    step: str  # "scrape" | "extract" | "research" | "graph" | "integrate" | ...
    message: str  # Human-readable description
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class PipelineBus:
    """Async event bus using per-subscriber queues.

    Each subscriber gets its own asyncio.Queue. When an event is emitted,
    it is pushed to every active subscriber queue. Subscribers that are
    slow or disconnected are pruned automatically.

    Usage::

        bus = PipelineBus()

        # In the SSE endpoint:
        queue = bus.subscribe()
        try:
            while True:
                event = await queue.get()
                yield f"data: {event.to_json()}\\n\\n"
        finally:
            bus.unsubscribe(queue)

        # In an engine:
        await bus.emit(PipelineEvent(
            event_type="step",
            engine="link_intel",
            step="scrape",
            message="Scraping https://lu.ma/sfagents...",
        ))
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[PipelineEvent]] = []
        self._history: list[PipelineEvent] = []
        self._max_history = 200

    def subscribe(self) -> asyncio.Queue[PipelineEvent]:
        """Create a new subscriber queue and return it."""
        queue: asyncio.Queue[PipelineEvent] = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        logger.debug("PipelineBus: new subscriber (total=%d)", len(self._subscribers))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[PipelineEvent]) -> None:
        """Remove a subscriber queue."""
        try:
            self._subscribers.remove(queue)
            logger.debug("PipelineBus: removed subscriber (total=%d)", len(self._subscribers))
        except ValueError:
            pass

    async def emit(self, event: PipelineEvent) -> None:
        """Push an event to all subscriber queues."""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        dead: list[asyncio.Queue[PipelineEvent]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(queue)
                logger.warning("PipelineBus: dropping slow subscriber")

        for q in dead:
            self.unsubscribe(q)

    async def emit_step(
        self,
        engine: str,
        step: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Convenience: emit a 'step' event."""
        await self.emit(PipelineEvent(
            event_type="step",
            engine=engine,
            step=step,
            message=message,
            data=data or {},
        ))

    async def emit_error(
        self,
        engine: str,
        step: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Convenience: emit an 'error' event."""
        await self.emit(PipelineEvent(
            event_type="error",
            engine=engine,
            step=step,
            message=message,
            data=data or {},
        ))

    async def emit_result(
        self,
        engine: str,
        step: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Convenience: emit a 'result' event."""
        await self.emit(PipelineEvent(
            event_type="result",
            engine=engine,
            step=step,
            message=message,
            data=data or {},
        ))

    async def emit_agent(
        self,
        step: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Convenience: emit an 'agent' event (Claude integration steps)."""
        await self.emit(PipelineEvent(
            event_type="agent",
            engine="agent",
            step=step,
            message=message,
            data=data or {},
        ))

    @property
    def history(self) -> list[PipelineEvent]:
        """Return recent event history."""
        return list(self._history)


# ---------------------------------------------------------------------------
# Global singleton — imported by api.py and engines
# ---------------------------------------------------------------------------

pipeline_bus = PipelineBus()
