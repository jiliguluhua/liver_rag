from __future__ import annotations

from langchain_core.documents import Document

from services.redis_store import RedisStore


def test_redis_store_is_disabled_without_url(monkeypatch):
    monkeypatch.setattr("services.redis_store.config.REDIS_URL", "")
    store = RedisStore()

    assert store.is_enabled() is False
    assert store.get_job_status("job-1") is None


def test_redis_store_search_serialization_round_trip(monkeypatch):
    monkeypatch.setattr("services.redis_store.config.REDIS_URL", "redis://unused")
    monkeypatch.setattr("services.redis_store.config.REDIS_SEARCH_CACHE_TTL_SECONDS", 30)
    store = RedisStore()

    captured: dict[str, dict] = {}
    monkeypatch.setattr(store, "set_json", lambda key, data, ttl_seconds: captured.update({key: data}))
    monkeypatch.setattr(store, "get_json", lambda key: captured.get(key))

    docs = [Document(page_content="guide text", metadata={"source": "guideline.pdf"})]
    store.set_search_results("肝癌治疗", 3, docs)
    restored = store.get_search_results("肝癌治疗", 3)

    assert restored is not None
    assert restored[0].page_content == "guide text"
    assert restored[0].metadata["source"] == "guideline.pdf"


def test_redis_store_session_context_round_trip(monkeypatch):
    monkeypatch.setattr("services.redis_store.config.REDIS_URL", "redis://unused")
    monkeypatch.setattr("services.redis_store.config.REDIS_SESSION_CONTEXT_TTL_SECONDS", 60)
    store = RedisStore()

    captured: dict[str, dict] = {}
    monkeypatch.setattr(store, "set_json", lambda key, data, ttl_seconds: captured.update({key: data}))
    monkeypatch.setattr(store, "get_json", lambda key: captured.get(key))

    payload = {
        "session_summary": "Q: prior question A: prior answer",
        "recent_turns": [{"query": "prior question", "report": "prior answer"}],
    }
    store.set_session_context("session-ctx", payload)
    restored = store.get_session_context("session-ctx")

    assert restored == payload
