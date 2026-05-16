from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import main as api_main
from core.database import Base
from core.models import ConsultationJobRecord, ConsultationRecord


class DummyQueue:
    def __init__(self):
        self.submitted: list[str] = []

    def submit(self, job_id: str) -> None:
        self.submitted.append(job_id)

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


def _make_client(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(api_main, "init_db", lambda: None)
    monkeypatch.setattr(api_main, "_cleanup_expired_upload_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_main, "SessionLocal", TestingSessionLocal)
    api_main.app.dependency_overrides[api_main.get_db] = override_get_db
    api_main.app.state.agent = object()
    api_main.app.state.job_queue = DummyQueue()

    return TestClient(api_main.app), TestingSessionLocal


def test_health_endpoint(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["agent_ready"] is True


def test_consult_endpoint_returns_mocked_response(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    def fake_run_consultation(**kwargs):
        return api_main.ConsultResponse(
            report="mock report",
            preview_image_base64=None,
            consultation_id=1,
            session_id=kwargs["session_id"],
            status="completed",
            intent="clinical",
            perception_status="skipped",
            warnings=[],
            errors=[],
            evidence=[],
            trace=[],
        )

    monkeypatch.setattr(api_main, "_run_consultation", fake_run_consultation)

    response = client.post(
        "/v1/consult",
        json={"query": "请给出治疗建议", "reviewer_enabled": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"] == "mock report"
    assert payload["status"] == "completed"
    assert payload["intent"] == "clinical"


def test_collect_endpoint_returns_follow_up_questions(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    monkeypatch.setattr(api_main.redis_store, "get_session_context", lambda session_id: None)
    monkeypatch.setattr(api_main.redis_store, "set_session_context", lambda session_id, payload: None)

    response = client.post(
        "/v1/collect",
        json={"query": "患者最近总觉得右上腹不舒服", "reviewer_enabled": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["assistant_message"]
    assert payload["follow_up_questions"]
    assert payload["can_generate_report"] is False


def test_dispatch_endpoint_returns_sync_result_in_auto_mode(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    monkeypatch.setattr(
        api_main,
        "analyze_intent_routing",
        lambda query, image_path: {
            "intent": "education",
            "should_retrieve": True,
            "should_perceive": False,
            "routing_mode": "llm",
            "warnings": [],
            "errors": [],
        },
    )

    def fake_run_consultation(**kwargs):
        return api_main.ConsultResponse(
            report="dispatch sync report",
            preview_image_base64=None,
            consultation_id=11,
            session_id=kwargs["session_id"],
            status="completed",
            intent="education",
            perception_status="skipped",
            warnings=[],
            errors=[],
            evidence=[],
            trace=[],
        )

    monkeypatch.setattr(api_main, "_run_consultation", fake_run_consultation)

    response = client.post(
        "/v1/dispatch",
        params={"dispatch_mode": "auto"},
        json={"query": "summarize guideline follow-up", "reviewer_enabled": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "sync"
    assert payload["result"]["report"] == "dispatch sync report"
    assert payload["job"] is None


def test_dispatch_endpoint_returns_job_in_auto_mode_when_perception_needed(monkeypatch, tmp_path):
    client, TestingSessionLocal = _make_client(monkeypatch, tmp_path)

    monkeypatch.setattr(
        api_main,
        "analyze_intent_routing",
        lambda query, image_path: {
            "intent": "clinical",
            "should_retrieve": True,
            "should_perceive": True,
            "routing_mode": "llm",
            "warnings": [],
            "errors": [],
        },
    )

    response = client.post(
        "/v1/dispatch",
        params={"dispatch_mode": "auto"},
        json={
            "query": "analyze lesion volume",
            "image_path": "/tmp/scan.nii.gz",
            "reviewer_enabled": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "async"
    assert payload["job"]["status"] == "queued"
    assert api_main.app.state.job_queue.submitted == [payload["job"]["job_id"]]

    db = TestingSessionLocal()
    try:
        row = db.get(ConsultationJobRecord, payload["job"]["job_id"])
        assert row is not None
        assert "auto dispatch selected async" in row.warnings_json.lower()
    finally:
        db.close()


def test_dispatch_endpoint_honors_forced_sync(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    monkeypatch.setattr(
        api_main,
        "analyze_intent_routing",
        lambda query, image_path: {
            "intent": "clinical",
            "should_retrieve": True,
            "should_perceive": True,
            "routing_mode": "llm",
            "warnings": [],
            "errors": [],
        },
    )

    def fake_run_consultation(**kwargs):
        return api_main.ConsultResponse(
            report="forced sync report",
            preview_image_base64=None,
            consultation_id=12,
            session_id=kwargs["session_id"],
            status="completed",
            intent="clinical",
            perception_status="completed",
            warnings=[],
            errors=[],
            evidence=[],
            trace=[],
        )

    monkeypatch.setattr(api_main, "_run_consultation", fake_run_consultation)

    response = client.post(
        "/v1/dispatch",
        params={"dispatch_mode": "sync"},
        json={
            "query": "analyze lesion volume",
            "image_path": "/tmp/scan.nii.gz",
            "reviewer_enabled": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "sync"
    assert payload["result"]["report"] == "forced sync report"
    assert payload["job"] is None


def test_dispatch_upload_returns_async_job_when_auto_mode_needs_perception(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    monkeypatch.setattr(api_main.config, "UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(api_main.config, "UPLOAD_CACHE_DIR", str(tmp_path / "upload_cache"))
    monkeypatch.setattr(
        api_main,
        "analyze_intent_routing",
        lambda query, image_path: {
            "intent": "clinical",
            "should_retrieve": True,
            "should_perceive": True,
            "routing_mode": "llm",
            "warnings": [],
            "errors": [],
        },
    )

    response = client.post(
        "/v1/dispatch/upload",
        data={"query": "analyze uploaded nifti", "reviewer_enabled": "true", "dispatch_mode": "auto"},
        files={"image_file": ("scan.nii.gz", b"fake-nifti-content", "application/gzip")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "async"
    assert payload["job"]["status"] == "queued"


def test_submit_job_persists_record_and_queues_task(monkeypatch, tmp_path):
    client, TestingSessionLocal = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/v1/jobs",
        json={"query": "异步咨询测试", "reviewer_enabled": False},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert api_main.app.state.job_queue.submitted == [payload["job_id"]]

    db = TestingSessionLocal()
    try:
        row = db.get(ConsultationJobRecord, payload["job_id"])
        assert row is not None
        assert row.query == "异步咨询测试"
        assert row.reviewer_enabled is False
        assert row.status == "queued"
    finally:
        db.close()


def test_consult_upload_rejects_non_nifti_file(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    response = client.post(
        "/v1/consult/upload",
        data={"query": "上传测试"},
        files={"image_file": ("scan.txt", b"not-a-nifti", "text/plain")},
    )

    assert response.status_code == 400
    assert "nii.gz" in response.json()["detail"]


def test_consult_upload_returns_cache_miss_warning(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    monkeypatch.setattr(api_main.config, "UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(api_main.config, "UPLOAD_CACHE_DIR", str(tmp_path / "upload_cache"))

    def fake_run_consultation(**kwargs):
        return api_main.ConsultResponse(
            report="upload report",
            preview_image_base64=None,
            consultation_id=7,
            session_id=kwargs["session_id"],
            status="completed",
            intent="clinical",
            perception_status="skipped",
            warnings=[],
            errors=[],
            evidence=[],
            trace=[],
        )

    monkeypatch.setattr(api_main, "_run_consultation", fake_run_consultation)

    response = client.post(
        "/v1/consult/upload",
        data={"query": "上传咨询", "reviewer_enabled": "true"},
        files={"image_file": ("scan.nii.gz", b"fake-nifti-content", "application/gzip")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"] == "upload report"
    assert any("cache miss" in warning.lower() for warning in payload["warnings"])


def test_submit_upload_job_persists_warning_and_queues_task(monkeypatch, tmp_path):
    client, TestingSessionLocal = _make_client(monkeypatch, tmp_path)

    monkeypatch.setattr(api_main.config, "UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(api_main.config, "UPLOAD_CACHE_DIR", str(tmp_path / "upload_cache"))

    response = client.post(
        "/v1/jobs/upload",
        data={"query": "异步上传", "reviewer_enabled": "false"},
        files={"image_file": ("scan.nii.gz", b"fake-nifti-content", "application/gzip")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert api_main.app.state.job_queue.submitted == [payload["job_id"]]

    db = TestingSessionLocal()
    try:
        row = db.get(ConsultationJobRecord, payload["job_id"])
        assert row is not None
        assert "cache miss" in row.warnings_json.lower()
        assert row.image_path is not None
    finally:
        db.close()


def test_get_job_status_returns_404_for_missing_job(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    response = client.get("/v1/jobs/missing-job-id")

    assert response.status_code == 404


def test_get_job_status_returns_completed_result(monkeypatch, tmp_path):
    client, TestingSessionLocal = _make_client(monkeypatch, tmp_path)

    db = TestingSessionLocal()
    try:
        row = ConsultationJobRecord(
            id="job-123",
            session_id="session-1",
            query="状态查询",
            image_path=None,
            reviewer_enabled=True,
            status="completed",
            report="done",
            preview_image_base64=None,
            intent="clinical",
            perception_status="skipped",
            warnings_json='["warn"]',
            errors_json="[]",
            evidence_json="[]",
            trace_json="[]",
            consultation_id=10,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()

    response = client.get("/v1/jobs/job-123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-123"
    assert payload["status"] == "completed"
    assert payload["result"]["report"] == "done"


def test_list_consultations_supports_session_filter(monkeypatch, tmp_path):
    client, TestingSessionLocal = _make_client(monkeypatch, tmp_path)

    db = TestingSessionLocal()
    try:
        db.add_all(
            [
                ConsultationRecord(
                    session_id="session-a",
                    query="query-a",
                    report="report-a",
                    image_path=None,
                    has_preview=False,
                ),
                ConsultationRecord(
                    session_id="session-b",
                    query="query-b",
                    report="report-b",
                    image_path=None,
                    has_preview=False,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/v1/consultations", params={"session_id": "session-a"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["session_id"] == "session-a"


def test_get_consultation_returns_record_detail(monkeypatch, tmp_path):
    client, TestingSessionLocal = _make_client(monkeypatch, tmp_path)

    db = TestingSessionLocal()
    try:
        row = ConsultationRecord(
            session_id="session-detail",
            query="detail-query",
            report="detail-report",
            image_path="/tmp/scan.nii.gz",
            has_preview=False,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        consultation_id = row.id
    finally:
        db.close()

    response = client.get(f"/v1/consultations/{consultation_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == consultation_id
    assert payload["query"] == "detail-query"
    assert payload["report"] == "detail-report"


def test_consult_requires_api_key_when_configured(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(api_main.config, "SERVICE_API_KEY", "secret-key")

    response = client.post(
        "/v1/consult",
        json={"query": "需要鉴权"},
    )

    assert response.status_code == 401


def test_consult_accepts_valid_api_key_when_configured(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)
    monkeypatch.setattr(api_main.config, "SERVICE_API_KEY", "secret-key")

    def fake_run_consultation(**kwargs):
        return api_main.ConsultResponse(
            report="authorized report",
            preview_image_base64=None,
            consultation_id=2,
            session_id=kwargs["session_id"],
            status="completed",
            intent="clinical",
            perception_status="skipped",
            warnings=[],
            errors=[],
            evidence=[],
            trace=[],
        )

    monkeypatch.setattr(api_main, "_run_consultation", fake_run_consultation)

    response = client.post(
        "/v1/consult",
        headers={"X-API-Key": "secret-key"},
        json={"query": "带鉴权访问"},
    )

    assert response.status_code == 200
    assert response.json()["report"] == "authorized report"


def test_consult_loads_recent_session_context(monkeypatch, tmp_path):
    client, TestingSessionLocal = _make_client(monkeypatch, tmp_path)

    db = TestingSessionLocal()
    try:
        db.add_all(
            [
                ConsultationRecord(
                    session_id="session-memory",
                    query="first visit question",
                    report="first visit answer",
                    image_path=None,
                    has_preview=False,
                ),
                ConsultationRecord(
                    session_id="session-memory",
                    query="second visit question",
                    report="second visit answer",
                    image_path=None,
                    has_preview=False,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    captured_context: dict = {}

    class FakeAgent:
        def run(self, image_path, user_query, **kwargs):
            nonlocal captured_context
            captured_context = kwargs.get("user_context", {})
            return (
                "context aware report",
                None,
                {
                    "workflow_status": "completed",
                    "intent": "clinical",
                    "perception_status": "skipped",
                    "warnings": [],
                    "errors": [],
                    "evidence": [],
                    "trace": [],
                },
            )

    api_main.app.state.agent = FakeAgent()

    response = client.post(
        "/v1/consult",
        json={"query": "follow-up question", "session_id": "session-memory", "reviewer_enabled": True},
    )

    assert response.status_code == 200
    assert captured_context["recent_turns"][0]["query"] == "first visit question"
    assert captured_context["recent_turns"][1]["query"] == "second visit question"
    assert "first visit question" in captured_context["session_summary"]


def test_report_endpoint_uses_cached_session_image_path(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    monkeypatch.setattr(
        api_main.redis_store,
        "get_session_context",
        lambda session_id: {
            "session_summary": "cached session",
            "recent_turns": [{"query": "prior", "report": "answer"}],
            "latest_image_path": "/cached/image.nii.gz",
        },
    )

    captured_image_path = None

    class FakeAgent:
        def run(self, image_path, user_query, **kwargs):
            nonlocal captured_image_path
            captured_image_path = image_path
            return (
                "report from cached image path",
                None,
                {
                    "workflow_status": "completed",
                    "intent": "clinical",
                    "perception_status": "skipped",
                    "warnings": [],
                    "errors": [],
                    "evidence": [],
                    "trace": [],
                },
            )

    api_main.app.state.agent = FakeAgent()

    response = client.post(
        "/v1/report",
        json={"query": "请生成正式报告", "session_id": "session-memory", "reviewer_enabled": True},
    )

    assert response.status_code == 200
    assert captured_image_path == "/cached/image.nii.gz"


def test_job_events_stream_returns_error_for_missing_job(monkeypatch, tmp_path):
    client, _session = _make_client(monkeypatch, tmp_path)

    with client.stream("GET", "/v1/jobs/missing-job/events") as response:
        body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    assert response.status_code == 200
    assert "event: error" in body
    assert "Consultation job not found" in body


def test_job_events_stream_returns_completed_snapshot(monkeypatch, tmp_path):
    client, TestingSessionLocal = _make_client(monkeypatch, tmp_path)

    db = TestingSessionLocal()
    try:
        row = ConsultationJobRecord(
            id="job-sse-1",
            session_id="session-sse",
            query="sse-query",
            image_path=None,
            reviewer_enabled=True,
            status="completed",
            report="sse-report",
            preview_image_base64=None,
            intent="clinical",
            perception_status="skipped",
            warnings_json="[]",
            errors_json="[]",
            evidence_json="[]",
            trace_json="[]",
            consultation_id=21,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()

    with client.stream("GET", "/v1/jobs/job-sse-1/events") as response:
        body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())

    assert response.status_code == 200
    assert "event: job_completed" in body
    assert "sse-report" in body
