from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Optional


class InMemoryJobQueue:
    def __init__(self, handler: Callable[[str], None]):
        self._handler = handler
        self._queue: queue.Queue[Optional[str]] = queue.Queue()
        self._worker = threading.Thread(target=self._run, name="consultation-job-worker", daemon=True)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._worker.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._queue.put(None)
        self._worker.join(timeout=5)
        self._started = False

    def submit(self, job_id: str) -> None:
        self._queue.put(job_id)

    def qsize(self) -> int:
        return self._queue.qsize()

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                self._queue.task_done()
                break
            try:
                self._handler(job_id)
            finally:
                self._queue.task_done()
