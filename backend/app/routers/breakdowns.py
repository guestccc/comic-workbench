"""故事拆解结果接口：优化后文章、角色设定卡与分镜页。

``group_photo_prompt`` 是旧流程字段，新流程不再写入，保留仅为兼容旧数据。


拆解本身由 Claude Code 技能完成，本模块只负责结果读写。
一个故事只有一份拆解结果；分镜页存放在 JSON 列中，按 page_number 排序。
"""

from __future__ import annotations

import hashlib
from pathlib import Path as FsPath
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Path, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    MAX_BREAKDOWN_PAGES,
    MAX_CHAPTERS,
    MAX_OPTIMIZE_ANALYZE_INPUT_CHARS,
)
from ..crud import get_art_styles, resolve_deepseek_key
from ..database import get_db
from ..errors import AppError
from ..models import Story, StoryBreakdown
from ..schemas import (
    ChapterCoverOptimizeRequest,
    ChapterCoverOptimizeResult,
    CharacterCard,
    CharacterCardRead,
    CharacterOptimizeRequest,
    CharacterSyncRequest,
    CharacterSyncResult,
    StoryboardChapterRead,
    StoryboardMappingItem,
    StoryboardPagePayload,
    StoryboardPageRead,
    StoryBreakdownRead,
    StoryBreakdownUpdate,
    StoryOptimizationAnalysis,
)
from ..services.deepseek import (
    analyze_optimization_changes,
    optimize_chapter_cover as generate_chapter_cover_optimization,
    stream_character_optimization,
    sync_character_reviews,
)
from ..services.files import (
    build_chapter_images_zip,
    chapter_asset_url,
    character_asset_url,
    delete_chapter_asset,
    delete_character_asset,
    delete_group_photo,
    delete_page_image,
    delete_story_chapter_assets,
    delete_story_character_assets,
    delete_story_page_images,
    group_photo_url,
    organize_page_images,
    page_chapter_number,
    page_image_url,
    save_chapter_asset,
    save_character_asset,
    save_group_photo,
    save_page_image,
)
from ..services.prompts import validate_prompt_page_number

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


def _mapping_structure(mapping: list[dict]) -> list[tuple[int, str, bool]]:
    """对照表结构签名：只关心段号、原文摘录与弃用标记。"""
    return [
        (
            item.get("page_number"),
            item.get("source_text") or "",
            bool(item.get("excluded")),
        )
        for item in mapping
    ]


def _chapter_structure(chapters: list[dict]) -> list[tuple[int, tuple[int, ...]]]:
    """章节结构签名：只关心章号与对照段分配，文字修改不算结构变化。"""
    return [
        (
            chapter.get("chapter_number"),
            tuple(chapter.get("mapping_page_numbers") or []),
        )
        for chapter in chapters
    ]


def _validate_chapters(chapters: list[dict], mapping: list[dict]) -> None:
    """章节必须按对照表顺序覆盖全部未弃用段，不重不漏。

    允许 chapters=[] 关闭章节模式；一旦配置章节，就必须完整覆盖，
    避免出现章节之间漏段、跳段或跨章重复。
    """
    if not chapters:
        return

    mapping_numbers = [item.get("page_number") for item in mapping]
    excluded = {
        item.get("page_number") for item in mapping if item.get("excluded")
    }
    active = [number for number in mapping_numbers if number not in excluded]
    ordered: list[int] = []

    for index, chapter in enumerate(chapters, start=1):
        if chapter.get("chapter_number") != index:
            raise AppError(
                422, "章节号必须从 1 连续编号", "CHAPTER_NUMBER_INVALID"
            )
        for number in chapter.get("mapping_page_numbers") or []:
            if number in excluded:
                raise AppError(
                    422,
                    f"对照第 {number} 段已标记弃用，不能分入章节",
                    "CHAPTER_USES_EXCLUDED_PAGE",
                )
            if number not in mapping_numbers:
                raise AppError(
                    422,
                    f"对照第 {number} 段不在分镜对照表中",
                    "CHAPTER_MAPPING_NOT_FOUND",
                )
            if number in ordered:
                raise AppError(
                    422,
                    f"对照第 {number} 段被多个章节使用",
                    "CHAPTER_MAPPING_DUPLICATED",
                )
            ordered.append(number)

    if ordered != active:
        raise AppError(
            422,
            "章节必须按对照表顺序覆盖全部未弃用段落，不重不漏",
            "CHAPTER_COVERAGE_INVALID",
        )


def _get_chapter_or_404(
    breakdown: StoryBreakdown, chapter_number: int
) -> dict:
    for chapter in breakdown.chapters or []:
        if chapter.get("chapter_number") == chapter_number:
            return chapter
    raise AppError(404, "章节不存在", "CHAPTER_NOT_FOUND")


def _to_breakdown_read(
    breakdown: StoryBreakdown,
    story: Story,
    style: dict[str, str] | None,
    upload_dir: FsPath,
) -> StoryBreakdownRead:
    """组装响应模型，并计算原文 / 画风的过期标记与每页成品图地址。"""
    pages = sorted(
        (
            StoryboardPageRead.model_validate(page)
            for page in (breakdown.pages or [])
        ),
        key=lambda page: page.page_number,
    )
    # 成品图绑定由文件系统决定：uploads/pages/<story_id>/page-<页码>.<ext> 存在即已完成
    for page in pages:
        page.display_page_number = (
            page.chapter_page_number or page.page_number
        )
        page.image_url = page_image_url(
            upload_dir, breakdown.story_id, page.page_number
        )

    # 角色资产图同理：文件名存在数据库里，访问地址按文件是否存在计算
    characters: list[CharacterCardRead] = []
    for card in (breakdown.characters or []):
        item = CharacterCardRead.model_validate(card)
        item.asset_url = character_asset_url(
            upload_dir, breakdown.story_id, item.asset_filename
        )
        characters.append(item)

    mapping = [
        StoryboardMappingItem.model_validate(item)
        for item in (breakdown.mapping or [])
    ]

    chapters: list[StoryboardChapterRead] = []
    for item in breakdown.chapters or []:
        chapter = StoryboardChapterRead.model_validate(item)
        chapter.cover.image_url = chapter_asset_url(
            upload_dir,
            breakdown.story_id,
            chapter.chapter_number,
            "cover",
        )
        chapter.guide.image_url = chapter_asset_url(
            upload_dir,
            breakdown.story_id,
            chapter.chapter_number,
            "guide",
        )
        chapters.append(chapter)

    return StoryBreakdownRead(
        id=breakdown.id,
        story_id=breakdown.story_id,
        optimized_content=breakdown.optimized_content,
        characters=characters,
        group_photo_prompt=breakdown.group_photo_prompt,
        # 合照绑定由文件系统决定：uploads/group-photos/<story_id>.<ext> 存在即有图
        group_photo_url=group_photo_url(upload_dir, breakdown.story_id),
        mapping=mapping,
        chapters=chapters,
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
    story_id: int, request: Request, db: Session = Depends(get_db)
) -> StoryBreakdownRead | None:
    """读取拆解结果；尚未拆解时返回 null，前端按空态展示。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        return None
    return _to_breakdown_read(
        breakdown,
        story,
        _resolve_story_style(db, story),
        request.app.state.app_settings.upload_dir,
    )


@router.patch("/{story_id}/breakdown", response_model=StoryBreakdownRead)
def update_breakdown(
    story_id: int,
    payload: StoryBreakdownUpdate,
    request: Request,
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
        # 角色卡整体替换时按名称继承资产图：重新拆解 / 编辑卡片不会丢图。
        # 原有资产图中不再被引用的文件顺手删除，避免留下孤儿文件。
        old_cards = {
            card.get("name"): card for card in (breakdown.characters or [])
        }
        old_assets = {
            card.get("asset_filename")
            for card in (breakdown.characters or [])
            if card.get("asset_filename")
        }
        new_cards: list[dict] = []
        kept_assets: set[str] = set()
        for card in data["characters"]:
            if not card.get("asset_filename"):
                old = old_cards.get(card["name"])
                if old and old.get("asset_filename"):
                    card["asset_filename"] = old["asset_filename"]
            if card.get("asset_filename"):
                kept_assets.add(card["asset_filename"])
            new_cards.append(card)
        breakdown.characters = new_cards
        upload_dir = request.app.state.app_settings.upload_dir
        for stray in old_assets - kept_assets:
            delete_character_asset(upload_dir, story_id, stray)
    if data.get("mapping") is not None:
        # 对照表变了会改变页面来源；已有正文页时禁止直接替换，先清空页面。
        if (
            breakdown.pages
            and _mapping_structure(data["mapping"])
            != _mapping_structure(breakdown.mapping or [])
        ):
            raise AppError(
                409,
                "已有正文分镜页，修改分镜对照前请先清空分镜页面",
                "MAPPING_LOCKED_BY_PAGES",
            )
        # 对照表整体替换；第二步生成脚本时不清空它
        breakdown.mapping = data["mapping"]

    effective_mapping = breakdown.mapping or []
    if data.get("chapters") is not None:
        _validate_chapters(data["chapters"], effective_mapping)
        # 只改标题 / 封面 / 引导卡文字时允许保留页面；
        # 章节号或对照段分配变化会改变页面归属，必须先把正文页清空。
        if (
            breakdown.pages
            and _chapter_structure(breakdown.chapters or [])
            != _chapter_structure(data["chapters"])
        ):
            raise AppError(
                409,
                "已有正文分镜页，重新规划章节前请先清空分镜页面",
                "CHAPTERS_LOCKED_BY_PAGES",
            )
        breakdown.chapters = data["chapters"]
    elif data.get("mapping") is not None and (breakdown.chapters or []):
        # 对照表变了但没同步更新章节：旧章节可能漏段/跳段，直接拒绝
        _validate_chapters(breakdown.chapters, effective_mapping)

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
    upload_dir = request.app.state.app_settings.upload_dir
    if data.get("chapters") is not None:
        # 章节重新规划后，把已有页图移动到新的章节目录
        organize_page_images(
            upload_dir,
            story_id,
            breakdown.pages or [],
            breakdown.chapters or [],
        )
    return _to_breakdown_read(breakdown, story, style, upload_dir)


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


@router.post("/{story_id}/breakdown/characters/optimize")
def optimize_character(
    story_id: int,
    payload: CharacterOptimizeRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """AI 优化角色设定卡的外形描述，以 SSE 流式返回；Key 只在服务端使用。

    用于把用户在生图平台中的形象调整同步回角色卡；本接口只生成文本，
    是否写回由前端在用户确认后通过 PATCH breakdown 完成。
    """
    _get_story_or_404(db, story_id)
    if _get_breakdown(db, story_id) is None:
        raise AppError(
            404,
            "该故事还没有拆解结果，请先运行拆解生成角色卡",
            "BREAKDOWN_NOT_FOUND",
        )

    api_key, _, _ = resolve_deepseek_key(db)
    character_name = payload.character_name
    character_role = payload.character_role
    current_appearance = payload.current_appearance
    messages = [message.model_dump() for message in payload.messages]
    # 流式期间不持有数据库事务（与 settings.py 的提示词 / 画风优化一致）
    db.rollback()

    if api_key is None:
        raise AppError(
            409,
            "尚未配置 DeepSeek API Key，请先到「设置」页面完成配置",
            "DEEPSEEK_KEY_MISSING",
        )

    return StreamingResponse(
        stream_character_optimization(
            api_key,
            character_name,
            character_role,
            current_appearance,
            messages,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _count_chinese_chars(text: str) -> int:
    return sum(1 for char in text if "一" <= char <= "鿿")


@router.post(
    "/{story_id}/breakdown/chapters/{chapter_number}/cover/optimize",
    response_model=ChapterCoverOptimizeResult,
)
def optimize_chapter_cover(
    story_id: int,
    payload: ChapterCoverOptimizeRequest,
    chapter_number: int = Path(ge=1, le=MAX_CHAPTERS),
    db: Session = Depends(get_db),
) -> ChapterCoverOptimizeResult:
    """AI 优化章节封面三项：主标题、副标题、画面提示词。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(
            404,
            "该故事还没有拆解结果，请先完成章节规划",
            "BREAKDOWN_NOT_FOUND",
        )
    chapter = _get_chapter_or_404(breakdown, chapter_number)
    style = _resolve_story_style(db, story)
    if style is None:
        raise AppError(
            422,
            "该故事尚未选择有效画风，请先重新选择画风",
            "ART_STYLE_REQUIRED",
        )

    api_key, _, _ = resolve_deepseek_key(db)
    cover = chapter.get("cover") or {}
    chapter_title = payload.chapter_title or chapter.get("title", "")
    cover_label = payload.cover_label or cover.get("label", "")
    cover_main = payload.cover_main or cover.get("narration_main", "")
    cover_highlight = (
        payload.cover_highlight or cover.get("narration_highlight", "")
    )
    cover_sub = payload.cover_sub or cover.get("narration_sub", "")
    # AI 调用期间不持有数据库事务
    db.rollback()

    if api_key is None:
        raise AppError(
            409,
            "尚未配置 DeepSeek API Key，请先到「设置」页面完成配置",
            "DEEPSEEK_KEY_MISSING",
        )

    result = generate_chapter_cover_optimization(
        api_key,
        story.name or "",
        chapter_title,
        style["name"],
        style["content"],
        cover_label,
        cover_main,
        cover_highlight,
        cover_sub,
        payload.current_prompt,
        payload.suggestion,
    )

    main_count = _count_chinese_chars(result.narration_main)
    sub_count = _count_chinese_chars(result.narration_sub)
    if main_count >= 15:
        raise AppError(
            502,
            f"AI 返回的主标题为 {main_count} 字，超过 15 字，请换个建议重试",
            "AI_COVER_TEXT_INVALID",
        )
    if sub_count >= 35:
        raise AppError(
            502,
            f"AI 返回的副标题为 {sub_count} 字，超过 35 字，请换个建议重试",
            "AI_COVER_TEXT_INVALID",
        )
    if (
        cover_highlight
        and cover_highlight not in result.narration_main
        and cover_highlight not in result.narration_sub
    ):
        raise AppError(
            502,
            f"AI 结果没有保留标红词「{cover_highlight}」，请换个建议重试",
            "AI_COVER_HIGHLIGHT_MISSING",
        )
    if "【页码】" in result.image_prompt:
        raise AppError(
            502,
            "AI 结果意外包含了【页码】，封面不允许页码，请重试",
            "AI_COVER_RESULT_INVALID",
        )
    for required_text, label in (
        (cover_label, "顶部小字"),
        (result.narration_main, "主标题"),
        (result.narration_sub, "副标题"),
    ):
        if required_text and required_text not in result.image_prompt:
            raise AppError(
                502,
                f"AI 返回的画面提示词没有逐字保留{label}，请重试",
                "AI_COVER_RESULT_INVALID",
            )
    return result


@router.post(
    "/{story_id}/breakdown/characters/sync",
    response_model=CharacterSyncResult,
)
def sync_characters(
    story_id: int,
    payload: CharacterSyncRequest,
    db: Session = Depends(get_db),
) -> CharacterSyncResult:
    """同步生图平台返回的新版角色卡，并联动更新分镜「人物回顾」。

    流程：
    1. 按角色名匹配：已存在的整体覆盖外形，不存在的作为新卡追加；
    2. 找出登场角色中包含同步角色的分镜页，调用 DeepSeek 按新外形
       重写这些页的人物回顾（生图提示词用 {{变量}} 引用角色卡，无需改动）；
    3. AI 调用在数据库写入之前完成：调用失败时不落任何改动，避免
       「角色卡更新了但回顾没同步」的中间状态；
    4. 未配置 Key 时只更新角色卡，人物回顾保持原样并在结果中给出提示。
    """
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(
            404,
            "该故事还没有拆解结果，请先运行拆解生成角色卡",
            "BREAKDOWN_NOT_FOUND",
        )

    # 在内存中先算好新角色卡列表与受影响页面，此时不写库
    existing_cards = [CharacterCard.model_validate(card) for card in breakdown.characters]
    cards_by_name = {card.name: card for card in existing_cards}
    updated_names: list[str] = []
    created_names: list[str] = []
    for item in payload.characters:
        card = cards_by_name.get(item.name)
        if card is None:
            card = CharacterCard(name=item.name, role="", appearance=item.appearance)
            cards_by_name[item.name] = card
            existing_cards.append(card)
            created_names.append(item.name)
        else:
            card.appearance = item.appearance
            updated_names.append(item.name)

    synced_names = set(updated_names) | set(created_names)
    # 登场角色中包含任一同步角色的页面，其人物回顾需要重写
    affected_pages = [
        page
        for page in breakdown.pages
        if synced_names & set(page.get("characters", []))
    ]

    api_key, _, _ = resolve_deepseek_key(db)
    # 外部 HTTP 请求期间不持有数据库事务（与 analyze / optimize 一致）
    db.rollback()

    new_reviews: dict[int, str] = {}
    review_warning: str | None = None
    if not affected_pages:
        review_warning = "没有分镜页登场这些角色，人物回顾无需更新"
    elif api_key is None:
        review_warning = (
            "尚未配置 DeepSeek API Key：角色卡已更新，"
            "但分镜人物回顾仍是旧外形，请配置 Key 后重新同步"
        )
    else:
        new_reviews = sync_character_reviews(
            api_key,
            [card.model_dump() for card in existing_cards],
            [
                {
                    "page_number": page.get("page_number"),
                    "characters": page.get("characters", []),
                    "character_review": page.get("character_review", ""),
                }
                for page in affected_pages
            ],
        )

    # AI 成功（或无需调用）后才落库：角色卡 + 人物回顾同一事务提交
    breakdown.characters = [card.model_dump() for card in existing_cards]
    if new_reviews:
        pages = []
        for page in breakdown.pages:
            page_number = page.get("page_number")
            if page_number in new_reviews:
                page = {**page, "character_review": new_reviews[page_number]}
            pages.append(page)
        breakdown.pages = pages
    _touch_source(breakdown, story)
    db.commit()

    return CharacterSyncResult(
        updated_names=updated_names,
        created_names=created_names,
        review_updated_pages=sorted(new_reviews),
        review_warning=review_warning,
    )


@router.put(
    "/{story_id}/breakdown/pages/{page_number}",
    response_model=StoryboardPageRead,
)
def upsert_page(
    story_id: int,
    payload: StoryboardPagePayload,
    request: Request,
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

    existing_page = next(
        (
            item
            for item in breakdown.pages
            if item.get("page_number") == page_number
        ),
        None,
    )
    data = payload.model_dump()
    # 编辑页面的请求可以不携带来源对照段 / 章节信息，此时沿用原值
    if data.get("mapping_page_number") is None and existing_page is not None:
        data["mapping_page_number"] = existing_page.get("mapping_page_number")
    if data.get("chapter_number") is None and existing_page is not None:
        data["chapter_number"] = existing_page.get("chapter_number")
    if data.get("chapter_page_number") is None and existing_page is not None:
        data["chapter_page_number"] = existing_page.get("chapter_page_number")

    mapping_page_number = data.get("mapping_page_number")
    if mapping_page_number is not None:
        mapping_numbers = {
            item.get("page_number") for item in (breakdown.mapping or [])
        }
        if mapping_page_number not in mapping_numbers:
            raise AppError(
                422,
                f"分镜对照表里没有第 {mapping_page_number} 段，无法关联来源",
                "MAPPING_PAGE_NOT_FOUND",
            )
        conflict = next(
            (
                item
                for item in breakdown.pages
                if item.get("page_number") != page_number
                and item.get("mapping_page_number") == mapping_page_number
            ),
            None,
        )
        if conflict is not None:
            raise AppError(
                422,
                f"对照第 {mapping_page_number} 段已关联到脚本第 "
                f"{conflict.get('page_number')} 页，一段不能对应两页",
                "MAPPING_PAGE_DUPLICATED",
            )

    chapter_number = data.get("chapter_number")
    chapter_page_number = data.get("chapter_page_number")
    if chapter_number is not None or chapter_page_number is not None:
        if chapter_number is None or chapter_page_number is None:
            raise AppError(
                422,
                "章节号和章内页码必须同时提供",
                "CHAPTER_PAGE_INCOMPLETE",
            )
        chapter = next(
            (
                item
                for item in (breakdown.chapters or [])
                if item.get("chapter_number") == chapter_number
            ),
            None,
        )
        if chapter is None:
            raise AppError(
                422,
                f"第 {chapter_number} 章不存在，无法写入该页",
                "CHAPTER_NOT_FOUND",
            )
        chapter_mapping_numbers = chapter.get("mapping_page_numbers") or []
        if not (1 <= chapter_page_number <= len(chapter_mapping_numbers)):
            raise AppError(
                422,
                f"第 {chapter_number} 章没有第 {chapter_page_number} 页",
                "CHAPTER_PAGE_OUT_OF_RANGE",
            )
        expected_source = chapter_mapping_numbers[chapter_page_number - 1]
        if data.get("mapping_page_number") != expected_source:
            raise AppError(
                422,
                f"第 {chapter_number} 章第 {chapter_page_number} 页"
                f"应对应对照第 {expected_source} 段",
                "CHAPTER_PAGE_MAPPING_MISMATCH",
            )
        offset = sum(
            len(item.get("mapping_page_numbers") or [])
            for item in (breakdown.chapters or [])
            if item.get("chapter_number", 0) < chapter_number
        )
        expected_page_number = offset + chapter_page_number
        if page_number != expected_page_number:
            raise AppError(
                422,
                f"第 {chapter_number} 章第 {chapter_page_number} 页"
                f"的全局页码应为 {expected_page_number}",
                "CHAPTER_PAGE_NUMBER_MISMATCH",
            )

    # 图片里的页码必须是章内页码；有【页码】分块时禁止写全局页码或对照段号
    expected_display_page = (
        chapter_page_number
        if chapter_page_number is not None
        else page_number
    )
    validate_prompt_page_number(
        data.get("image_prompt", ""), expected_display_page
    )

    page = {"page_number": page_number, **data}
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
    upload_dir = request.app.state.app_settings.upload_dir
    # 页面换了章节时，把已有成品图移动到对应章节目录
    organize_page_images(
        upload_dir, story_id, breakdown.pages or [], breakdown.chapters or []
    )
    read = StoryboardPageRead.model_validate(page)
    read.display_page_number = (
        read.chapter_page_number or read.page_number
    )
    read.image_url = page_image_url(upload_dir, story_id, page_number)
    return read


@router.post(
    "/{story_id}/breakdown/pages/{page_number}/image",
    response_model=StoryboardPageRead,
)
def upload_page_image(
    story_id: int,
    request: Request,
    file: UploadFile = File(...),
    page_number: int = Path(ge=1, le=MAX_BREAKDOWN_PAGES),
    db: Session = Depends(get_db),
) -> StoryboardPageRead:
    """上传某页的成品图；有成品图即视为该页已完成。

    同页重复上传会覆盖旧图；文件按固定路径存储，重跑拆解后同页码自动挂回。
    """
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(
            404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND"
        )
    page = next(
        (
            item
            for item in breakdown.pages
            if item.get("page_number") == page_number
        ),
        None,
    )
    if page is None:
        raise AppError(404, f"第 {page_number} 页不存在", "PAGE_NOT_FOUND")

    upload_dir = request.app.state.app_settings.upload_dir
    chapter_number = page_chapter_number(page, breakdown.chapters or [])
    save_page_image(
        file, upload_dir, story_id, page_number, chapter_number
    )
    read = StoryboardPageRead.model_validate(page)
    read.display_page_number = (
        read.chapter_page_number or read.page_number
    )
    read.image_url = page_image_url(upload_dir, story_id, page_number)
    return read


@router.delete(
    "/{story_id}/breakdown/pages/{page_number}/image", status_code=204
)
def remove_page_image(
    story_id: int,
    request: Request,
    page_number: int = Path(ge=1, le=MAX_BREAKDOWN_PAGES),
    db: Session = Depends(get_db),
) -> Response:
    """删除某页的成品图，取消完成标记；重复删除同样返回 204。"""
    _get_story_or_404(db, story_id)
    if _get_breakdown(db, story_id) is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    delete_page_image(
        request.app.state.app_settings.upload_dir, story_id, page_number
    )
    return Response(status_code=204)


@router.delete(
    "/{story_id}/breakdown/pages/{page_number}", status_code=204
)
def delete_page(
    story_id: int,
    request: Request,
    page_number: int = Path(ge=1, le=MAX_BREAKDOWN_PAGES),
    db: Session = Depends(get_db),
) -> Response:
    """删除单页（连同成品图）；页码不存在时同样返回 204，便于重复清理。"""
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
    delete_page_image(
        request.app.state.app_settings.upload_dir, story_id, page_number
    )
    return Response(status_code=204)


@router.delete("/{story_id}/breakdown/pages", status_code=204)
def clear_pages(
    story_id: int, request: Request, db: Session = Depends(get_db)
) -> Response:
    """清空全部分镜页及其成品图，保留优化文、角色卡与对照表。

    脚本页码会按新的选段重新编号，旧成品图不能继续按页码挂回，
    否则会对应到错误的分镜；因此清空页面时一并清理成品图文件。
    """
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")

    if breakdown.pages:
        breakdown.pages = []
        db.commit()
    delete_story_page_images(request.app.state.app_settings.upload_dir, story_id)
    return Response(status_code=204)


@router.post(
    "/{story_id}/breakdown/chapters/{chapter_number}/cover/image",
    response_model=StoryBreakdownRead,
)
def upload_chapter_cover(
    story_id: int,
    request: Request,
    file: UploadFile = File(...),
    chapter_number: int = Path(ge=1, le=MAX_CHAPTERS),
    db: Session = Depends(get_db),
) -> StoryBreakdownRead:
    """上传章节封面图；重复上传覆盖旧图。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    _get_chapter_or_404(breakdown, chapter_number)

    upload_dir = request.app.state.app_settings.upload_dir
    save_chapter_asset(file, upload_dir, story_id, chapter_number, "cover")
    return _to_breakdown_read(
        breakdown, story, _resolve_story_style(db, story), upload_dir
    )


@router.delete(
    "/{story_id}/breakdown/chapters/{chapter_number}/cover/image",
    status_code=204,
)
def remove_chapter_cover(
    story_id: int,
    request: Request,
    chapter_number: int = Path(ge=1, le=MAX_CHAPTERS),
    db: Session = Depends(get_db),
) -> Response:
    """删除章节封面图；重复删除保持幂等。"""
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    _get_chapter_or_404(breakdown, chapter_number)
    delete_chapter_asset(
        request.app.state.app_settings.upload_dir,
        story_id,
        chapter_number,
        "cover",
    )
    return Response(status_code=204)


@router.post(
    "/{story_id}/breakdown/chapters/{chapter_number}/guide/image",
    response_model=StoryBreakdownRead,
)
def upload_chapter_guide(
    story_id: int,
    request: Request,
    file: UploadFile = File(...),
    chapter_number: int = Path(ge=1, le=MAX_CHAPTERS),
    db: Session = Depends(get_db),
) -> StoryBreakdownRead:
    """上传章节引导卡图；重复上传覆盖旧图。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    _get_chapter_or_404(breakdown, chapter_number)

    upload_dir = request.app.state.app_settings.upload_dir
    save_chapter_asset(file, upload_dir, story_id, chapter_number, "guide")
    return _to_breakdown_read(
        breakdown, story, _resolve_story_style(db, story), upload_dir
    )


@router.delete(
    "/{story_id}/breakdown/chapters/{chapter_number}/guide/image",
    status_code=204,
)
def remove_chapter_guide(
    story_id: int,
    request: Request,
    chapter_number: int = Path(ge=1, le=MAX_CHAPTERS),
    db: Session = Depends(get_db),
) -> Response:
    """删除章节引导卡图；重复删除保持幂等。"""
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    _get_chapter_or_404(breakdown, chapter_number)
    delete_chapter_asset(
        request.app.state.app_settings.upload_dir,
        story_id,
        chapter_number,
        "guide",
    )
    return Response(status_code=204)


def _chapter_images_zip_response(
    story: Story,
    breakdown: StoryBreakdown,
    upload_dir: FsPath,
    style: dict[str, str] | None,
    only_chapter: int | None = None,
) -> Response:
    """把章节图片按「章节文件夹 + 发布顺序」导出为 ZIP。"""
    read = _to_breakdown_read(breakdown, story, style, upload_dir)
    result = build_chapter_images_zip(
        upload_dir,
        story.name,
        [chapter.model_dump() for chapter in read.chapters],
        [page.model_dump() for page in read.pages],
        only_chapter=only_chapter,
    )
    if result is None:
        raise AppError(
            404,
            "本章还没有上传任何图片" if only_chapter is not None
            else "还没有可导出的章节图片",
            "NO_CHAPTER_IMAGES",
        )
    data, filename = result
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                "attachment; filename=\"chapter-images.zip\"; "
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.get("/{story_id}/breakdown/chapters/{chapter_number}/export")
def export_chapter_images(
    story_id: int,
    request: Request,
    chapter_number: int = Path(ge=1, le=MAX_CHAPTERS),
    db: Session = Depends(get_db),
) -> Response:
    """导出单章图片：封面 → 正文（章内页码顺序）→ 引导卡。

    ZIP 内按「第N章_标题/01_封面.png、02_第1页.png …」组织，
    直接解压后按文件名顺序上传小红书即可。
    """
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    _get_chapter_or_404(breakdown, chapter_number)
    return _chapter_images_zip_response(
        story,
        breakdown,
        request.app.state.app_settings.upload_dir,
        _resolve_story_style(db, story),
        only_chapter=chapter_number,
    )


@router.get("/{story_id}/breakdown/export-images")
def export_all_chapter_images(
    story_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """导出全部章节图片，ZIP 内每章一个文件夹。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    return _chapter_images_zip_response(
        story,
        breakdown,
        request.app.state.app_settings.upload_dir,
        _resolve_story_style(db, story),
    )


@router.post(
    "/{story_id}/breakdown/characters/{character_index}/asset-image",
    response_model=StoryBreakdownRead,
)
def upload_character_asset(
    story_id: int,
    request: Request,
    character_index: int = Path(..., ge=0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> StoryBreakdownRead:
    """给单个角色上传资产图；重复上传覆盖旧图。

    资产图只存在本地 uploads 目录，供角色卡展示与对照，
    不参与生图流程，也不影响 {{角色名}} 变量绑定。
    """
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    if character_index >= len(breakdown.characters or []):
        raise AppError(404, "角色卡不存在", "CHARACTER_NOT_FOUND")

    upload_dir = request.app.state.app_settings.upload_dir
    characters = list(breakdown.characters or [])
    card = dict(characters[character_index])
    card["asset_filename"] = save_character_asset(
        file, upload_dir, story_id, card.get("asset_filename")
    )
    characters[character_index] = card
    breakdown.characters = characters
    db.commit()
    db.refresh(breakdown)
    return _to_breakdown_read(
        breakdown, story, _resolve_story_style(db, story), upload_dir
    )


@router.delete(
    "/{story_id}/breakdown/characters/{character_index}/asset-image",
    status_code=204,
)
def remove_character_asset(
    story_id: int,
    request: Request,
    character_index: int = Path(..., ge=0),
    db: Session = Depends(get_db),
) -> Response:
    """删除单个角色的资产图；重复删除返回 204，保持幂等。"""
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    if character_index >= len(breakdown.characters or []):
        raise AppError(404, "角色卡不存在", "CHARACTER_NOT_FOUND")

    characters = list(breakdown.characters or [])
    card = dict(characters[character_index])
    filename = card.get("asset_filename")
    if filename:
        delete_character_asset(
            request.app.state.app_settings.upload_dir, story_id, filename
        )
        card["asset_filename"] = None
        characters[character_index] = card
        breakdown.characters = characters
        db.commit()
    return Response(status_code=204)


@router.post(
    "/{story_id}/breakdown/group-photo", response_model=StoryBreakdownRead
)
def upload_group_photo(
    story_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> StoryBreakdownRead:
    """上传最终确认的人物合照；重复上传覆盖旧图。

    合照只存在本地 uploads 目录，供角色卡 tab 展示与核对，不参与生图流程。
    """
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(
            404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND"
        )

    upload_dir = request.app.state.app_settings.upload_dir
    save_group_photo(file, upload_dir, story_id)
    return _to_breakdown_read(
        breakdown, story, _resolve_story_style(db, story), upload_dir
    )


@router.delete("/{story_id}/breakdown/group-photo", status_code=204)
def remove_group_photo(
    story_id: int, request: Request, db: Session = Depends(get_db)
) -> Response:
    """删除人物合照；重复删除同样返回 204，保持幂等。"""
    _get_story_or_404(db, story_id)
    if _get_breakdown(db, story_id) is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    delete_group_photo(request.app.state.app_settings.upload_dir, story_id)
    return Response(status_code=204)


@router.delete("/{story_id}/breakdown", status_code=204)
def delete_breakdown(
    story_id: int, request: Request, db: Session = Depends(get_db)
) -> Response:
    """清空整份拆解结果（连同成品图、合照与角色资产图）；不存在时返回 204。"""
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is not None:
        db.delete(breakdown)
        db.commit()
    upload_dir = request.app.state.app_settings.upload_dir
    delete_story_page_images(upload_dir, story_id)
    delete_story_chapter_assets(upload_dir, story_id)
    delete_story_character_assets(upload_dir, story_id)
    delete_group_photo(upload_dir, story_id)
    return Response(status_code=204)
