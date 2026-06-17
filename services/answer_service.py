from __future__ import annotations

from api.schemas import AnswerResponse, ConsultResponse
from services.topic_parser import infer_procedure_and_topics


def build_answer_response(consult_response: ConsultResponse, *, query: str) -> AnswerResponse:
    _procedure, topics = infer_procedure_and_topics(query)
    return AnswerResponse(
        answer=consult_response.report,
        consultation_id=consult_response.consultation_id,
        session_id=consult_response.session_id,
        status=consult_response.status,
        intent=consult_response.intent,
        perception_status=consult_response.perception_status,
        evidence=consult_response.evidence,
        related_topics=topics,
        warnings=consult_response.warnings,
        errors=consult_response.errors,
        trace=consult_response.trace,
    )
