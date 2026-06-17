from __future__ import annotations

from typing import Any

from api.schemas import LearningSessionReportResponse
from services.llm_service import generate_learning_session_report_payload, llm_enabled
from services.recommendation_service import build_recommendation_items
from services.topic_parser import infer_procedure_and_topics


def build_learning_session_report(
    *,
    session_id: str,
    context: dict[str, Any],
) -> LearningSessionReportResponse:
    turns = context.get("recent_turns", [])
    joined_text = " ".join(f"{turn.get('query', '')} {turn.get('report', '')}" for turn in turns)
    procedure, covered_topics = infer_procedure_and_topics(joined_text)
    unique_topics = list(dict.fromkeys(covered_topics))
    recommended_next_topics = [topic for topic in ["anatomy", "risk_points", "complications", "bailout_strategy"] if topic not in unique_topics][:3]
    weak_topics = recommended_next_topics[:2]
    recommended_items = build_recommendation_items(
        query=joined_text or session_id,
        procedure=procedure,
        topics=recommended_next_topics or unique_topics,
        scene="learning",
    )

    summary = (
        f"Session {session_id} focused on {procedure or 'general hepatobiliary learning'}. "
        f"Covered topics: {', '.join(unique_topics) if unique_topics else 'none captured yet'}. "
        f"Suggested next topics: {', '.join(recommended_next_topics) if recommended_next_topics else 'continue deepening current topics'}."
    )

    if llm_enabled():
        try:
            payload = generate_learning_session_report_payload(
                session_id=session_id,
                procedure=procedure,
                turns=turns,
                covered_topics=unique_topics,
                weak_topics=weak_topics,
                recommended_next_topics=recommended_next_topics,
                recommended_items=[item.model_dump() for item in recommended_items],
            )
            summary = str(payload.get("summary", summary))
            unique_topics = [str(item) for item in payload.get("covered_topics", unique_topics)]
            weak_topics = [str(item) for item in payload.get("weak_topics", weak_topics)]
            recommended_next_topics = [str(item) for item in payload.get("recommended_next_topics", recommended_next_topics)]
        except Exception:
            pass

    return LearningSessionReportResponse(
        session_id=session_id,
        procedure=procedure,
        covered_topics=unique_topics,
        weak_topics=weak_topics,
        recommended_next_topics=recommended_next_topics,
        recommended_next_materials=recommended_items,
        summary=summary,
    )
