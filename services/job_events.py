from __future__ import annotations

import queue
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class JobEvent:
    event: str
    data: dict[str, Any]


class JobEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[queue.Queue[JobEvent]]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, job_id: str) -> queue.Queue[JobEvent]:
        q: queue.Queue[JobEvent] = queue.Queue()
        with self._lock:
            self._subscribers[job_id].append(q)
        return q

    def unsubscribe(self, job_id: str, q: queue.Queue[JobEvent]) -> None:
        with self._lock:
            subscribers = self._subscribers.get(job_id, [])
            if q in subscribers:
                subscribers.remove(q)
            if not subscribers and job_id in self._subscribers:
                del self._subscribers[job_id]

    def publish(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        payload = JobEvent(event=event, data=data)
        with self._lock:
            subscribers = list(self._subscribers.get(job_id, []))
        for subscriber in subscribers:
            subscriber.put(payload)


job_event_bus = JobEventBus()
