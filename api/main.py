from __future__ import annotations

import base64
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
from fastapi.responses import HTMLResponse
from PIL import Image
from sqlalchemy.orm import Session

from api.schemas import ConsultRequest, ConsultResponse, ConsultationSummary, HealthResponse
from core import config
from core.database import get_db, init_db
from core.models import ConsultationRecord
from services.medical_agent import LiverSmartAgent


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _cleanup_expired_upload_cache(Path(config.UPLOAD_CACHE_DIR))
    app.state.agent = LiverSmartAgent(api_key=config.LLM_API_KEY or "")
    yield


app = FastAPI(
    title="Liver RAG Agent API",
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

    agent: LiverSmartAgent = app.state.agent
    report, preview_img, final_state = agent.run(
        image_path,
        body.query,
        session_id=session_id,
        reviewer_enabled=body.reviewer_enabled,
    )

    row = _save_consultation(
        db,
        session_id=session_id,
        query=body.query,
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
        agent: LiverSmartAgent = app.state.agent
        report, preview_img, final_state = agent.run(
            image_path,
            query,
            session_id=active_session_id,
            reviewer_enabled=reviewer_enabled,
        )
        warnings = list(final_state.get("warnings", []))
        if cache_hit:
            warnings.append(f"Upload cache hit: reused cached NIfTI file for sha256={content_hash[:12]}.")
        else:
            warnings.append(f"Upload cache miss: stored NIfTI file for sha256={content_hash[:12]}.")
        final_state["warnings"] = warnings

        row = _save_consultation(
            db,
            session_id=active_session_id,
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
    finally:
        await image_file.close()
        shutil.rmtree(session_root, ignore_errors=True)


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
