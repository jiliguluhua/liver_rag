import operator
from typing import Annotated, Any, Literal, Optional, TypedDict


IntentType = Literal["clinical", "education", "unrelated"]
WorkflowStatus = Literal["pending", "running", "completed", "failed"]
PerceptionStatus = Literal[
    "not_requested",
    "pending",
    "completed",
    "failed",
    "skipped",
    "placeholder",
]
ReviewStatus = Literal["not_run", "passed", "failed", "skipped"]
NodeStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class EvidenceItem(TypedDict, total=False):
    source: str
    title: str
    snippet: str
    score: float
    metadata: dict[str, Any]


class TraceEvent(TypedDict, total=False):
    node: str
    status: NodeStatus
    message: str
    duration_ms: float
    error: str
    metadata: dict[str, Any]


class StructuredReport(TypedDict, total=False):
    summary: str
    clinical_answer: str
    next_step: str
    limitations: list[str]
    risk_flags: list[str]
    evidence: list[EvidenceItem]


class AgentState(TypedDict, total=False):
    # Request context
    session_id: str
    query: str
    image_path: Optional[str]
    user_context: dict[str, Any]

    # Workflow routing
    workflow_status: WorkflowStatus
    intent: IntentType
    should_retrieve: bool
    should_perceive: bool
    reviewer_enabled: bool

    # Perception branch
    perception_status: PerceptionStatus
    perception_data: str
    perception_payload: dict[str, Any]

    # Retrieval branch
    retrieved_docs: list[Any]
    evidence: list[EvidenceItem]

    # Reporting branch
    report: str
    structured_report: StructuredReport

    # Review branch
    review_status: ReviewStatus
    review_feedback: str
    is_medical_valid: bool

    # Observability and resilience
    trace: Annotated[list[TraceEvent], operator.add]
    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    metrics: dict[str, float]
    debug: dict[str, Any]


def create_initial_state(
    query: str,
    image_path: Optional[str] = None,
    session_id: str = "",
    reviewer_enabled: bool = True,
) -> AgentState:
    return {
        "session_id": session_id,
        "query": query,
        "image_path": image_path,
        "user_context": {},
        "workflow_status": "pending",
        "should_retrieve": True,
        "should_perceive": False,
        "reviewer_enabled": reviewer_enabled,
        "perception_status": "not_requested",
        "perception_data": "",
        "perception_payload": {},
        "retrieved_docs": [],
        "evidence": [],
        "report": "",
        "structured_report": {
            "summary": "",
            "clinical_answer": "",
            "next_step": "",
            "limitations": [],
            "risk_flags": [],
            "evidence": [],
        },
        "review_status": "not_run",
        "review_feedback": "",
        "is_medical_valid": False,
        "trace": [],
        "warnings": [],
        "errors": [],
        "metrics": {},
        "debug": {},
    }

