from __future__ import annotations

from services.job_events import JobEventBus


def test_job_event_bus_publish_and_unsubscribe():
    bus = JobEventBus()
    subscriber = bus.subscribe("job-1")

    bus.publish("job-1", "job_update", {"status": "running"})
    event = subscriber.get_nowait()

    assert event.event == "job_update"
    assert event.data["status"] == "running"

    bus.unsubscribe("job-1", subscriber)
    assert "job-1" not in bus._subscribers

