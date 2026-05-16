from __future__ import annotations

import json

from services import job_events
from services.job_events import InMemoryJobEventBus, RedisJobEventBus, build_job_event_bus


def test_job_event_bus_publish_and_unsubscribe():
    bus = InMemoryJobEventBus()
    subscriber = bus.subscribe("job-1")

    bus.publish("job-1", "job_update", {"status": "running"})
    event = subscriber.get_nowait()

    assert event.event == "job_update"
    assert event.data["status"] == "running"

    bus.unsubscribe("job-1", subscriber)
    assert "job-1" not in bus._subscribers


def test_build_job_event_bus_uses_redis_when_enabled(monkeypatch):
    monkeypatch.setattr(job_events.redis_store, "is_enabled", lambda: True)

    bus = build_job_event_bus()

    assert isinstance(bus, RedisJobEventBus)


def test_build_job_event_bus_falls_back_to_memory_when_redis_disabled(monkeypatch):
    monkeypatch.setattr(job_events.redis_store, "is_enabled", lambda: False)

    bus = build_job_event_bus()

    assert isinstance(bus, InMemoryJobEventBus)


def test_redis_job_event_bus_publish_uses_redis_channel(monkeypatch):
    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        job_events.redis_store,
        "publish",
        lambda channel, data: published.append((channel, data)),
    )

    bus = RedisJobEventBus()
    bus.publish("job-42", "node_update", {"status": "running"})

    assert published == [
        (
            "liver:job_events:job-42",
            {"event": "node_update", "data": {"status": "running"}},
        )
    ]


def test_redis_job_event_bus_subscribe_forwards_pubsub_messages(monkeypatch):
    class FakePubSub:
        def __init__(self) -> None:
            self.channels: list[str] = []
            self.closed = False
            self.unsubscribed: list[str] = []

        def subscribe(self, channel: str) -> None:
            self.channels.append(channel)

        def unsubscribe(self, channel: str) -> None:
            self.unsubscribed.append(channel)

        def close(self) -> None:
            self.closed = True

        def listen(self):
            yield {"type": "subscribe", "data": 1}
            yield {
                "type": "message",
                "data": json.dumps({"event": "job_update", "data": {"status": "running"}}),
            }
            while not self.closed:
                yield {"type": "subscribe", "data": 1}

    class FakeRedisClient:
        def __init__(self) -> None:
            self.pubsub_instance = FakePubSub()

        def pubsub(self) -> FakePubSub:
            return self.pubsub_instance

    fake_client = FakeRedisClient()
    monkeypatch.setattr(job_events.redis_store, "get_client", lambda: fake_client)

    bus = RedisJobEventBus()
    subscriber = bus.subscribe("job-77")
    event = subscriber.get(timeout=1)

    assert event.event == "job_update"
    assert event.data["status"] == "running"

    bus.unsubscribe("job-77", subscriber)
    assert fake_client.pubsub_instance.unsubscribed == ["liver:job_events:job-77"]
    assert fake_client.pubsub_instance.closed is True
