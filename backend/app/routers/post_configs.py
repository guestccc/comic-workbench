"""每个故事一份的小红书发文配置。

与「发文管理」的多条 posts 记录相互独立：这里只保存故事配套的
标题与正文，供发布小红书时直接修改使用。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import AppError
from ..models import Story, StoryPostConfig
from ..schemas import StoryPostConfigRead, StoryPostConfigUpdate

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


@router.get(
    "/{story_id}/post-config", response_model=StoryPostConfigRead | None
)
def get_post_config(
    story_id: int, db: Session = Depends(get_db)
) -> StoryPostConfigRead | None:
    """读取配置；尚未保存时返回 null，前端显示空表单。"""
    _get_story_or_404(db, story_id)
    config = _get_config(db, story_id)
    return None if config is None else _to_read(config)


@router.put(
    "/{story_id}/post-config", response_model=StoryPostConfigRead
)
def save_post_config(
    story_id: int,
    payload: StoryPostConfigUpdate,
    db: Session = Depends(get_db),
) -> StoryPostConfigRead:
    """全量保存标题与正文；空字符串允许保存。"""
    _get_story_or_404(db, story_id)
    config = _get_config(db, story_id)
    if config is None:
        config = StoryPostConfig(story_id=story_id)
        db.add(config)

    config.title = payload.title
    config.content = payload.content
    db.commit()
    db.refresh(config)
    return _to_read(config)
