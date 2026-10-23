"""故事管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..crud import get_art_styles
from ..database import get_db
from ..errors import AppError
from ..models import Post, Story
from ..schemas import StoryCreate, StoryRead, StoryUpdate
from ..services.files import (
    delete_cover_file,
    delete_group_photo,
    delete_story_page_images,
    validate_cover_filename,
)

router = APIRouter(prefix="/api/stories", tags=["故事"])


def _load_art_styles(db: Session) -> dict[str, dict[str, str]]:
    """一次性读取画风列表，构建 id -> {name, content} 映射。"""
    styles, _ = get_art_styles(db)
    return {style["id"]: style for style in styles}


def _validate_art_style_id(
    art_style_id: str | None, styles: dict[str, dict[str, str]]
) -> None:
    """故事只能引用画风列表中已存在的画风。"""
    if art_style_id is not None and art_style_id not in styles:
        raise AppError(
            422,
            "所选画风不存在，请先在「启动提示词」页的画风列表中添加或重新选择",
            "ART_STYLE_NOT_FOUND",
        )


def _to_story_read(story: Story, styles: dict[str, dict[str, str]]) -> StoryRead:
    """把故事转为响应模型，并解析出画风名称与描述。

    画风被删除后 art_style_id 仍保留（悬空引用），此时名称与描述为 None，
    由前端提示用户重新选择，避免静默丢失用户的选择记录。
    """
    style = styles.get(story.art_style_id) if story.art_style_id else None
    return StoryRead(
        id=story.id,
        name=story.name,
        content=story.content,
        cover_filename=story.cover_filename,
        cover_url=f"/uploads/{story.cover_filename}" if story.cover_filename else None,
        art_style_id=story.art_style_id,
        art_style_name=style["name"] if style else None,
        art_style_content=style["content"] if style else None,
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
    styles = _load_art_styles(db)
    return [_to_story_read(story, styles) for story in stories]


@router.post("", response_model=StoryRead, status_code=201)
def create_story(
    payload: StoryCreate, request: Request, db: Session = Depends(get_db)
) -> StoryRead:
    upload_dir = request.app.state.app_settings.upload_dir
    validate_cover_filename(payload.cover_filename, upload_dir)

    styles = _load_art_styles(db)
    _validate_art_style_id(payload.art_style_id, styles)

    story = Story(
        name=payload.name,
        content=payload.content,
        cover_filename=payload.cover_filename,
        art_style_id=payload.art_style_id,
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return _to_story_read(story, styles)


@router.get("/{story_id}", response_model=StoryRead)
def get_story(story_id: int, db: Session = Depends(get_db)) -> StoryRead:
    story = _get_story_or_404(db, story_id)
    return _to_story_read(story, _load_art_styles(db))


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

    styles = _load_art_styles(db)
    _validate_art_style_id(payload.art_style_id, styles)

    story.name = payload.name
    story.content = payload.content
    story.cover_filename = payload.cover_filename
    story.art_style_id = payload.art_style_id
    db.commit()
    db.refresh(story)

    # 数据库提交成功后再删除旧封面，避免事务回滚导致文件丢失
    if old_cover and old_cover != story.cover_filename:
        delete_cover_file(old_cover, upload_dir)

    return _to_story_read(story, styles)


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
    # 分镜成品图目录与人物合照随故事一起清理
    delete_story_page_images(request.app.state.app_settings.upload_dir, story_id)
    delete_group_photo(request.app.state.app_settings.upload_dir, story_id)
    return Response(status_code=204)
