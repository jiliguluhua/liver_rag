from __future__ import annotations

import asyncio
import base64
import json
import hashlib
import io
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from PIL import Image
from sqlalchemy.orm import Session

from api.schemas import (
    ConsultRequest,
    ConsultResponse,
    ConsultationSummary,
    DispatchDecision,
    DispatchResponse,
    DispatchMode,
    HealthResponse,
    JobStatusResponse,
    JobSubmitResponse,
)
from core import config
from core.database import SessionLocal, get_db, init_db
from core.models import ConsultationJobRecord, ConsultationRecord
from agents.nodes import analyze_intent_routing
from services.job_events import job_event_bus
from services.job_queue import InMemoryJobQueue
from services.medical_agent import LiverSmartAgent
from services.redis_store import redis_store


WEB_INDEX_PATH = Path(__file__).resolve().parent.parent / "web" / "index.html"


def _pil_to_png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _optional_service_auth(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    expected = (config.SERVICE_API_KEY or "").strip()
    if not expected:
        return
    if (x_api_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def _normalize_dispatch_mode(raw_mode: Optional[str]) -> DispatchMode:
    mode = (raw_mode or "auto").strip().lower()
    if mode not in {"auto", "sync", "async"}:
        raise HTTPException(status_code=400, detail="dispatch_mode must be one of: auto, sync, async")
    return mode  # type: ignore[return-value]


def _cleanup_expired_upload_cache(cache_root: Path) -> None:
    ttl = timedelta(hours=config.UPLOAD_CACHE_TTL_HOURS)
    now = datetime.utcnow()
    if not cache_root.exists():
        return
    for entry in cache_root.iterdir():
        if not entry.is_dir():
            continue
        modified_at = datetime.utcfromtimestamp(entry.stat().st_mtime)
        if now - modified_at > ttl:
            shutil.rmtree(entry, ignore_errors=True)


def _write_upload_and_hash(upload_file: UploadFile, output_path: Path) -> str:
    hasher = hashlib.sha256()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            f.write(chunk)
    upload_file.file.seek(0)
    return hasher.hexdigest()


def _resolve_cache_paths(content_hash: str) -> tuple[Path, Path]:
    cache_dir = Path(config.UPLOAD_CACHE_DIR) / content_hash
    cached_file_path = cache_dir / "image.nii.gz"
    return cache_dir, cached_file_path


def _save_consultation(
    db: Session,
    *,
    session_id: str,
    query: str,
    report: str,
    image_path: Optional[str],
    has_preview: bool,
) -> ConsultationRecord:
    row = ConsultationRecord(
        session_id=session_id,
        query=query,
        report=report,
        image_path=image_path,
        has_preview=has_preview,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _json_loads_list(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _json_dumps(data: list | dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def _build_consult_response(
    *,
    row: ConsultationRecord,
    report: str,
    preview_img: Optional[Image.Image],
    final_state: dict,
) -> ConsultResponse:
    preview_b64 = _pil_to_png_b64(preview_img) if preview_img is not None else None
    return ConsultResponse(
        report=report,
        preview_image_base64=preview_b64,
        consultation_id=row.id,
        session_id=row.session_id,
        status=final_state.get("workflow_status", "completed"),
        intent=final_state.get("intent"),
        perception_status=final_state.get("perception_status"),
        warnings=list(final_state.get("warnings", [])),
        errors=list(final_state.get("errors", [])),
        evidence=list(final_state.get("evidence", [])),
        trace=list(final_state.get("trace", [])),
    )


def _build_job_status_response(row: ConsultationJobRecord) -> JobStatusResponse:
    result: Optional[ConsultResponse] = None
    if row.status == "completed" and row.report is not None:
        result = ConsultResponse(
            report=row.report,
            preview_image_base64=row.preview_image_base64,
            consultation_id=row.consultation_id or 0,
            session_id=row.session_id,
            status=row.status,
            intent=row.intent,
            perception_status=row.perception_status,
            warnings=_json_loads_list(row.warnings_json),
            errors=_json_loads_list(row.errors_json),
            evidence=_json_loads_list(row.evidence_json),
            trace=_json_loads_list(row.trace_json),
        )
    return JobStatusResponse(
        job_id=row.id,
        session_id=row.session_id,
        status=row.status,
        query=row.query,
        image_path=row.image_path,
        reviewer_enabled=row.reviewer_enabled,
        consultation_id=row.consultation_id,
        error_message=row.error_message,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        result=result,
    )


def _cache_job_status_snapshot(snapshot: JobStatusResponse) -> None:
    redis_store.set_job_status(snapshot.job_id, snapshot.model_dump(mode="json"))


def _serialize_sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _submit_job_record(
    *,
    db: Session,
    session_id: str,
    query: str,
    image_path: Optional[str],
    reviewer_enabled: bool,
    warnings: Optional[list[str]] = None,
) -> JobSubmitResponse:
    job_id = str(uuid.uuid4())
    row = ConsultationJobRecord(
        id=job_id,
        session_id=session_id,
        query=query,
        image_path=image_path,
        reviewer_enabled=reviewer_enabled,
        status="queued",
        warnings_json=_json_dumps(warnings or []),
    )
    db.add(row)
    db.commit()
    _cache_job_status_snapshot(_build_job_status_response(row))
    app.state.job_queue.submit(job_id)
    return JobSubmitResponse(job_id=job_id, session_id=session_id, status="queued")


def _build_dispatch_decision(
    *,
    query: str,
    image_path: Optional[str],
    reviewer_enabled: bool,
    requested_mode: DispatchMode,
    upload_present: bool,
) -> DispatchDecision:
    normalized_image_path = (image_path or "").strip()
    routing = analyze_intent_routing(query, normalized_image_path)
    should_retrieve = bool(routing["should_retrieve"])
    should_perceive = bool(routing["should_perceive"])
    intent_hint = str(routing["intent"])
    has_image_signal = upload_present or bool(normalized_image_path)
    llm_reason = (
        f"Shared analyzer classified intent={intent_hint}, "
        f"retrieve={should_retrieve}, perceive={should_perceive}."
    )

    if requested_mode == "sync":
        return DispatchDecision(
            mode="sync",
            reason=f"Manual override forced synchronous execution. {llm_reason}",
            should_retrieve=should_retrieve,
            should_perceive=should_perceive,
            intent_hint=intent_hint,
        )
    if requested_mode == "async":
        return DispatchDecision(
            mode="async",
            reason=f"Manual override forced asynchronous execution. {llm_reason}",
            should_retrieve=should_retrieve,
            should_perceive=should_perceive,
            intent_hint=intent_hint,
        )

    if should_perceive and upload_present:
        reason = f"Auto dispatch selected async because upload-backed image analysis is required. {llm_reason}"
        mode: DispatchMode = "async"
    elif should_perceive and reviewer_enabled:
        reason = f"Auto dispatch selected async because perception is required and reviewer processing is enabled. {llm_reason}"
        mode = "async"
    elif should_perceive and has_image_signal:
        reason = f"Auto dispatch selected async because shared analyzer requested image perception. {llm_reason}"
        mode = "async"
    elif routing.get("errors"):
        reason = f"Auto dispatch selected async because analyzer routing fell back after an error. {llm_reason}"
        mode = "async"
    else:
        reason = f"Auto dispatch selected sync because shared analyzer did not require image perception. {llm_reason}"
        mode = "sync"

    return DispatchDecision(
        mode=mode,
        reason=reason,
        should_retrieve=should_retrieve,
        should_perceive=should_perceive,
        intent_hint=intent_hint,
    )


def _execute_dispatch(
    *,
    db: Session,
    query: str,
    session_id: Optional[str],
    image_path: Optional[str],
    reviewer_enabled: bool,
    requested_mode: DispatchMode,
    upload_present: bool,
    extra_warnings: Optional[list[str]] = None,
) -> DispatchResponse:
    active_session_id = (session_id or "").strip() or str(uuid.uuid4())
    normalized_image_path = (image_path or "").strip() or (config.DEFAULT_DICOM_DIR or "").strip() or None
    decision = _build_dispatch_decision(
        query=query,
        image_path=normalized_image_path,
        reviewer_enabled=reviewer_enabled,
        requested_mode=requested_mode,
        upload_present=upload_present,
    )

    if decision.mode == "async":
        warnings = list(extra_warnings or [])
        warnings.append(decision.reason)
        job = _submit_job_record(
            db=db,
            session_id=active_session_id,
            query=query,
            image_path=normalized_image_path,
            reviewer_enabled=reviewer_enabled,
            warnings=warnings,
        )
        return DispatchResponse(mode="async", decision=decision, job=job)

    result = _run_consultation(
        agent=app.state.agent,
        db=db,
        job_id=None,
        session_id=active_session_id,
        query=query,
        image_path=normalized_image_path,
        reviewer_enabled=reviewer_enabled,
    )
    merged_warnings = [*result.warnings, *(extra_warnings or []), decision.reason]
    return DispatchResponse(
        mode="sync",
        decision=decision,
        result=result.model_copy(update={"warnings": merged_warnings}),
    )


def _run_consultation(
    *,
    agent: LiverSmartAgent,
    db: Session,
    job_id: Optional[str],
    session_id: str,
    query: str,
    image_path: Optional[str],
    reviewer_enabled: bool,
) -> ConsultResponse:
    report, preview_img, final_state = agent.run(
        image_path,
        query,
        job_id=job_id,
        session_id=session_id,
        reviewer_enabled=reviewer_enabled,
    )
    row = _save_consultation(
        db,
        session_id=session_id,
        query=query,
        report=report,
        image_path=image_path,
        has_preview=preview_img is not None,
    )
    return _build_consult_response(
        row=row,
        report=report,
        preview_img=preview_img,
        final_state=final_state,
    )


def _process_consultation_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(ConsultationJobRecord, job_id)
        if job is None:
            return
        queued_warnings = _json_loads_list(job.warnings_json)

        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()
        _cache_job_status_snapshot(_build_job_status_response(job))
        job_event_bus.publish(job_id, "job_update", {"job_id": job_id, "status": "running", "message": "Background worker started processing."})

        agent: LiverSmartAgent = app.state.agent
        consult_response = _run_consultation(
            agent=agent,
            db=db,
            job_id=job_id,
            session_id=job.session_id,
            query=job.query,
            image_path=job.image_path,
            reviewer_enabled=job.reviewer_enabled,
        )

        job.status = "completed"
        job.error_message = None
        job.report = consult_response.report
        job.preview_image_base64 = consult_response.preview_image_base64
        job.intent = consult_response.intent
        job.perception_status = consult_response.perception_status
        job.warnings_json = _json_dumps([*queued_warnings, *consult_response.warnings])
        job.errors_json = _json_dumps(consult_response.errors)
        job.evidence_json = _json_dumps(consult_response.evidence)
        job.trace_json = _json_dumps(consult_response.trace)
        job.consultation_id = consult_response.consultation_id
        job.completed_at = datetime.utcnow()
        db.commit()
        _cache_job_status_snapshot(_build_job_status_response(job))
        job_event_bus.publish(
            job_id,
            "job_completed",
            {
                "job_id": job_id,
                "status": "completed",
                "message": "Background worker completed the task.",
                "result": consult_response.model_dump(mode="json"),
                "consultation_id": consult_response.consultation_id,
            },
        )
    except Exception as exc:
        job = db.get(ConsultationJobRecord, job_id)
        if job is not None:
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db.commit()
            _cache_job_status_snapshot(_build_job_status_response(job))
            job_event_bus.publish(
                job_id,
                "job_failed",
                {
                    "job_id": job_id,
                    "status": "failed",
                    "message": "Background worker failed.",
                    "error_message": str(exc),
                },
            )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _cleanup_expired_upload_cache(Path(config.UPLOAD_CACHE_DIR))
    app.state.agent = LiverSmartAgent(api_key=config.LLM_API_KEY or "")
    app.state.job_queue = InMemoryJobQueue(_process_consultation_job)
    app.state.job_queue.start()
    yield
    app.state.job_queue.stop()


app = FastAPI(
    title="Liver RAG Agent",
    version="1.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse, tags=["meta"])
def root() -> HTMLResponse:
    return HTMLResponse(WEB_INDEX_PATH.read_text(encoding="utf-8"))


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        agent_ready=True,
        default_image_path_configured=bool((config.DEFAULT_DICOM_DIR or "").strip()),
    )


@app.post(
    "/v1/consult",
    response_model=ConsultResponse,
    tags=["agent"],
    dependencies=[Depends(_optional_service_auth)],
)
def consult(
    body: ConsultRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ConsultResponse:
    session_id = (body.session_id or "").strip() or str(uuid.uuid4())
    image_path = (body.image_path or "").strip() or (config.DEFAULT_DICOM_DIR or "").strip() or None

    return _run_consultation(
        agent=app.state.agent,
        db=db,
        job_id=None,
        session_id=session_id,
        query=body.query,
        image_path=image_path,
        reviewer_enabled=body.reviewer_enabled,
    )


@app.post(
    "/v1/dispatch",
    response_model=DispatchResponse,
    tags=["agent"],
    dependencies=[Depends(_optional_service_auth)],
)
def dispatch_consult(
    body: ConsultRequest,
    db: Annotated[Session, Depends(get_db)],
    dispatch_mode: str = Query(default="auto", description="Dispatch mode: auto, sync, or async."),
) -> DispatchResponse:
    return _execute_dispatch(
        db=db,
        query=body.query,
        session_id=body.session_id,
        image_path=body.image_path,
        reviewer_enabled=body.reviewer_enabled,
        requested_mode=_normalize_dispatch_mode(dispatch_mode),
        upload_present=False,
    )


@app.post(
    "/v1/consult/upload",
    response_model=ConsultResponse,
    tags=["agent"],
    dependencies=[Depends(_optional_service_auth)],
)
async def consult_upload(
    db: Annotated[Session, Depends(get_db)],
    query: str = Form(...),
    reviewer_enabled: bool = Form(default=True),
    session_id: Optional[str] = Form(default=None),
    image_file: UploadFile = File(...),
) -> ConsultResponse:
    filename = (image_file.filename or "").lower()
    if not filename.endswith(".nii.gz"):
        raise HTTPException(status_code=400, detail="Only .nii.gz uploads are supported.")

    active_session_id = (session_id or "").strip() or str(uuid.uuid4())
    session_root = Path(config.UPLOADS_DIR) / active_session_id
    if session_root.exists():
        shutil.rmtree(session_root)
    session_root.mkdir(parents=True, exist_ok=True)

    try:
        temp_file_path = session_root / "incoming.nii.gz"
        content_hash = _write_upload_and_hash(image_file, temp_file_path)
        cache_dir, cached_file_path = _resolve_cache_paths(content_hash)
        cache_hit = cached_file_path.exists() and cached_file_path.is_file()

        if not cache_hit:
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_file_path), str(cached_file_path))
        else:
            temp_file_path.unlink(missing_ok=True)

        image_path = str(cached_file_path)
        consult_response = _run_consultation(
            agent=app.state.agent,
            db=db,
            job_id=None,
            session_id=active_session_id,
            query=query,
            image_path=image_path,
            reviewer_enabled=reviewer_enabled,
        )
        warnings = list(consult_response.warnings)
        if cache_hit:
            warnings.append(f"Upload cache hit: reused cached NIfTI file for sha256={content_hash[:12]}.")
        else:
            warnings.append(f"Upload cache miss: stored NIfTI file for sha256={content_hash[:12]}.")
        return consult_response.model_copy(update={"warnings": warnings})
    finally:
        await image_file.close()
        shutil.rmtree(session_root, ignore_errors=True)


@app.post(
    "/v1/dispatch/upload",
    response_model=DispatchResponse,
    tags=["agent"],
    dependencies=[Depends(_optional_service_auth)],
)
async def dispatch_upload(
    db: Annotated[Session, Depends(get_db)],
    query: str = Form(...),
    reviewer_enabled: bool = Form(default=True),
    session_id: Optional[str] = Form(default=None),
    dispatch_mode: str = Form(default="auto"),
    image_file: UploadFile = File(...),
) -> DispatchResponse:
    filename = (image_file.filename or "").lower()
    if not filename.endswith(".nii.gz"):
        raise HTTPException(status_code=400, detail="Only .nii.gz uploads are supported.")

    active_session_id = (session_id or "").strip() or str(uuid.uuid4())
    session_root = Path(config.UPLOADS_DIR) / active_session_id
    if session_root.exists():
        shutil.rmtree(session_root)
    session_root.mkdir(parents=True, exist_ok=True)

    try:
        temp_file_path = session_root / "incoming.nii.gz"
        content_hash = _write_upload_and_hash(image_file, temp_file_path)
        cache_dir, cached_file_path = _resolve_cache_paths(content_hash)
        cache_hit = cached_file_path.exists() and cached_file_path.is_file()

        if not cache_hit:
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_file_path), str(cached_file_path))
        else:
            temp_file_path.unlink(missing_ok=True)

        extra_warnings = [
            (
                f"Upload cache hit: reused cached NIfTI file for sha256={content_hash[:12]}."
                if cache_hit
                else f"Upload cache miss: stored NIfTI file for sha256={content_hash[:12]}."
            )
        ]
        return _execute_dispatch(
            db=db,
            query=query,
            session_id=active_session_id,
            image_path=str(cached_file_path),
            reviewer_enabled=reviewer_enabled,
            requested_mode=_normalize_dispatch_mode(dispatch_mode),
            upload_present=True,
            extra_warnings=extra_warnings,
        )
    finally:
        await image_file.close()
        shutil.rmtree(session_root, ignore_errors=True)


@app.post(
    "/v1/jobs",
    response_model=JobSubmitResponse,
    status_code=202,
    tags=["jobs"],
    dependencies=[Depends(_optional_service_auth)],
)
def submit_consult_job(
    body: ConsultRequest,
    db: Annotated[Session, Depends(get_db)],
) -> JobSubmitResponse:
    session_id = (body.session_id or "").strip() or str(uuid.uuid4())
    image_path = (body.image_path or "").strip() or (config.DEFAULT_DICOM_DIR or "").strip() or None
    return _submit_job_record(
        db=db,
        session_id=session_id,
        query=body.query,
        image_path=image_path,
        reviewer_enabled=body.reviewer_enabled,
    )


@app.post(
    "/v1/jobs/upload",
    response_model=JobSubmitResponse,
    status_code=202,
    tags=["jobs"],
    dependencies=[Depends(_optional_service_auth)],
)
async def submit_upload_job(
    db: Annotated[Session, Depends(get_db)],
    query: str = Form(...),
    reviewer_enabled: bool = Form(default=True),
    session_id: Optional[str] = Form(default=None),
    image_file: UploadFile = File(...),
) -> JobSubmitResponse:
    filename = (image_file.filename or "").lower()
    if not filename.endswith(".nii.gz"):
        raise HTTPException(status_code=400, detail="Only .nii.gz uploads are supported.")

    active_session_id = (session_id or "").strip() or str(uuid.uuid4())
    session_root = Path(config.UPLOADS_DIR) / active_session_id
    if session_root.exists():
        shutil.rmtree(session_root)
    session_root.mkdir(parents=True, exist_ok=True)

    try:
        temp_file_path = session_root / "incoming.nii.gz"
        content_hash = _write_upload_and_hash(image_file, temp_file_path)
        cache_dir, cached_file_path = _resolve_cache_paths(content_hash)
        cache_hit = cached_file_path.exists() and cached_file_path.is_file()

        if not cache_hit:
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_file_path), str(cached_file_path))
        else:
            temp_file_path.unlink(missing_ok=True)

        warnings = [
            (
                f"Upload cache hit: reused cached NIfTI file for sha256={content_hash[:12]}."
                if cache_hit
                else f"Upload cache miss: stored NIfTI file for sha256={content_hash[:12]}."
            )
        ]
        return _submit_job_record(
            db=db,
            session_id=active_session_id,
            query=query,
            image_path=str(cached_file_path),
            reviewer_enabled=reviewer_enabled,
            warnings=warnings,
        )
    finally:
        await image_file.close()
        shutil.rmtree(session_root, ignore_errors=True)


@app.get(
    "/v1/jobs/{job_id}",
    response_model=JobStatusResponse,
    tags=["jobs"],
    dependencies=[Depends(_optional_service_auth)],
)
def get_job_status(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> JobStatusResponse:
    cached = redis_store.get_job_status(job_id)
    if cached is not None:
        return JobStatusResponse.model_validate(cached)
    row = db.get(ConsultationJobRecord, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Consultation job not found.")
    snapshot = _build_job_status_response(row)
    _cache_job_status_snapshot(snapshot)
    return snapshot


@app.get(
    "/v1/jobs/{job_id}/events",
    tags=["jobs"],
    dependencies=[Depends(_optional_service_auth)],
)
async def stream_job_events(job_id: str):
    async def wrapped_generator():
        subscriber = job_event_bus.subscribe(job_id)
        try:
            last_snapshot: Optional[str] = None
            while True:
                db = SessionLocal()
                try:
                    row = db.get(ConsultationJobRecord, job_id)
                    if row is None:
                        yield _serialize_sse("error", {"job_id": job_id, "message": "Consultation job not found."})
                        return
                    snapshot = _build_job_status_response(row)
                    _cache_job_status_snapshot(snapshot)
                    snapshot_json = snapshot.model_dump_json()
                    if snapshot_json != last_snapshot:
                        event_name = "job_completed" if snapshot.status == "completed" else "job_failed" if snapshot.status == "failed" else "job_update"
                        yield _serialize_sse(event_name, snapshot.model_dump(mode="json"))
                        last_snapshot = snapshot_json
                finally:
                    db.close()

                while not subscriber.empty():
                    live_event = subscriber.get_nowait()
                    yield _serialize_sse(live_event.event, live_event.data)

                if snapshot.status in {"completed", "failed"}:
                    return
                yield ": keep-alive\n\n"
                await asyncio.sleep(1.0)
        finally:
            job_event_bus.unsubscribe(job_id, subscriber)

    return StreamingResponse(wrapped_generator(), media_type="text/event-stream")


@app.get(
    "/v1/consultations",
    response_model=list[ConsultationSummary],
    tags=["history"],
    dependencies=[Depends(_optional_service_auth)],
)
def list_consultations(
    db: Annotated[Session, Depends(get_db)],
    session_id: Optional[str] = Query(default=None, description="Filter by session ID."),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ConsultationSummary]:
    q = db.query(ConsultationRecord).order_by(ConsultationRecord.created_at.desc())
    if session_id:
        q = q.filter(ConsultationRecord.session_id == session_id)
    rows = q.limit(limit).all()
    out: list[ConsultationSummary] = []
    for r in rows:
        preview = r.report if len(r.report) <= 400 else r.report[:400] + "..."
        out.append(
            ConsultationSummary(
                id=r.id,
                session_id=r.session_id,
                query=r.query,
                report_preview=preview,
                image_path=r.image_path,
                has_preview=r.has_preview,
                created_at=r.created_at,
            )
        )
    return out


@app.get("/v1/consultations/{consultation_id}", tags=["history"], dependencies=[Depends(_optional_service_auth)])
def get_consultation(
    consultation_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = db.get(ConsultationRecord, consultation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Consultation record not found.")
    return {
        "id": row.id,
        "session_id": row.session_id,
        "query": row.query,
        "report": row.report,
        "image_path": row.image_path,
        "has_preview": row.has_preview,
        "created_at": row.created_at.isoformat(),
    }

