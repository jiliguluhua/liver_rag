from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import main as api_main
from core.database import Base
from core.models import ConsultationJobRecord


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
