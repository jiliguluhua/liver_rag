from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from api.schemas import RecommendationItem, RecommendResponse
from core.models import RecommendationLogRecord
from services.learning_service import upsert_learning_session
from services.topic_parser import infer_procedure_and_topics


def build_recommendation_items(
    *,
    query: str,
    procedure: Optional[str],
    topics: list[str],
    scene: Optional[str],
) -> list[RecommendationItem]:
    active_scene = scene or "learning"
    items: list[RecommendationItem] = []
    source_map = {
        "anatomy": ("reference", "image"),
        "disease_background": ("review", "text"),
        "operative_steps": ("guideline", "text"),
        "risk_points": ("guideline", "text"),
        "complications": ("case", "text"),
        "bailout_strategy": ("case", "video"),
    }
    for topic in topics[:3]:
        source_type, modality = source_map.get(topic, ("review", "text"))
        items.append(
            RecommendationItem(
                title=f"{procedure or 'general'} {topic} for {active_scene}",
                procedure=procedure,
                topic=topic,
                source_type=source_type,
                modality=modality,
                reason=f"Based on query '{query[:40]}' and scene '{active_scene}', this topic is a high-priority next step.",
            )
        )
    return items


def save_recommendation_log(
    db: Session,
    *,
    session_id: str,
    user_id: Optional[int],
    query: str,
    procedure_name: Optional[str],
    topic: Optional[str],
    recommendations: list[RecommendationItem],
) -> None:
    row = RecommendationLogRecord(
        session_id=session_id,
        user_id=user_id,
        query=query,
        procedure_name=procedure_name,
        topic=topic,
        recommendations_json=json.dumps([item.model_dump() for item in recommendations], ensure_ascii=False),
    )
    db.add(row)
    db.commit()


def build_recommend_response(
    db: Session,
    *,
    query: str,
    session_id: str,
    user_id: Optional[int],
    procedure: Optional[str],
    scene: Optional[str],
) -> RecommendResponse:
    inferred_procedure, topics = infer_procedure_and_topics(f"{procedure or ''} {query}")
    active_procedure = (procedure or "").strip() or inferred_procedure
    active_scene = (scene or "").strip() or "learning"
    items = build_recommendation_items(
        query=query,
        procedure=active_procedure,
        topics=topics,
        scene=active_scene,
    )
    upsert_learning_session(db, session_id=session_id, procedure_name=active_procedure, scene=active_scene)
    save_recommendation_log(
        db,
        session_id=session_id,
        user_id=user_id,
        query=query,
        procedure_name=active_procedure,
        topic=topics[0] if topics else None,
        recommendations=items,
    )
    return RecommendResponse(
        session_id=session_id,
        procedure=active_procedure,
        scene=active_scene,
        recommended_materials=items,
        topic_grouping={item.topic: [item.title] for item in items},
        recommend_reason="Current recommendation is generated from procedure/topic heuristics and is ready to be replaced by a dedicated Java recommendation service.",
        next_step="Pick one recommended topic and then use Answer for a focused follow-up question.",
    )
