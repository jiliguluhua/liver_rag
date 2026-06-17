from __future__ import annotations

from typing import Optional


def infer_procedure_and_topics(text: str) -> tuple[Optional[str], list[str]]:
    normalized = (text or "").lower()
    procedure = None
    if any(token in normalized for token in ["cholecystectomy", "胆囊切除", "胆囊"]):
        procedure = "cholecystectomy"
    elif any(token in normalized for token in ["hepatectomy", "肝切除", "肝段"]):
        procedure = "hepatectomy"

    topic_keywords = {
        "anatomy": ["anatomy", "解剖", "calot", "calot triangle", "胆道变异"],
        "disease_background": ["病理", "机制", "疾病", "背景", "肿瘤", "胆囊炎", "肝癌"],
        "operative_steps": ["步骤", "术式", "操作", "切除步骤", "procedure", "step"],
        "risk_points": ["风险", "损伤", "注意点", "陷阱", "risk"],
        "complications": ["并发症", "胆漏", "出血", "损伤", "complication"],
        "bailout_strategy": ["bailout", "转开放", "补救", "挽救", "困难胆囊"],
    }
    topics = [name for name, keywords in topic_keywords.items() if any(token in normalized for token in keywords)]
    if not topics:
        topics = ["operative_steps"] if procedure else ["disease_background"]
    return procedure, topics
