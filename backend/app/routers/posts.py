"""发文管理接口：CRUD 与 AI 文案生成。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..crud import (
    get_art_styles,
    get_start_prompt,
    resolve_deepseek_key,
)
from ..database import get_db
from ..errors import AppError
from ..models import Post, Story
from ..schemas import (
    GenerateRequest,
    GenerateResponse,
    PostCreate,
    PostRead,
    PostStatus,
    PostUpdate,
)
from ..services.deepseek import generate_copy

router = APIRouter(prefix="/api/posts", tags=["发文"])


def _to_post_read(post: Post, story_name: str) -> PostRead:
    return PostRead(
        id=post.id,
        story_id=post.story_id,
        story_name=story_name,
        title=post.title,
        content=post.content,
        status=post.status,  # type: ignore[arg-type]
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


def _get_post_or_404(db: Session, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise AppError(404, "发文记录不存在或已被删除", "POST_NOT_FOUND")
    return post


@router.get("", response_model=list[PostRead])
def list_posts(
    story_id: int | None = None,
    status: PostStatus | None = None,
    db: Session = Depends(get_db),
) -> list[PostRead]:
    stmt = (
        select(Post)
        .options(joinedload(Post.story))
        .order_by(Post.updated_at.desc(), Post.id.desc())
    )
    if story_id is not None:
        stmt = stmt.where(Post.story_id == story_id)
    if status is not None:
        stmt = stmt.where(Post.status == status)

    posts = db.scalars(stmt).unique().all()
    return [_to_post_read(post, post.story.name) for post in posts]


@router.post("", response_model=PostRead, status_code=201)
def create_post(payload: PostCreate, db: Session = Depends(get_db)) -> PostRead:
    story = db.get(Story, payload.story_id)
    if story is None:
        raise AppError(404, "关联的故事不存在，请先创建故事", "STORY_NOT_FOUND")

    post = Post(
        story_id=payload.story_id,
        title=payload.title,
        content=payload.content,
        status=payload.status,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _to_post_read(post, story.name)


@router.post("/generate", response_model=GenerateResponse)
def generate_post_copy(
    payload: GenerateRequest, db: Session = Depends(get_db)
) -> GenerateResponse:
    """根据故事与启动提示词调用 DeepSeek，结果不入库，由用户确认后保存。"""
    story = db.get(Story, payload.story_id)
    if story is None:
        raise AppError(404, "所选故事不存在，请刷新后重试", "STORY_NOT_FOUND")

    # 先把所需数据取到局部变量，再结束读事务，外部 HTTP 调用期间不持有数据库事务
    story_name = story.name
    story_content = story.content
    start_prompt, _ = get_start_prompt(db)
    # 生成文案优先使用故事自己的画风，故事画风无效时回退全局当前画风
    styles, active_id = get_art_styles(db)
    style = next(
        (item for item in styles if item["id"] == story.art_style_id), None
    )
    if style is None and active_id is not None:
        style = next(
            (item for item in styles if item["id"] == active_id), None
        )
    art_style = style["content"] if style is not None else None
    art_style_name = style["name"] if style is not None else None
    api_key, _, _ = resolve_deepseek_key(db)
    db.rollback()

    if api_key is None:
        raise AppError(
            409,
            "尚未配置 DeepSeek API Key，请先到「启动提示词」页面完成配置",
            "DEEPSEEK_KEY_MISSING",
        )

    copy = generate_copy(
        api_key=api_key,
        start_prompt=start_prompt,
        story_name=story_name,
        story_content=story_content,
        art_style=art_style,
        art_style_name=art_style_name,
    )
    return GenerateResponse(
        story_id=payload.story_id, title=copy.title, content=copy.content
    )


@router.get("/{post_id}", response_model=PostRead)
def get_post(post_id: int, db: Session = Depends(get_db)) -> PostRead:
    post = _get_post_or_404(db, post_id)
    return _to_post_read(post, post.story.name)


@router.patch("/{post_id}", response_model=PostRead)
def update_post(
    post_id: int, payload: PostUpdate, db: Session = Depends(get_db)
) -> PostRead:
    post = _get_post_or_404(db, post_id)

    if payload.title is not None:
        post.title = payload.title
    if payload.content is not None:
        post.content = payload.content
    if payload.status is not None:
        post.status = payload.status

    db.commit()
    db.refresh(post)
    return _to_post_read(post, post.story.name)


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session = Depends(get_db)) -> Response:
    post = _get_post_or_404(db, post_id)
    db.delete(post)
    db.commit()
    return Response(status_code=204)
