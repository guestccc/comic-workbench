"""故事拆解结果接口：优化后文章、角色设定卡与分镜页。

``group_photo_prompt`` 是旧流程字段，新流程不再写入，保留仅为兼容旧数据。


拆解本身由 Claude Code 技能完成，本模块只负责结果读写。
一个故事只有一份拆解结果；分镜页存放在 JSON 列中，按 page_number 排序。
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import MAX_BREAKDOWN_PAGES, MAX_OPTIMIZE_ANALYZE_INPUT_CHARS
from ..crud import get_art_styles, resolve_deepseek_key
from ..database import get_db
from ..errors import AppError
from ..models import Story, StoryBreakdown
from ..schemas import (
    CharacterCard,
    StoryboardPagePayload,
    StoryboardPageRead,
    StoryBreakdownRead,
    StoryBreakdownUpdate,
    StoryOptimizationAnalysis,
)
from ..services.deepseek import analyze_optimization_changes

router = APIRouter(prefix="/api/stories", tags=["故事拆解"])


def _get_story_or_404(db: Session, story_id: int) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise AppError(404, "故事不存在或已被删除", "STORY_NOT_FOUND")
    return story


def _get_breakdown(db: Session, story_id: int) -> StoryBreakdown | None:
    return db.scalar(
        select(StoryBreakdown).where(StoryBreakdown.story_id == story_id)
    )


def _content_hash(content: str) -> str:
    """用原文 hash 判断拆解结果是否基于最新原文。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _analysis_hash(story_content: str, optimized_content: str) -> str:
    """改动解读的缓存键：原文或优化文任一变化都会让旧解读失效。"""
    payload = f"{story_content}\x00{optimized_content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_story_style(
    db: Session, story: Story
) -> dict[str, str] | None:
    """解析故事当前选用的画风；画风被删除时返回 None。"""
    styles, _ = get_art_styles(db)
    for style in styles:
        if style["id"] == story.art_style_id:
            return style
    return None


def _is_art_style_stale(
    breakdown: StoryBreakdown,
    story: Story,
    style: dict[str, str] | None,
) -> bool:
    """画风 id 变化、画风被删除，或画风内容被修改，都视为过期。"""
    if breakdown.art_style_id != story.art_style_id:
        return True
    if story.art_style_id is None:
        return False
    if style is None:
        return True
    return (
        style["name"] != breakdown.art_style_name
        or style["content"] != breakdown.art_style_content
    )


def _to_breakdown_read(
    breakdown: StoryBreakdown,
    story: Story,
    style: dict[str, str] | None,
) -> StoryBreakdownRead:
    """组装响应模型，并计算原文 / 画风的过期标记。"""
    pages = sorted(
        (
            StoryboardPageRead.model_validate(page)
            for page in breakdown.pages
        ),
        key=lambda page: page.page_number,
    )
    return StoryBreakdownRead(
        id=breakdown.id,
        story_id=breakdown.story_id,
        optimized_content=breakdown.optimized_content,
        characters=[
            CharacterCard.model_validate(card) for card in breakdown.characters
        ],
        group_photo_prompt=breakdown.group_photo_prompt,
        pages=pages,
        art_style_id=breakdown.art_style_id,
        art_style_name=breakdown.art_style_name,
        art_style_content=breakdown.art_style_content,
        is_content_stale=breakdown.source_content_hash
        != _content_hash(story.content),
        is_art_style_stale=_is_art_style_stale(breakdown, story, style),
        created_at=breakdown.created_at,
        updated_at=breakdown.updated_at,
    )


def _touch_source(breakdown: StoryBreakdown, story: Story) -> None:
    """记录本次写回所基于的原文版本。"""
    breakdown.source_content_hash = _content_hash(story.content)


@router.get(
    "/{story_id}/breakdown", response_model=StoryBreakdownRead | None
)
def get_breakdown(
    story_id: int, db: Session = Depends(get_db)
) -> StoryBreakdownRead | None:
    """读取拆解结果；尚未拆解时返回 null，前端按空态展示。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        return None
    return _to_breakdown_read(
        breakdown, story, _resolve_story_style(db, story)
    )


@router.patch("/{story_id}/breakdown", response_model=StoryBreakdownRead)
def update_breakdown(
    story_id: int,
    payload: StoryBreakdownUpdate,
    db: Session = Depends(get_db),
) -> StoryBreakdownRead:
    """局部更新拆解头部信息；不存在时创建。

    创建拆解要求故事已选择有效画风，避免生成没有画风约束的分镜。
    """
    story = _get_story_or_404(db, story_id)
    style = _resolve_story_style(db, story)
    breakdown = _get_breakdown(db, story_id)

    if breakdown is None:
        if style is None:
            raise AppError(
                422,
                "该故事尚未选择有效画风，请先选择画风后再拆解",
                "ART_STYLE_REQUIRED",
            )
        breakdown = StoryBreakdown(story_id=story_id)
        db.add(breakdown)

    data = payload.model_dump(exclude_unset=True)
    if data.get("optimized_content") is not None:
        breakdown.optimized_content = data["optimized_content"]
    if data.get("characters") is not None:
        breakdown.characters = data["characters"]
    if data.get("group_photo_prompt") is not None:
        breakdown.group_photo_prompt = data["group_photo_prompt"]

    _touch_source(breakdown, story)
    # 故事画风有效时刷新快照：重跑拆解换画风后，旧快照随之更新
    if style is not None:
        breakdown.art_style_id = style["id"]
        breakdown.art_style_name = style["name"]
        breakdown.art_style_content = style["content"]

    db.commit()
    db.refresh(breakdown)
    return _to_breakdown_read(breakdown, story, style)


@router.post(
    "/{story_id}/breakdown/analyze",
    response_model=StoryOptimizationAnalysis,
)
def analyze_optimization(
    story_id: int,
    force: bool = Query(
        default=False,
        description="为 true 时忽略缓存，强制重新调用模型",
    ),
    db: Session = Depends(get_db),
) -> StoryOptimizationAnalysis:
    """调用 DeepSeek 解读原文到优化文的改动。

    原文与优化文由服务端读取，避免前端重复传输长文本；
    Key 仅在服务端使用，不会下发浏览器。

    解读结果按「原文 + 优化文」的哈希缓存：内容未变时直接返回，
    不重复消耗模型额度；force=true 用于用户主动「重新解读」。
    """
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None or not breakdown.optimized_content.strip():
        raise AppError(
            404,
            "该故事还没有优化后文章，请先完成拆解",
            "BREAKDOWN_NOT_FOUND",
        )

    original_content = story.content.strip()
    optimized_content = breakdown.optimized_content.strip()
    if not original_content:
        raise AppError(422, "故事原文为空，无法对比", "STORY_CONTENT_EMPTY")

    total_chars = len(original_content) + len(optimized_content)
    if total_chars > MAX_OPTIMIZE_ANALYZE_INPUT_CHARS:
        raise AppError(
            422,
            f"原文与优化文合计 {total_chars} 字，超过 AI 解读上限 "
            f"{MAX_OPTIMIZE_ANALYZE_INPUT_CHARS} 字，请直接查看逐字对比",
            "OPTIMIZE_ANALYZE_TOO_LONG",
        )

    # 原文与优化文都没变时直接复用上次结果，避免重复调用模型
    input_hash = _analysis_hash(original_content, optimized_content)
    if (
        not force
        and breakdown.analysis_cache
        and breakdown.analysis_input_hash == input_hash
    ):
        return StoryOptimizationAnalysis.model_validate(
            breakdown.analysis_cache
        )

    api_key, _, _ = resolve_deepseek_key(db)
    story_name = story.name
    # 外部 HTTP 请求期间不持有数据库事务（与 posts.py / settings.py 一致）
    db.rollback()

    if api_key is None:
        raise AppError(
            409,
            "尚未配置 DeepSeek API Key，请先到「设置」页面完成配置",
            "DEEPSEEK_KEY_MISSING",
        )

    result = analyze_optimization_changes(
        api_key, story_name, original_content, optimized_content
    )

    # 解读成功后落库缓存；下次内容不变时直接读取，不再产生模型调用
    breakdown.analysis_cache = result.model_dump()
    breakdown.analysis_input_hash = input_hash
    db.commit()
    return result


@router.put(
    "/{story_id}/breakdown/pages/{page_number}",
    response_model=StoryboardPageRead,
)
def upsert_page(
    story_id: int,
    payload: StoryboardPagePayload,
    page_number: int = Path(ge=1, le=MAX_BREAKDOWN_PAGES),
    db: Session = Depends(get_db),
) -> StoryboardPageRead:
    """写入单页分镜：同页码覆盖，不存在则追加，天然幂等。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(
            404,
            "该故事还没有拆解结果，请先写入优化后文章与角色设定卡",
            "BREAKDOWN_NOT_FOUND",
        )

    page = {"page_number": page_number, **payload.model_dump()}
    pages = [
        item
        for item in breakdown.pages
        if item.get("page_number") != page_number
    ]
    pages.append(page)
    pages.sort(key=lambda item: item.get("page_number", 0))
    breakdown.pages = pages
    _touch_source(breakdown, story)
    db.commit()
    db.refresh(breakdown)
    return StoryboardPageRead.model_validate(page)


@router.delete(
    "/{story_id}/breakdown/pages/{page_number}", status_code=204
)
def delete_page(
    story_id: int,
    page_number: int = Path(ge=1, le=MAX_BREAKDOWN_PAGES),
    db: Session = Depends(get_db),
) -> Response:
    """删除单页；页码不存在时同样返回 204，便于重复清理。"""
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")

    remaining = [
        item
        for item in breakdown.pages
        if item.get("page_number") != page_number
    ]
    if len(remaining) != len(breakdown.pages):
        breakdown.pages = remaining
        db.commit()
    return Response(status_code=204)


@router.delete("/{story_id}/breakdown/pages", status_code=204)
def clear_pages(
    story_id: int, db: Session = Depends(get_db)
) -> Response:
    """清空全部分镜页，保留优化文、人设卡与合影提示词。"""
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")

    if breakdown.pages:
        breakdown.pages = []
        db.commit()
    return Response(status_code=204)


@router.delete("/{story_id}/breakdown", status_code=204)
def delete_breakdown(
    story_id: int, db: Session = Depends(get_db)
) -> Response:
    """清空整份拆解结果；不存在时返回 204，便于重复清理。"""
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is not None:
        db.delete(breakdown)
        db.commit()
    return Response(status_code=204)
