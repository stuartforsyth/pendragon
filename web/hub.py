"""Server-sent-events hub: tells every open GM console and Table screen that
the session changed. Messages are tiny (a sequence number + a reason); clients
fetch what they need, so a reconnecting client can never miss an event."""

import asyncio
import json


class Hub:
    def __init__(self):
        self._queues = set()

    def subscribe(self):
        q = asyncio.Queue(maxsize=256)
        self._queues.add(q)
        return q

    @property
    def viewers(self):
        """How many live streams are open (one per browser: its tabs share one)."""
        return len(self._queues)

    def unsubscribe(self, q):
        self._queues.discard(q)

    def publish(self, message):
        data = json.dumps(message)
        for q in list(self._queues):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:     # a stalled client — drop it
                self._queues.discard(q)

    async def stream(self, q, heartbeat=15.0):
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=heartbeat)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self.unsubscribe(q)
