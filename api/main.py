from __future__ import annotations

import base64
import io
import os
import shutil
import uuid
import zipfile
from contextlib import asynccontextmanager
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


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zip_file:
        for member in zip_file.infolist():
            member_path = target_dir / member.filename
            resolved_target = member_path.resolve()
            if target_dir.resolve() not in resolved_target.parents and resolved_target != target_dir.resolve():
                raise HTTPException(status_code=400, detail="Unsafe zip archive path detected.")
        zip_file.extractall(target_dir)


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
    dicom_zip: UploadFile = File(...),
) -> ConsultResponse:
    if not dicom_zip.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads are supported for DICOM series.")

    active_session_id = (session_id or "").strip() or str(uuid.uuid4())
    upload_root = Path(config.UPLOADS_DIR) / active_session_id
    archive_path = upload_root / dicom_zip.filename
    extract_dir = upload_root / "extracted"

    if upload_root.exists():
        shutil.rmtree(upload_root)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with archive_path.open("wb") as f:
            shutil.copyfileobj(dicom_zip.file, f)

        _safe_extract_zip(archive_path, extract_dir)

        extracted_items = [p for p in extract_dir.iterdir()]
        if not extracted_items:
            raise HTTPException(status_code=400, detail="Uploaded zip archive is empty.")

        image_path = str(extract_dir)
        agent: LiverSmartAgent = app.state.agent
        report, preview_img, final_state = agent.run(
            image_path,
            query,
            session_id=active_session_id,
            reviewer_enabled=reviewer_enabled,
        )

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
        await dicom_zip.close()


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
