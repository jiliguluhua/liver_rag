from __future__ import annotations

import json
import queue
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from services.redis_store import RedisError, redis_store


@dataclass
class JobEvent:
    event: str
    data: dict[str, Any]


class BaseJobEventBus(Protocol):
    def subscribe(self, job_id: str) -> queue.Queue[JobEvent]:
        ...

    def unsubscribe(self, job_id: str, q: queue.Queue[JobEvent]) -> None:
        ...

    def publish(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        ...


class InMemoryJobEventBus:
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


class RedisJobEventBus:
    def __init__(self) -> None:
        self._listeners: dict[tuple[str, int], tuple[Any, threading.Thread]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _channel(job_id: str) -> str:
        return f"liver:job_events:{job_id}"

    def subscribe(self, job_id: str) -> queue.Queue[JobEvent]:
        q: queue.Queue[JobEvent] = queue.Queue()
        client = redis_store.get_client()
        if client is None:
            return q

        pubsub = client.pubsub()
        pubsub.subscribe(self._channel(job_id))
        worker = threading.Thread(
            target=self._forward_messages,
            args=(pubsub, q),
            name=f"redis-job-event-{job_id}",
            daemon=True,
        )
        with self._lock:
            self._listeners[(job_id, id(q))] = (pubsub, worker)
        worker.start()
        return q

    def unsubscribe(self, job_id: str, q: queue.Queue[JobEvent]) -> None:
        listener: Optional[tuple[Any, threading.Thread]]
        with self._lock:
            listener = self._listeners.pop((job_id, id(q)), None)
        if listener is None:
            return
        pubsub, worker = listener
        try:
            pubsub.unsubscribe(self._channel(job_id))
        except RedisError:
            pass
        try:
            pubsub.close()
        except RedisError:
            pass
        worker.join(timeout=0.2)

    def publish(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        redis_store.publish(self._channel(job_id), {"event": event, "data": data})

    def _forward_messages(self, pubsub: Any, target: queue.Queue[JobEvent]) -> None:
        try:
            for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                raw_data = message.get("data")
                if not isinstance(raw_data, str):
                    continue
                try:
                    payload = json.loads(raw_data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                event = payload.get("event")
                data = payload.get("data")
                if not isinstance(event, str) or not isinstance(data, dict):
                    continue
                target.put(JobEvent(event=event, data=data))
        except RedisError:
            return
        except OSError:
            return


def build_job_event_bus() -> BaseJobEventBus:
    if redis_store.is_enabled():
        return RedisJobEventBus()
    return InMemoryJobEventBus()


JobEventBus = InMemoryJobEventBus
job_event_bus = build_job_event_bus()
