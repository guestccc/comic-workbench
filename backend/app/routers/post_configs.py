"""每个故事一份的小红书发文配置。

与「发文管理」的多条 posts 记录相互独立：这里只保存故事配套的
标题与正文，供发布小红书时直接修改使用。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import AppError
from ..models import (
    Story,
    StoryBreakdown,
    StoryChapterPostConfig,
    StoryPostConfig,
)
from ..schemas import (
    StoryChapterPostConfigRead,
    StoryPostConfigRead,
    StoryPostConfigUpdate,
)
from ..services.zhihu import apply_alias_prefix

router = APIRouter(prefix="/api/stories", tags=["发文配置"])


def _get_story_or_404(db: Session, story_id: int) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise AppError(404, "故事不存在或已被删除", "STORY_NOT_FOUND")
    return story


def _get_config(
    db: Session, story_id: int
) -> StoryPostConfig | None:
    return db.scalar(
        select(StoryPostConfig).where(StoryPostConfig.story_id == story_id)
    )


def _to_read(config: StoryPostConfig) -> StoryPostConfigRead:
    return StoryPostConfigRead(
        id=config.id,
        story_id=config.story_id,
        title=config.title,
        content=config.content,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _to_chapter_read(
    config: StoryChapterPostConfig,
) -> StoryChapterPostConfigRead:
    return StoryChapterPostConfigRead(
        id=config.id,
        story_id=config.story_id,
        chapter_number=config.chapter_number,
        title=config.title,
        content=config.content,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _get_chapter_or_404(
    db: Session, story_id: int, chapter_number: int
) -> dict:
    """校验章节确实存在于该故事的章节规划中。"""
    breakdown = db.scalar(
        select(StoryBreakdown).where(StoryBreakdown.story_id == story_id)
    )
    if breakdown is None or not breakdown.chapters:
        raise AppError(
            404, "该故事还没有章节规划", "CHAPTERS_NOT_FOUND"
        )
    for chapter in breakdown.chapters:
        if chapter.get("chapter_number") == chapter_number:
            return chapter
    raise AppError(
        404, f"第 {chapter_number} 章不存在", "CHAPTER_NOT_FOUND"
    )


def _get_chapter_config(
    db: Session, story_id: int, chapter_number: int
) -> StoryChapterPostConfig | None:
    return db.scalar(
        select(StoryChapterPostConfig).where(
            StoryChapterPostConfig.story_id == story_id,
            StoryChapterPostConfig.chapter_number == chapter_number,
        )
    )


@router.get(
    "/{story_id}/post-config",
    response_model=StoryPostConfigRead
    | StoryChapterPostConfigRead
    | None,
)
def get_post_config(
    story_id: int,
    chapter: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> StoryPostConfigRead | StoryChapterPostConfigRead | None:
    """读取配置；尚未保存时返回 null，前端显示空表单。

    传 chapter 时读取该章配置；不传时读取旧版整篇故事配置。
    """
    _get_story_or_404(db, story_id)
    if chapter is not None:
        _get_chapter_or_404(db, story_id, chapter)
        config = _get_chapter_config(db, story_id, chapter)
        return None if config is None else _to_chapter_read(config)

    config = _get_config(db, story_id)
    return None if config is None else _to_read(config)


@router.put(
    "/{story_id}/post-config",
    response_model=StoryPostConfigRead | StoryChapterPostConfigRead,
)
def save_post_config(
    story_id: int,
    payload: StoryPostConfigUpdate,
    chapter: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> StoryPostConfigRead | StoryChapterPostConfigRead:
    """全量保存标题与正文；空字符串允许保存。

    传 chapter 时保存到该章；不传时保存旧版整篇故事配置。
    """
    story = _get_story_or_404(db, story_id)
    content = (
        apply_alias_prefix(payload.content, story.zhihu_alias)
        if story.zhihu_alias
        else payload.content
    )

    if chapter is not None:
        _get_chapter_or_404(db, story_id, chapter)
        config = _get_chapter_config(db, story_id, chapter)
        if config is None:
            config = StoryChapterPostConfig(
                story_id=story_id, chapter_number=chapter
            )
            db.add(config)
        config.title = payload.title
        config.content = content
        db.commit()
        db.refresh(config)
        return _to_chapter_read(config)

    config = _get_config(db, story_id)
    if config is None:
        config = StoryPostConfig(story_id=story_id)
        db.add(config)

    config.title = payload.title
    config.content = content
    db.commit()
    db.refresh(config)
    return _to_read(config)
