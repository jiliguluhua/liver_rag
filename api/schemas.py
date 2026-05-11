from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConsultRequest(BaseModel):
    query: str = Field(..., min_length=1, description="用户临床问题")
    image_path: str | None = Field(
        default=None,
        description="DICOM 序列目录；缺省时使用服务端配置的 LIVER_DEFAULT_DICOM_DIR",
    )
    session_id: str | None = Field(
        default=None,
        description="可选会话 ID，用于关联历史记录",
    )


class ConsultResponse(BaseModel):
    report: str
    preview_image_base64: str | None = None
    consultation_id: int
    session_id: str


class ConsultationSummary(BaseModel):
    id: int
    session_id: str
    query: str
    report_preview: str
    image_path: str | None
    has_preview: bool
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    agent_ready: bool
    default_image_path_configured: bool
