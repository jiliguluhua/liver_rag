from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

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


JobStatus = Literal["queued", "running", "completed", "failed"]
DispatchMode = Literal["auto", "sync", "async"]


class JobSubmitResponse(BaseModel):
    job_id: str
    session_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    session_id: str
    status: JobStatus
    query: str
    image_path: Optional[str] = None
    reviewer_enabled: bool
    consultation_id: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[ConsultResponse] = None


class DispatchDecision(BaseModel):
    mode: DispatchMode
    reason: str
    should_retrieve: bool
    should_perceive: bool
    intent_hint: str


class DispatchResponse(BaseModel):
    mode: DispatchMode
    decision: DispatchDecision
    result: Optional[ConsultResponse] = None
    job: Optional[JobSubmitResponse] = None


class ReportResponse(DispatchResponse):
    pass


class CollectResponse(BaseModel):
    session_id: str
    assistant_message: str
    follow_up_questions: list[str] = Field(default_factory=list)
    can_generate_report: bool
    readiness_mode: str = "rule_based"
    readiness_reasons: list[str] = Field(default_factory=list)
    context_turn_count: int = 0
    latest_image_path: Optional[str] = None
    collected_context: dict[str, Any] = Field(default_factory=dict)


class AnswerRequest(ConsultRequest):
    pass


class AnswerResponse(BaseModel):
    answer: str
    consultation_id: int
    session_id: str
    status: str
    intent: Optional[str] = None
    perception_status: Optional[str] = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default=None)
    user_id: Optional[int] = Field(default=None)
    procedure: Optional[str] = Field(default=None)
    scene: Optional[str] = Field(default=None)


class RecommendationItem(BaseModel):
    title: str
    procedure: Optional[str] = None
    topic: str
    source_type: str
    modality: str
    reason: str


class RecommendResponse(BaseModel):
    session_id: str
    procedure: Optional[str] = None
    scene: Optional[str] = None
    recommended_materials: list[RecommendationItem] = Field(default_factory=list)
    topic_grouping: dict[str, list[str]] = Field(default_factory=dict)
    recommend_reason: str
    next_step: str


class LearningSessionReportRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: Optional[int] = Field(default=None)


class ProfileAnalysisRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_id: Optional[int] = Field(default=None)
    max_turns: int = Field(default=10, ge=1, le=50)


class ProfileAnalysisResponse(BaseModel):
    session_id: str
    inferred_user_label: str
    role: Optional[str] = None
    level: str
    preferred_procedures: list[str] = Field(default_factory=list)
    preferred_topics: list[str] = Field(default_factory=list)
    preferred_modalities: list[str] = Field(default_factory=list)
    learning_goal: str
    recent_focus: list[str] = Field(default_factory=list)
    evidence_queries: list[str] = Field(default_factory=list)
    profile_summary: str


class LearningSessionReportResponse(BaseModel):
    session_id: str
    procedure: Optional[str] = None
    covered_topics: list[str] = Field(default_factory=list)
    weak_topics: list[str] = Field(default_factory=list)
    recommended_next_topics: list[str] = Field(default_factory=list)
    recommended_next_materials: list[RecommendationItem] = Field(default_factory=list)
    summary: str
