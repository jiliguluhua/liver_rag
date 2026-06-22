from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from api.schemas import ProfileAnalysisResponse
from services.topic_parser import infer_procedure_and_topics

_LEVEL_KEYWORDS = {
    "advanced": ["advanced", "complex", "complication", "bailout", "进阶", "复杂", "并发症", "补救"],
    "beginner": ["basic", "overview", "anatomy", "step", "基础", "入门", "解剖", "步骤"],
}
_MODALITY_KEYWORDS = {
    "video": ["video", "录像", "视频"],
    "image": ["image", "atlas", "图谱", "影像"],
    "text": ["guideline", "review", "paper", "指南", "综述", "文献"],
}
_GOAL_KEYWORDS = {
    "operative mastery": ["step", "technique", "procedure", "术式", "步骤", "操作"],
    "risk reduction": ["risk", "injury", "complication", "风险", "损伤", "并发症"],
    "knowledge overview": ["overview", "background", "review", "基础", "背景", "综述"],
}


def _first_match(text: str, mapping: dict[str, list[str]]) -> Optional[str]:
    normalized = text.lower()
    for label, keywords in mapping.items():
        if any(keyword in normalized for keyword in keywords):
            return label
    return None


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def build_profile_analysis(
    *,
    session_id: str,
    turns: list[dict[str, Any]],
    user_id: Optional[int] = None,
) -> ProfileAnalysisResponse:
    queries = [str(turn.get("query", "")).strip() for turn in turns if str(turn.get("query", "")).strip()]
    joined_text = " ".join(
        f"{str(turn.get('query', ''))} {str(turn.get('report', ''))}"
        for turn in turns
    ).strip()

    procedure_counter: Counter[str] = Counter()
    topic_counter: Counter[str] = Counter()
    modality_counter: Counter[str] = Counter()
    goal_counter: Counter[str] = Counter()
    advanced_hits = 0
    beginner_hits = 0

    for turn in turns:
        text = f"{str(turn.get('query', ''))} {str(turn.get('report', ''))}"
        procedure, topics = infer_procedure_and_topics(text)
        if procedure:
            procedure_counter[procedure] += 1
        for topic in topics:
            topic_counter[topic] += 1
        modality = _first_match(text, _MODALITY_KEYWORDS)
        if modality:
            modality_counter[modality] += 1
        goal = _first_match(text, _GOAL_KEYWORDS)
        if goal:
            goal_counter[goal] += 1
        level_signal = _first_match(text, _LEVEL_KEYWORDS)
        if level_signal == "advanced":
            advanced_hits += 1
        elif level_signal == "beginner":
            beginner_hits += 1

    preferred_procedures = [item for item, _count in procedure_counter.most_common(3)]
    preferred_topics = [item for item, _count in topic_counter.most_common(4)]
    preferred_modalities = [item for item, _count in modality_counter.most_common(3)] or ["text"]
    learning_goal = goal_counter.most_common(1)[0][0] if goal_counter else "knowledge overview"
    level = "advanced" if advanced_hits > beginner_hits else "beginner"
    recent_focus = _dedupe_keep_order(preferred_topics + preferred_procedures)[:4]

    if preferred_procedures:
        role = "hepatobiliary learner"
    else:
        role = "general medical learner"

    label = f"session-{session_id}"
    if user_id is not None:
        label = f"user-{user_id}"

    if not queries:
        summary = "当前 session 还没有足够的提问记录，暂时只能判断这是一个刚开始的学习会话。"
    else:
        summary = (
            f"{label} 近期主要围绕 {', '.join(preferred_procedures or ['general hepatobiliary topics'])} 提问，"
            f"关注重点是 {', '.join(preferred_topics or ['disease_background'])}。"
            f"从提问方式看，当前更偏向 {level} 阶段，材料偏好更像 {', '.join(preferred_modalities)}，"
            f"当前学习目标更接近 {learning_goal}。"
        )

    return ProfileAnalysisResponse(
        session_id=session_id,
        inferred_user_label=label,
        role=role,
        level=level,
        preferred_procedures=preferred_procedures,
        preferred_topics=preferred_topics,
        preferred_modalities=preferred_modalities,
        learning_goal=learning_goal,
        recent_focus=recent_focus,
        evidence_queries=queries[-5:],
        profile_summary=summary,
    )
