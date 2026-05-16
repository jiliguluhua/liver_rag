from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from langchain_core.documents import Document

from core import config

try:
    from redis import Redis
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - handled gracefully when dependency is unavailable
    Redis = None  # type: ignore[assignment]

    class RedisError(Exception):
        pass


class RedisStore:
    def __init__(self) -> None:
        self._client: Optional[Redis] = None
        self._enabled = bool(config.REDIS_URL)

    def is_enabled(self) -> bool:
        return self._enabled and self._get_client() is not None

    def _get_client(self) -> Optional[Redis]:
        if not self._enabled or Redis is None:
            return None
        if self._client is not None:
            return self._client
        try:
            self._client = Redis.from_url(config.REDIS_URL, decode_responses=True)
            self._client.ping()
        except RedisError:
            self._client = None
            self._enabled = False
        return self._client

    def get_client(self) -> Optional[Redis]:
        return self._get_client()

    def get_json(self, key: str) -> Optional[dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return None
        try:
            raw = client.get(key)
        except RedisError:
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def set_json(self, key: str, data: dict[str, Any], ttl_seconds: int) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            client.setex(key, ttl_seconds, json.dumps(data, ensure_ascii=False))
        except RedisError:
            return

    def publish(self, channel: str, data: dict[str, Any]) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            client.publish(channel, json.dumps(data, ensure_ascii=False))
        except RedisError:
            return

    def build_job_status_key(self, job_id: str) -> str:
        return f"liver:job_status:{job_id}"

    def set_job_status(self, job_id: str, payload: dict[str, Any]) -> None:
        self.set_json(self.build_job_status_key(job_id), payload, config.REDIS_JOB_STATUS_TTL_SECONDS)

    def get_job_status(self, job_id: str) -> Optional[dict[str, Any]]:
        return self.get_json(self.build_job_status_key(job_id))

    def build_search_key(self, query: str, top_k: int) -> str:
        digest = hashlib.sha256(f"{query}|{top_k}".encode("utf-8")).hexdigest()
        return f"liver:search:{digest}"

    def get_search_results(self, query: str, top_k: int) -> Optional[list[Document]]:
        cached = self.get_json(self.build_search_key(query, top_k))
        if not cached:
            return None
        items = cached.get("documents", [])
        if not isinstance(items, list):
            return None
        docs: list[Document] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            docs.append(
                Document(
                    page_content=str(item.get("page_content", "")),
                    metadata=item.get("metadata", {}) or {},
                )
            )
        return docs

    def set_search_results(self, query: str, top_k: int, docs: list[Document]) -> None:
        payload = {
            "documents": [
                {
                    "page_content": doc.page_content,
                    "metadata": getattr(doc, "metadata", {}) or {},
                }
                for doc in docs
            ]
        }
        self.set_json(self.build_search_key(query, top_k), payload, config.REDIS_SEARCH_CACHE_TTL_SECONDS)


redis_store = RedisStore()
