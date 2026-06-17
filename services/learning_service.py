from __future__ import annotations

from sqlalchemy.orm import Session

from core.models import LearningSessionRecord


def upsert_learning_session(
    db: Session,
    *,
    session_id: str,
    procedure_name: str | None,
    scene: str | None,
) -> LearningSessionRecord:
    row = (
        db.query(LearningSessionRecord)
        .filter(LearningSessionRecord.session_id == session_id)
        .order_by(LearningSessionRecord.started_at.desc())
        .first()
    )
    if row is None:
        row = LearningSessionRecord(
            session_id=session_id,
            procedure_name=procedure_name,
            scene=scene,
        )
        db.add(row)
    else:
        if procedure_name and not row.procedure_name:
            row.procedure_name = procedure_name
        if scene:
            row.scene = scene
    db.commit()
    db.refresh(row)
    return row
