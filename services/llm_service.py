from __future__ import annotations

import json
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from core import config


_report_llm: Optional[ChatOpenAI] = None


def llm_enabled() -> bool:
    return bool((config.LLM_API_KEY or "").strip())


def _get_report_llm() -> ChatOpenAI:
    global _report_llm
    if _report_llm is None:
        _report_llm = ChatOpenAI(
            model=config.LLM_MODEL_NAME,
            openai_api_key=config.LLM_API_KEY,
            openai_api_base=config.LLM_BASE_URL,
            temperature=0.2,
        )
    return _report_llm


def generate_learning_session_report_payload(
    *,
    session_id: str,
    procedure: str | None,
    turns: list[dict[str, Any]],
    covered_topics: list[str],
    weak_topics: list[str],
    recommended_next_topics: list[str],
    recommended_items: list[dict[str, Any]],
) -> dict[str, Any]:
    if not llm_enabled():
        raise RuntimeError("LLM is not enabled.")

    prompt = f"""
You are generating a concise learning session report for a hepatobiliary surgery education system.

Return valid JSON with this shape:
{{
  "summary": "short summary",
  "covered_topics": ["topic1"],
  "weak_topics": ["topic2"],
  "recommended_next_topics": ["topic3"]
}}

Session ID: {session_id}
Procedure: {procedure or "unknown"}
Turns: {json.dumps(turns, ensure_ascii=False)}
Current covered topics: {json.dumps(covered_topics, ensure_ascii=False)}
Current weak topics: {json.dumps(weak_topics, ensure_ascii=False)}
Current recommended next topics: {json.dumps(recommended_next_topics, ensure_ascii=False)}
Recommended materials: {json.dumps(recommended_items, ensure_ascii=False)}
"""
    raw = _get_report_llm().invoke(prompt).content.strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM learning session report is not a JSON object.")
    return data
