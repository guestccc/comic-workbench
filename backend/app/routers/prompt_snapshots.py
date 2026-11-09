"""提示词快照接口：查看渲染历史、恢复上一版提示词。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import PromptSnapshotRead, PromptSnapshotRestoreResult
from ..services import prompt_snapshots as service

router = APIRouter(prefix="/api", tags=["提示词快照"])


@router.get(
    "/stories/{story_id}/prompt-snapshots",
    response_model=list[PromptSnapshotRead],
)
def list_prompt_snapshots(
    story_id: int,
    target_type: str | None = Query(default=None),
    chapter_number: int | None = Query(default=None, ge=1),
    page_number: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict]:
    return service.list_snapshots(
        db,
        story_id,
        target_type=target_type,
        chapter_number=chapter_number,
        page_number=page_number,
        limit=limit,
    )


@router.post(
    "/prompt-snapshots/{snapshot_id}/restore",
    response_model=PromptSnapshotRestoreResult,
)
def restore_prompt_snapshot(
    snapshot_id: int, db: Session = Depends(get_db)
) -> dict:
    return service.restore_snapshot(db, snapshot_id)
