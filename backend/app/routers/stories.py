"""故事管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import AppError
from ..models import Post, Story
from ..schemas import StoryCreate, StoryRead, StoryUpdate
from ..services.files import delete_cover_file, validate_cover_filename

router = APIRouter(prefix="/api/stories", tags=["故事"])


def _to_story_read(story: Story) -> StoryRead:
    return StoryRead(
        id=story.id,
        name=story.name,
        content=story.content,
        cover_filename=story.cover_filename,
        cover_url=f"/uploads/{story.cover_filename}" if story.cover_filename else None,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )


def _get_story_or_404(db: Session, story_id: int) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise AppError(404, "故事不存在或已被删除", "STORY_NOT_FOUND")
    return story


@router.get("", response_model=list[StoryRead])
def list_stories(db: Session = Depends(get_db)) -> list[StoryRead]:
    stories = db.scalars(
        select(Story).order_by(Story.updated_at.desc(), Story.id.desc())
    ).all()
    return [_to_story_read(story) for story in stories]


@router.post("", response_model=StoryRead, status_code=201)
def create_story(
    payload: StoryCreate, request: Request, db: Session = Depends(get_db)
) -> StoryRead:
    upload_dir = request.app.state.app_settings.upload_dir
    validate_cover_filename(payload.cover_filename, upload_dir)

    story = Story(
        name=payload.name,
        content=payload.content,
        cover_filename=payload.cover_filename,
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return _to_story_read(story)


@router.get("/{story_id}", response_model=StoryRead)
def get_story(story_id: int, db: Session = Depends(get_db)) -> StoryRead:
    return _to_story_read(_get_story_or_404(db, story_id))


@router.put("/{story_id}", response_model=StoryRead)
def update_story(
    story_id: int,
    payload: StoryUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> StoryRead:
    story = _get_story_or_404(db, story_id)
    upload_dir = request.app.state.app_settings.upload_dir
    old_cover = story.cover_filename

    if payload.cover_filename is not None and payload.cover_filename != old_cover:
        validate_cover_filename(payload.cover_filename, upload_dir)

    story.name = payload.name
    story.content = payload.content
    story.cover_filename = payload.cover_filename
    db.commit()
    db.refresh(story)

    # 数据库提交成功后再删除旧封面，避免事务回滚导致文件丢失
    if old_cover and old_cover != story.cover_filename:
        delete_cover_file(old_cover, upload_dir)

    return _to_story_read(story)


@router.delete("/{story_id}", status_code=204)
def delete_story(
    story_id: int, request: Request, db: Session = Depends(get_db)
) -> Response:
    story = _get_story_or_404(db, story_id)

    post_count = (
        db.scalar(
            select(func.count()).select_from(Post).where(Post.story_id == story_id)
        )
        or 0
    )
    if post_count:
        raise AppError(
            409,
            f"该故事下已有 {post_count} 条发文记录，请先删除发文后再删除故事",
            "STORY_HAS_POSTS",
        )

    cover_filename = story.cover_filename
    db.delete(story)
    db.commit()
    delete_cover_file(cover_filename, request.app.state.app_settings.upload_dir)
    return Response(status_code=204)
