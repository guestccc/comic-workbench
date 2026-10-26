"""故事管理接口。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import MAX_ZHIHU_ALIASES
from ..crud import get_art_styles, resolve_deepseek_key
from ..database import get_db
from ..errors import AppError
from ..models import (
    Post,
    Story,
    StoryChapterPostConfig,
    StoryPostConfig,
)
from ..schemas import (
    StoryCreate,
    StoryRead,
    StoryUpdate,
    StoryZhihuUpdate,
    ZhihuAliasSuggestionsRead,
)
from ..services.deepseek import generate_zhihu_aliases
from ..services.zhihu import (
    ALIAS_PATTERN,
    apply_alias_prefix,
    title_bigrams,
    validate_alias,
)
from ..services.files import (
    chapter_asset_url,
    delete_cover_file,
    delete_group_photo,
    delete_story_chapter_assets,
    delete_story_character_assets,
    delete_story_page_images,
    page_image_url,
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


def _to_story_read(
    story: Story,
    styles: dict[str, dict[str, str]],
    upload_dir: Path,
) -> StoryRead:
    """把故事转为响应模型，并解析出画风名称与描述。

    画风被删除后 art_style_id 仍保留（悬空引用），此时名称与描述为 None，
    由前端提示用户重新选择，避免静默丢失用户的选择记录。

    封面：优先使用单独上传的封面；没有时默认取第 1 章封面，再没有就取
    第 1 页镜头的成品图，这样拆完章节、出过图的故事在列表里自然就有封面。
    """
    style = styles.get(story.art_style_id) if story.art_style_id else None
    cover_url = (
        f"/uploads/{story.cover_filename}" if story.cover_filename else None
    )
    if cover_url is None:
        cover_url = chapter_asset_url(upload_dir, story.id, 1, "cover")
    if cover_url is None:
        cover_url = page_image_url(upload_dir, story.id, 1)
    aliases = list(story.zhihu_aliases or [])
    if story.zhihu_alias and story.zhihu_alias not in aliases:
        aliases.insert(0, story.zhihu_alias)
    return StoryRead(
        id=story.id,
        name=story.name,
        content=story.content,
        cover_filename=story.cover_filename,
        cover_url=cover_url,
        art_style_id=story.art_style_id,
        art_style_name=style["name"] if style else None,
        art_style_content=style["content"] if style else None,
        # 知乎原名标题就是故事名，不单独存储，避免两处标题漂移
        zhihu_title=story.name,
        zhihu_article_id=story.zhihu_article_id,
        zhihu_alias=story.zhihu_alias,
        zhihu_aliases=aliases,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )


def _get_story_or_404(db: Session, story_id: int) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise AppError(404, "故事不存在或已被删除", "STORY_NOT_FOUND")
    return story


def _validate_name_change_for_aliases(story: Story, new_name: str) -> None:
    """故事名就是知乎原名标题；改名后仍要满足别名复用规则。

    旧候选别名可能不符合 6–8 字规则，这类历史数据不阻断改名；格式合法的
    别名如果与新故事名复用连续两个字，则拒绝改名，避免静默破坏 Z-02。
    """
    aliases = list(story.zhihu_aliases or [])
    if story.zhihu_alias and story.zhihu_alias not in aliases:
        aliases.append(story.zhihu_alias)
    if not aliases:
        return
    title = new_name.strip()
    if not title:
        raise AppError(
            422,
            "该故事已有知乎别名，不能清空故事名（知乎原名标题）",
            "ZHIHU_TITLE_REQUIRED",
        )
    for alias in aliases:
        if ALIAS_PATTERN.fullmatch(alias):
            validate_alias(title, alias)


def _validate_alias_unique(
    db: Session, story_id: int, alias: str
) -> None:
    """本地故事之间不允许使用同一个搜索别名，避免用户记混。"""
    if not alias:
        return
    conflict = db.scalar(
        select(Story).where(
            Story.zhihu_alias == alias,
            Story.id != story_id,
        )
    )
    if conflict is not None:
        raise AppError(
            409,
            f"别名「{alias}」已被故事《{conflict.name}》使用",
            "ALIAS_ALREADY_USED",
        )


@router.get("", response_model=list[StoryRead])
def list_stories(
    request: Request, db: Session = Depends(get_db)
) -> list[StoryRead]:
    stories = db.scalars(
        select(Story).order_by(Story.updated_at.desc(), Story.id.desc())
    ).all()
    styles = _load_art_styles(db)
    upload_dir = request.app.state.app_settings.upload_dir
    return [_to_story_read(story, styles, upload_dir) for story in stories]


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
    return _to_story_read(story, styles, upload_dir)


@router.get("/{story_id}", response_model=StoryRead)
def get_story(
    story_id: int, request: Request, db: Session = Depends(get_db)
) -> StoryRead:
    story = _get_story_or_404(db, story_id)
    return _to_story_read(
        story,
        _load_art_styles(db),
        request.app.state.app_settings.upload_dir,
    )


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
    if payload.name != story.name:
        _validate_name_change_for_aliases(story, payload.name)

    story.name = payload.name
    story.content = payload.content
    story.cover_filename = payload.cover_filename
    story.art_style_id = payload.art_style_id
    db.commit()
    db.refresh(story)

    # 数据库提交成功后再删除旧封面，避免事务回滚导致文件丢失
    if old_cover and old_cover != story.cover_filename:
        delete_cover_file(old_cover, upload_dir)

    return _to_story_read(story, styles, upload_dir)


@router.patch("/{story_id}/zhihu", response_model=StoryRead)
def update_story_zhihu(
    story_id: int,
    payload: StoryZhihuUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> StoryRead:
    """保存知乎原文 ID 与搜索别名，并同步已保存文案的开头。

    知乎原名标题不再单独录入，统一使用故事名；别名复用校验也基于故事名。
    """
    story = _get_story_or_404(db, story_id)
    aliases = (
        list(payload.zhihu_aliases)
        if payload.zhihu_aliases is not None
        else list(story.zhihu_aliases or [])
    )
    if payload.zhihu_alias and payload.zhihu_alias not in aliases:
        aliases.append(payload.zhihu_alias)
    if len(aliases) > MAX_ZHIHU_ALIASES:
        raise AppError(
            422,
            f"候选别名最多保存 {MAX_ZHIHU_ALIASES} 个",
            "TOO_MANY_ZHIHU_ALIASES",
        )
    title = story.name.strip()
    for alias in aliases:
        validate_alias(title, alias)
    _validate_alias_unique(db, story_id, payload.zhihu_alias)

    old_alias = story.zhihu_alias
    story.zhihu_article_id = payload.zhihu_article_id
    story.zhihu_alias = payload.zhihu_alias
    story.zhihu_aliases = aliases

    if old_alias != payload.zhihu_alias:
        chapter_configs = db.scalars(
            select(StoryChapterPostConfig).where(
                StoryChapterPostConfig.story_id == story_id
            )
        ).all()
        for config in chapter_configs:
            if config.content.strip():
                config.content = apply_alias_prefix(
                    config.content, payload.zhihu_alias
                )
        legacy_config = db.scalar(
            select(StoryPostConfig).where(StoryPostConfig.story_id == story_id)
        )
        if legacy_config is not None and legacy_config.content.strip():
            legacy_config.content = apply_alias_prefix(
                legacy_config.content, payload.zhihu_alias
            )

    db.commit()
    db.refresh(story)
    return _to_story_read(
        story,
        _load_art_styles(db),
        request.app.state.app_settings.upload_dir,
    )


@router.post(
    "/{story_id}/zhihu/alias-suggestions",
    response_model=ZhihuAliasSuggestionsRead,
)
def suggest_zhihu_aliases(
    story_id: int,
    db: Session = Depends(get_db),
) -> ZhihuAliasSuggestionsRead:
    """用 DeepSeek 生成 6 个候选别名，并过滤标题文字/本地重复。

    知乎原名标题就是故事名；故事名为空时无法保证别名不复用原标题文案。
    """
    story = _get_story_or_404(db, story_id)
    title = story.name.strip()
    if not title:
        raise AppError(
            422,
            "请先在「故事管理」中填写故事名（知乎原名标题），再生成别名",
            "ZHIHU_TITLE_REQUIRED",
        )

    api_key, _, _ = resolve_deepseek_key(db)
    other_stories = db.scalars(
        select(Story).where(Story.id != story_id)
    ).all()
    existing_aliases: set[str] = set()
    for item in other_stories:
        existing_aliases.update(item.zhihu_aliases or [])
        if item.zhihu_alias:
            existing_aliases.add(item.zhihu_alias)
    db.rollback()

    if api_key is None:
        raise AppError(
            409,
            "尚未配置 DeepSeek API Key，请先到「设置」页配置，或手动填写别名",
            "DEEPSEEK_KEY_MISSING",
        )

    aliases = generate_zhihu_aliases(api_key, title)
    forbidden_bigrams = title_bigrams(title)
    valid: list[str] = []
    for alias in aliases:
        alias = alias.strip()
        if not ALIAS_PATTERN.fullmatch(alias):
            continue
        alias_bigrams = {
            alias[index : index + 2] for index in range(len(alias) - 1)
        }
        if forbidden_bigrams & alias_bigrams:
            continue
        if alias in existing_aliases or alias in valid:
            continue
        valid.append(alias)
        if len(valid) >= 6:
            break

    if not valid:
        raise AppError(
            502,
            "别名生成失败，请稍后重试或手动填写",
            "ALIAS_GENERATION_FAILED",
        )
    return ZhihuAliasSuggestionsRead(aliases=valid)


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
    # 分镜成品图、章节封面/引导卡、角色资产图与人物合照随故事一起清理
    delete_story_page_images(request.app.state.app_settings.upload_dir, story_id)
    delete_story_chapter_assets(
        request.app.state.app_settings.upload_dir, story_id
    )
    delete_story_character_assets(
        request.app.state.app_settings.upload_dir, story_id
    )
    delete_group_photo(request.app.state.app_settings.upload_dir, story_id)
    return Response(status_code=204)
