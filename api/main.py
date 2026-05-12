"""
HTTP API for the Liver RAG agent.

Run from repo root:
  uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import base64
import io
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from sqlalchemy.orm import Session

from api.schemas import ConsultRequest, ConsultResponse, ConsultationSummary, HealthResponse
from core import config
from core.database import get_db, init_db
from core.models import ConsultationRecord
from services.medical_agent import LiverSmartAgent


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.agent = LiverSmartAgent(api_key=config.LLM_API_KEY or "")
    yield


app = FastAPI(
    title="Liver RAG Agent API",
    version="1.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

    preview_b64 = _pil_to_png_b64(preview_img) if preview_img is not None else None

    row = ConsultationRecord(
        session_id=session_id,
        query=body.query,
        report=report,
        image_path=image_path,
        has_preview=preview_img is not None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return ConsultResponse(
        report=report,
        preview_image_base64=preview_b64,
        consultation_id=row.id,
        session_id=session_id,
        status=final_state.get("workflow_status", "completed"),
        intent=final_state.get("intent"),
        perception_status=final_state.get("perception_status"),
        warnings=list(final_state.get("warnings", [])),
        errors=list(final_state.get("errors", [])),
        evidence=list(final_state.get("evidence", [])),
        trace=list(final_state.get("trace", [])),
    )


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
