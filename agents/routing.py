from __future__ import annotations

from typing import Optional

import core.config as config
from agents.state import RoutingDecision
from langchain_openai import ChatOpenAI


_logic_llm: Optional[ChatOpenAI] = None


def _get_logic_llm() -> ChatOpenAI:
    global _logic_llm
    if _logic_llm is None:
        _logic_llm = ChatOpenAI(
            model=config.LLM_MODEL_NAME,
            openai_api_key=config.LLM_API_KEY,
            openai_api_base=config.LLM_BASE_URL,
            temperature=0,
        )
    return _logic_llm


def analyze_intent_routing(query: str, image_path: Optional[str]) -> RoutingDecision:
    normalized_query = (query or "").strip()
    normalized_image_path = (image_path or "").strip()

    if not config.LLM_API_KEY:
        return {
            "intent": "clinical",
            "should_retrieve": True,
            "should_perceive": bool(normalized_image_path),
            "routing_mode": "fallback",
            "warnings": ["LLM_API_KEY is not configured; intent classification fell back to rule-based defaults."],
            "errors": [],
        }

    prompt = f"""
Classify the following user request into one of these labels only:
- clinical: diagnosis, treatment, prognosis, or patient-specific medical decision support
- education: general medical education, concept explanation, or literature-style overview
- unrelated: not medically relevant

Then decide whether retrieval is needed and whether image perception is needed.

User query: {normalized_query}
Image path provided: {"yes" if normalized_image_path else "no"}

Return exactly one line using this format:
intent=<clinical|education|unrelated>;retrieve=<yes|no>;perceive=<yes|no>
"""
    try:
        res = _get_logic_llm().invoke(prompt)
        raw = res.content.strip().lower()
        parsed = {
            "intent": "clinical",
            "retrieve": "yes",
            "perceive": "yes" if normalized_image_path else "no",
        }
        for part in raw.split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            parsed[key.strip()] = value.strip()

        intent = parsed["intent"]
        if intent not in {"clinical", "education", "unrelated"}:
            intent = "clinical"

        should_retrieve = parsed.get("retrieve", "yes") == "yes"
        should_perceive = parsed.get("perceive", "no") == "yes" and bool(normalized_image_path)
        return {
            "intent": intent,
            "should_retrieve": should_retrieve,
            "should_perceive": should_perceive,
            "routing_mode": "llm",
            "warnings": [],
            "errors": [],
        }
    except Exception as exc:
        return {
            "intent": "clinical",
            "should_retrieve": True,
            "should_perceive": bool(normalized_image_path),
            "routing_mode": "fallback",
            "warnings": [f"Intent analysis failed and used fallback routing: {exc}"],
            "errors": [f"intent_analyzer_error: {exc}"],
        }
