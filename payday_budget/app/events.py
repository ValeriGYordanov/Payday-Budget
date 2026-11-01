"""In-process broadcaster for the SSE `changed` event (§6.4)."""

import asyncio

CHANGED = "changed"


class Broadcaster:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[str]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[str]:
        # One pending event is enough: `changed` carries no data, so repeats coalesce.
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._queues.discard(queue)

    @property
    def subscribers(self) -> int:
        return len(self._queues)

    def publish(self, event: str = CHANGED) -> None:
        """Call from the event loop."""
        for queue in self._queues:
            if not queue.full():
                queue.put_nowait(event)

    def publish_threadsafe(self, event: str = CHANGED) -> None:
        """Call from worker threads (e.g. the scheduler job)."""
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self.publish, event)
