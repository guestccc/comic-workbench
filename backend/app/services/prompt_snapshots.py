"""提示词渲染快照：写入、查询与恢复上一版提示词。"""

from __future__ import annotations

import copy

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import PromptRenderSnapshot, StoryBreakdown


def _read(snapshot: PromptRenderSnapshot) -> dict:
    return {
        "id": snapshot.id,
        "story_id": snapshot.story_id,
        "target_type": snapshot.target_type,
        "chapter_number": snapshot.chapter_number,
        "page_number": snapshot.page_number,
        "template_type": snapshot.template_type,
        "prompt": snapshot.prompt,
        "applied_rules": snapshot.applied_rules or [],
        "rule_checks": snapshot.rule_checks or [],
        "restored_from_id": snapshot.restored_from_id,
        "created_at": snapshot.created_at,
    }


def create_snapshot(
    db: Session,
    *,
    story_id: int,
    template_type: str,
    context: dict,
    prompt: str,
    applied_rules: list[dict],
    rule_checks: list[dict] | None = None,
    restored_from_id: int | None = None,
) -> dict:
    snapshot = PromptRenderSnapshot(
        story_id=story_id,
        target_type="cover" if template_type == "cover" else "body",
        chapter_number=context.get("chapter_number"),
        page_number=(
            context.get("page_number") if template_type == "body" else None
        ),
        template_type=template_type,
        context=context,
        prompt=prompt,
        applied_rules=applied_rules,
        rule_checks=rule_checks or [],
        restored_from_id=restored_from_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return _read(snapshot)


def list_snapshots(
    db: Session,
    story_id: int,
    *,
    target_type: str | None = None,
    chapter_number: int | None = None,
    page_number: int | None = None,
    limit: int = 20,
) -> list[dict]:
    stmt = select(PromptRenderSnapshot).where(
        PromptRenderSnapshot.story_id == story_id
    )
    if target_type:
        stmt = stmt.where(PromptRenderSnapshot.target_type == target_type)
    if chapter_number is not None:
        stmt = stmt.where(
            PromptRenderSnapshot.chapter_number == chapter_number
        )
    if page_number is not None:
        stmt = stmt.where(PromptRenderSnapshot.page_number == page_number)
    stmt = stmt.order_by(
        PromptRenderSnapshot.created_at.desc(),
        PromptRenderSnapshot.id.desc(),
    ).limit(max(1, min(limit, 100)))
    return [_read(snapshot) for snapshot in db.scalars(stmt).all()]


def restore_snapshot(db: Session, snapshot_id: int) -> dict:
    snapshot = db.get(PromptRenderSnapshot, snapshot_id)
    if snapshot is None:
        raise AppError(404, "提示词快照不存在或已被删除", "PROMPT_SNAPSHOT_NOT_FOUND")
    breakdown = db.scalar(
        select(StoryBreakdown).where(
            StoryBreakdown.story_id == snapshot.story_id
        )
    )
    if breakdown is None:
        raise AppError(404, "故事拆解结果不存在", "BREAKDOWN_NOT_FOUND")

    if snapshot.target_type == "cover":
        chapters = copy.deepcopy(list(breakdown.chapters or []))
        target = next(
            (
                chapter
                for chapter in chapters
                if chapter.get("chapter_number") == snapshot.chapter_number
            ),
            None,
        )
        if target is None:
            raise AppError(
                404,
                "快照对应的章节封面不存在",
                "PROMPT_SNAPSHOT_TARGET_NOT_FOUND",
            )
        target.setdefault("cover", {})["image_prompt"] = snapshot.prompt
        breakdown.chapters = chapters
    elif snapshot.target_type == "body":
        pages = copy.deepcopy(list(breakdown.pages or []))
        target = next(
            (
                page
                for page in pages
                if page.get("chapter_number") == snapshot.chapter_number
                and page.get("chapter_page_number") == snapshot.page_number
            ),
            None,
        )
        if target is None:
            # 兼容旧数据：没有 chapter_page_number 时按全局页码匹配
            target = next(
                (
                    page
                    for page in pages
                    if page.get("page_number") == snapshot.page_number
                ),
                None,
            )
        if target is None:
            raise AppError(
                404,
                "快照对应的正文页不存在",
                "PROMPT_SNAPSHOT_TARGET_NOT_FOUND",
            )
        target["image_prompt"] = snapshot.prompt
        breakdown.pages = pages
    else:
        raise AppError(422, "快照目标类型不支持", "PROMPT_SNAPSHOT_TARGET_INVALID")

    db.commit()
    restored = create_snapshot(
        db,
        story_id=snapshot.story_id,
        template_type=snapshot.template_type,
        context=snapshot.context or {},
        prompt=snapshot.prompt,
        applied_rules=snapshot.applied_rules or [],
        rule_checks=snapshot.rule_checks or [],
        restored_from_id=snapshot.id,
    )
    return {
        "snapshot": restored,
        "target_type": snapshot.target_type,
        "chapter_number": snapshot.chapter_number,
        "page_number": snapshot.page_number,
    }
