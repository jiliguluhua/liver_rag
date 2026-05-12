from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ConsultRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User clinical or educational query.")
    image_path: Optional[str] = Field(
        default=None,
        description="Optional DICOM series directory. When omitted, the workflow can still run in text-only mode.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session identifier used to associate consultation history.",
    )
    reviewer_enabled: bool = Field(
        default=True,
        description="Whether to run the reviewer node after report generation.",
    )


class ConsultResponse(BaseModel):
    report: str
    preview_image_base64: Optional[str] = None
    consultation_id: int
    session_id: str
    status: str
    intent: Optional[str] = None
    perception_status: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)


class ConsultationSummary(BaseModel):
    id: int
    session_id: str
    query: str
    report_preview: str
    image_path: Optional[str]
    has_preview: bool
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    agent_ready: bool
    default_image_path_configured: bool
