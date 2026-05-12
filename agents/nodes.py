import os
import time
from typing import Any, Dict, Optional

import core.config as config
from agents.state import AgentState, EvidenceItem, TraceEvent
from langchain_openai import ChatOpenAI
from perception.perception import MedicalPerception
from rag.hybrid_searcher import MedicalHybridSearcher


_logic_llm: Optional[ChatOpenAI] = None
_report_llm: Optional[ChatOpenAI] = None
_searcher: Optional[MedicalHybridSearcher] = None
_perception_engine: Optional[MedicalPerception] = None


def _trace(
    node: str,
    status: str,
    message: str,
    *,
    start_time: Optional[float] = None,
    error: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> TraceEvent:
    event: TraceEvent = {
        "node": node,
        "status": status,
        "message": message,
    }
    if start_time is not None:
        event["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
    if error:
        event["error"] = error
    if metadata:
        event["metadata"] = metadata
    return event


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


def _get_report_llm() -> ChatOpenAI:
    global _report_llm
    if _report_llm is None:
        _report_llm = ChatOpenAI(
            model=config.LLM_MODEL_NAME,
            openai_api_key=config.LLM_API_KEY,
            openai_api_base=config.LLM_BASE_URL,
            temperature=0.3,
        )
    return _report_llm


def _get_searcher() -> MedicalHybridSearcher:
    global _searcher
    if _searcher is None:
        _searcher = MedicalHybridSearcher()
    return _searcher


def _get_perception_engine() -> MedicalPerception:
    global _perception_engine
    if _perception_engine is None:
        _perception_engine = MedicalPerception(
            config.PERCEPTION_MODEL_PATH,
            config.PERCEPTION_META_PATH,
        )
    return _perception_engine


def _format_evidence(docs: list[Any]) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for doc in docs:
        metadata = getattr(doc, "metadata", {}) or {}
        evidence.append(
            {
                "source": str(metadata.get("source", "unknown")),
                "title": str(metadata.get("title", metadata.get("file_name", "Untitled"))),
                "snippet": getattr(doc, "page_content", "")[:300],
                "metadata": metadata,
            }
        )
    return evidence


def _build_structured_report(state: AgentState, report_text: str) -> dict[str, Any]:
    limitations = list(state.get("warnings", []))
    if state.get("perception_status") in {"failed", "placeholder", "skipped"}:
        limitations.append("Perception module did not provide a validated tumor segmentation result.")
    if not state.get("evidence"):
        limitations.append("No supporting retrieval evidence was attached to this answer.")

    return {
        "summary": report_text[:240],
        "clinical_answer": report_text,
        "next_step": "Review cited evidence and validate against a clinician before use.",
        "limitations": limitations,
        "risk_flags": list(state.get("errors", [])),
        "evidence": list(state.get("evidence", [])),
    }


def _extract_preview_image(payload: dict[str, Any]) -> Any:
    if not isinstance(payload, dict):
        return None
    return payload.get("preview_img")


def _summarize_input_path(image_path: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "image_path": image_path,
        "exists": os.path.exists(image_path),
    }
    if not image_path or not os.path.exists(image_path):
        return summary

    summary["is_dir"] = os.path.isdir(image_path)
    if os.path.isdir(image_path):
        try:
            entries = sorted(os.listdir(image_path))
            summary["entry_count"] = len(entries)
            summary["sample_entries"] = entries[:10]
        except Exception as exc:
            summary["listdir_error"] = str(exc)
    else:
        try:
            summary["file_size_bytes"] = os.path.getsize(image_path)
        except Exception as exc:
            summary["stat_error"] = str(exc)
    return summary


def intent_analyzer_node(state: AgentState):
    start_time = time.perf_counter()
    query = state["query"]
    image_path = (state.get("image_path") or "").strip()

    if not config.LLM_API_KEY:
        return {
            "intent": "clinical",
            "should_retrieve": True,
            "should_perceive": bool(image_path),
            "workflow_status": "running",
            "warnings": ["LLM_API_KEY is not configured; intent classification fell back to rule-based defaults."],
            "trace": [
                _trace(
                    "analyzer",
                    "completed",
                    "Fell back to default routing because no LLM API key is configured.",
                    start_time=start_time,
                )
            ],
        }

    prompt = f"""
Classify the following user request into one of these labels only:
- clinical: diagnosis, treatment, prognosis, or patient-specific medical decision support
- education: general medical education, concept explanation, or literature-style overview
- unrelated: not medically relevant

Then decide whether retrieval is needed and whether image perception is needed.

User query: {query}
Image path provided: {"yes" if image_path else "no"}

Return exactly one line using this format:
intent=<clinical|education|unrelated>;retrieve=<yes|no>;perceive=<yes|no>
"""
    try:
        res = _get_logic_llm().invoke(prompt)
        raw = res.content.strip().lower()
        parsed = {
            "intent": "clinical",
            "retrieve": "yes",
            "perceive": "yes" if image_path else "no",
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
        should_perceive = parsed.get("perceive", "no") == "yes" and bool(image_path)

        return {
            "intent": intent,
            "should_retrieve": should_retrieve,
            "should_perceive": should_perceive,
            "workflow_status": "running",
            "trace": [
                _trace(
                    "analyzer",
                    "completed",
                    "Intent analysis completed.",
                    start_time=start_time,
                    metadata={
                        "intent": intent,
                        "should_retrieve": should_retrieve,
                        "should_perceive": should_perceive,
                    },
                )
            ],
        }
    except Exception as exc:
        return {
            "intent": "clinical",
            "should_retrieve": True,
            "should_perceive": bool(image_path),
            "workflow_status": "running",
            "warnings": [f"Intent analysis failed and used fallback routing: {exc}"],
            "errors": [f"intent_analyzer_error: {exc}"],
            "trace": [
                _trace(
                    "analyzer",
                    "failed",
                    "Intent analysis failed; fallback routing applied.",
                    start_time=start_time,
                    error=str(exc),
                )
            ],
        }


def retrieve_node(state: AgentState):
    start_time = time.perf_counter()
    if not state.get("should_retrieve", True):
        return {
            "retrieved_docs": [],
            "evidence": [],
            "trace": [
                _trace(
                    "retriever",
                    "skipped",
                    "Retrieval skipped by workflow routing.",
                    start_time=start_time,
                )
            ],
        }

    try:
        docs = _get_searcher().search(state["query"], top_k=config.TOP_K)
        evidence = _format_evidence(docs)
        return {
            "retrieved_docs": docs,
            "evidence": evidence,
            "trace": [
                _trace(
                    "retriever",
                    "completed",
                    "Retrieved supporting documents.",
                    start_time=start_time,
                    metadata={"count": len(docs)},
                )
            ],
        }
    except Exception as exc:
        return {
            "retrieved_docs": [],
            "evidence": [],
            "warnings": [f"Retrieval failed: {exc}"],
            "errors": [f"retrieval_error: {exc}"],
            "trace": [
                _trace(
                    "retriever",
                    "failed",
                    "Retrieval failed; downstream steps can continue without evidence.",
                    start_time=start_time,
                    error=str(exc),
                )
            ],
        }


def perception_node(state: AgentState):
    start_time = time.perf_counter()
    image_path = (state.get("image_path") or "").strip()

    if not state.get("should_perceive"):
        return {
            "perception_status": "skipped",
            "perception_data": "",
            "preview_image": None,
            "trace": [
                _trace(
                    "perceptor",
                    "skipped",
                    "Perception skipped by workflow routing.",
                    start_time=start_time,
                )
            ],
        }

    if not image_path:
        return {
            "perception_status": "skipped",
            "perception_data": "",
            "preview_image": None,
            "warnings": ["Perception requested but no image path was provided."],
            "trace": [
                _trace(
                    "perceptor",
                    "skipped",
                    "Perception skipped because no image path was provided.",
                    start_time=start_time,
                )
            ],
        }

    if not os.path.exists(config.PERCEPTION_MODEL_PATH):
        return {
            "perception_status": "placeholder",
            "perception_data": "Perception module unavailable: validated tumor segmentation weights are not configured.",
            "perception_payload": {},
            "preview_image": None,
            "warnings": ["Perception fell back to placeholder mode because the configured model weights were not found."],
            "trace": [
                _trace(
                    "perceptor",
                    "completed",
                    "Perception entered placeholder mode because model weights are missing.",
                    start_time=start_time,
                    metadata={
                        "model_path": config.PERCEPTION_MODEL_PATH,
                        "input_summary": _summarize_input_path(image_path),
                    },
                )
            ],
        }

    try:
        result = _get_perception_engine().get_tumor_volume(image_path)
        volume_ml = float(result.get("volume", 0.0))
        perception_data = f"Liver-region perception output estimated lesion-related volume at {volume_ml:.2f} mL."
        return {
            "perception_status": "completed",
            "perception_data": perception_data,
            "perception_payload": result,
            "preview_image": _extract_preview_image(result),
            "trace": [
                _trace(
                    "perceptor",
                    "completed",
                    "Perception completed successfully.",
                    start_time=start_time,
                    metadata={
                        "volume_ml": volume_ml,
                        "model_path": config.PERCEPTION_MODEL_PATH,
                        "input_summary": _summarize_input_path(image_path),
                    },
                )
            ],
        }
    except Exception as exc:
        input_summary = _summarize_input_path(image_path)
        return {
            "perception_status": "failed",
            "perception_data": "Perception module failed; report should rely on retrieval evidence only.",
            "perception_payload": {
                "error": str(exc),
                "model_path": config.PERCEPTION_MODEL_PATH,
                "meta_path": config.PERCEPTION_META_PATH,
                "input_summary": input_summary,
            },
            "preview_image": None,
            "warnings": [f"Perception failed and the workflow degraded to retrieval-only mode: {exc}"],
            "errors": [f"perception_error: {exc}"],
            "trace": [
                _trace(
                    "perceptor",
                    "failed",
                    "Perception failed; workflow degraded gracefully.",
                    start_time=start_time,
                    error=str(exc),
                    metadata={
                        "model_path": config.PERCEPTION_MODEL_PATH,
                        "meta_path": config.PERCEPTION_META_PATH,
                        "input_summary": input_summary,
                    },
                )
            ],
        }


def generate_report_node(state: AgentState):
    start_time = time.perf_counter()
    intent = state.get("intent", "clinical")

    if intent == "unrelated":
        report_text = "This system is designed for medical and liver-case-related questions only."
        return {
            "report": report_text,
            "structured_report": _build_structured_report(state, report_text),
            "workflow_status": "completed",
            "review_status": "skipped",
            "trace": [
                _trace(
                    "reporter",
                    "completed",
                    "Returned a guardrail response for an unrelated query.",
                    start_time=start_time,
                )
            ],
        }

    evidence_lines = []
    for idx, item in enumerate(state.get("evidence", []), start=1):
        evidence_lines.append(
            f"[Evidence {idx}] source={item.get('source', 'unknown')} snippet={item.get('snippet', '')}"
        )

    prompt = f"""
You are a careful medical decision-support assistant for liver-related cases.

User intent: {intent}
User query: {state.get("query", "")}
Perception status: {state.get("perception_status", "not_requested")}
Perception summary: {state.get("perception_data", "N/A")}
Review feedback from previous pass: {state.get("review_feedback", "")}

Supporting evidence:
{os.linesep.join(evidence_lines) if evidence_lines else "No retrieval evidence available."}

Write a concise but clinically careful answer with:
1. case summary
2. evidence-based interpretation
3. recommended next step
4. explicit limitations
"""

    if not config.LLM_API_KEY:
        report_text = (
            "LLM report generation is unavailable because no API key is configured. "
            "Retrieved evidence and module traces are available for inspection."
        )
        return {
            "report": report_text,
            "structured_report": _build_structured_report(state, report_text),
            "workflow_status": "completed",
            "warnings": ["Report generation used a fallback message because no LLM API key is configured."],
            "trace": [
                _trace(
                    "reporter",
                    "completed",
                    "Generated a fallback report because no LLM API key is configured.",
                    start_time=start_time,
                )
            ],
        }

    try:
        res = _get_report_llm().invoke(prompt)
        report_text = res.content.strip()
        return {
            "report": report_text,
            "structured_report": _build_structured_report(state, report_text),
            "workflow_status": "completed",
            "trace": [
                _trace(
                    "reporter",
                    "completed",
                    "Report generation completed.",
                    start_time=start_time,
                    metadata={"evidence_count": len(state.get("evidence", []))},
                )
            ],
        }
    except Exception as exc:
        report_text = (
            "Report generation failed. Please inspect retrieval evidence, perception status, "
            "and node traces for debugging."
        )
        return {
            "report": report_text,
            "structured_report": _build_structured_report(state, report_text),
            "workflow_status": "failed",
            "warnings": [f"Report generation failed: {exc}"],
            "errors": [f"report_generation_error: {exc}"],
            "trace": [
                _trace(
                    "reporter",
                    "failed",
                    "Report generation failed.",
                    start_time=start_time,
                    error=str(exc),
                )
            ],
        }


def medical_review_node(state: AgentState):
    start_time = time.perf_counter()

    if not state.get("reviewer_enabled", True):
        return {
            "review_status": "skipped",
            "is_medical_valid": True,
            "workflow_status": "completed",
            "trace": [
                _trace(
                    "reviewer",
                    "skipped",
                    "Reviewer disabled by workflow configuration.",
                    start_time=start_time,
                )
            ],
        }

    if not config.LLM_API_KEY:
        return {
            "review_status": "skipped",
            "is_medical_valid": True,
            "workflow_status": "completed",
            "warnings": ["Reviewer skipped because no LLM API key is configured."],
            "trace": [
                _trace(
                    "reviewer",
                    "skipped",
                    "Reviewer skipped because no LLM API key is configured.",
                    start_time=start_time,
                )
            ],
        }

    prompt = f"""
You are reviewing a medical decision-support answer for safety and reasoning quality.
If the report is acceptable, reply with PASS only.
Otherwise, reply with a short correction note.

User query: {state.get("query", "")}
Perception summary: {state.get("perception_data", "")}
Evidence count: {len(state.get("evidence", []))}
Report:
{state.get("report", "")}
"""
    try:
        res = _get_logic_llm().invoke(prompt)
        review_text = res.content.strip()
        passed = review_text.upper() == "PASS"
        return {
            "review_status": "passed" if passed else "failed",
            "is_medical_valid": passed,
            "review_feedback": "" if passed else review_text,
            "workflow_status": "completed",
            "trace": [
                _trace(
                    "reviewer",
                    "completed",
                    "Reviewer completed evaluation.",
                    start_time=start_time,
                    metadata={"passed": passed},
                )
            ],
        }
    except Exception as exc:
        return {
            "review_status": "skipped",
            "is_medical_valid": True,
            "workflow_status": "completed",
            "warnings": [f"Reviewer failed and was skipped: {exc}"],
            "errors": [f"reviewer_error: {exc}"],
            "trace": [
                _trace(
                    "reviewer",
                    "failed",
                    "Reviewer failed; current report was kept.",
                    start_time=start_time,
                    error=str(exc),
                )
            ],
        }
