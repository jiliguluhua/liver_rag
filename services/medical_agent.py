from __future__ import annotations

import uuid
from typing import Any, Optional

from agents.graph import medical_app
from agents.state import AgentState, create_initial_state


class LiverSmartAgent:
    def __init__(self, api_key: str, model_path=None, meta_path=None):
        self.api_key = api_key
        self.model_path = model_path
        self.meta_path = meta_path
        self.graph = medical_app

    def run(
        self,
        image_path: Optional[str],
        user_query: str,
        *,
        job_id: Optional[str] = None,
        session_id: Optional[str] = None,
        reviewer_enabled: bool = True,
        user_context: Optional[dict[str, Any]] = None,
    ) -> tuple[str, Any, AgentState]:
        initial_state = create_initial_state(
            query=user_query,
            image_path=(image_path or "").strip() or None,
            job_id=(job_id or "").strip(),
            session_id=(session_id or "").strip() or str(uuid.uuid4()),
            reviewer_enabled=reviewer_enabled,
            user_context=user_context,
        )
        final_state = self.graph.invoke(initial_state)
        report = final_state.get("report", "")
        preview_image = final_state.get("preview_image")
        return report, preview_image, final_state
