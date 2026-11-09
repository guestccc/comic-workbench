"""生图接口：角色资产图、章节封面、历史与提交。"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..config import MAX_IMAGE_REFERENCES
from ..crud import get_start_prompt
from ..database import get_db
from ..errors import AppError
from ..models import ImageGeneration
from ..schemas import (
    CharacterAssetGenerateRequest,
    ImageGenerationClearResult,
    ImageGenerationList,
    ImageGenerationPreview,
    ImageGenerationTarget,
    StoryBreakdownRead,
)
from ..services.files import (
    character_asset_path,
    character_asset_url,
    chapter_asset_url,
    detect_image_type,
)
from ..services.image_generations import (
    GenerationTarget,
    clear_generations,
    commit_generation,
    delete_generation,
    history_url,
    list_generations,
    save_generation,
)
from ..services.image_prompts import (
    build_character_sheet_prompt,
    build_provider_prompt,
    build_reference_prompt,
    extract_character_names,
)
from ..services.image_provider import (
    ReferenceImage,
    generate_image,
    resolve_image_provider,
)
from .breakdowns import (
    _get_breakdown,
    _get_chapter_or_404,
    _get_story_or_404,
    _resolve_story_style,
    _to_breakdown_read,
)

router = APIRouter(prefix="/api/stories", tags=["生图"])

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _acquire_lock(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        raise AppError(409, "这个目标正在生成中，请等待当前任务完成", "GENERATION_IN_PROGRESS")
    return lock


def _target(
    target_type: str,
    character_name: str | None,
    chapter_number: int | None,
    page_number: int | None,
) -> GenerationTarget:
    target = GenerationTarget(
        target_type=target_type,
        character_name=character_name,
        chapter_number=chapter_number,
        page_number=page_number,
    )
    target.validate()
    return target


def _style_for(breakdown, style: dict[str, str] | None) -> tuple[str, str]:
    name = (style or {}).get("name") or breakdown.art_style_name
    content = (style or {}).get("content") or breakdown.art_style_content
    if not name or not content:
        raise AppError(
            409,
            "故事还没有有效画风，请先到故事管理中选择画风",
            "ART_STYLE_REQUIRED",
        )
    return name, content


def _load_references(
    breakdown,
    upload_dir,
    names: list[str],
) -> list[ReferenceImage]:
    if len(names) > MAX_IMAGE_REFERENCES:
        raise AppError(
            422,
            f"单次最多使用 {MAX_IMAGE_REFERENCES} 张角色参考图",
            "TOO_MANY_REFERENCES",
        )
    cards = {card.get("name"): card for card in (breakdown.characters or [])}
    missing: list[str] = []
    references: list[ReferenceImage] = []
    for name in names:
        card = cards.get(name)
        if card is None:
            missing.append(name)
            continue
        path = character_asset_path(
            upload_dir, breakdown.story_id, card.get("asset_filename")
        )
        if path is None:
            missing.append(name)
            continue
        data = path.read_bytes()
        extension = detect_image_type(data[:16])
        if extension is None:
            missing.append(name)
            continue
        references.append(
            ReferenceImage(
                name=name,
                data=data,
                content_type=f"image/{extension}",
                extension=extension,
            )
        )
    if missing:
        raise AppError(
            409,
            "以下角色还没有资产图，请先在角色卡生成资产图："
            + "、".join(missing),
            "CHARACTER_ASSET_MISSING",
        )
    return references


def _preview(
    row,
    target: GenerationTarget,
    old_url: str | None,
    elapsed_ms: int,
) -> ImageGenerationPreview:
    return ImageGenerationPreview(
        generation_id=row.id,
        target_type=target.target_type,  # type: ignore[arg-type]
        old_url=old_url,
        new_url=history_url(row),
        model=row.model,
        size=row.size,
        elapsed_ms=elapsed_ms,
    )


@router.post(
    "/{story_id}/character-assets/generate",
    response_model=ImageGenerationPreview,
)
def generate_character_asset(
    story_id: int,
    payload: CharacterAssetGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ImageGenerationPreview:
    """生成角色三视角设定图；结果先入历史，不直接替换资产图。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    card = next(
        (
            item
            for item in (breakdown.characters or [])
            if item.get("name") == payload.character_name
        ),
        None,
    )
    if card is None:
        raise AppError(404, "角色卡不存在", "CHARACTER_NOT_FOUND")

    style = _resolve_story_style(db, story)
    style_name, style_content = _style_for(breakdown, style)
    upload_dir = request.app.state.app_settings.upload_dir
    target = _target("character_asset", payload.character_name, None, None)
    lock = _acquire_lock(f"{story_id}:character_asset:{payload.character_name}")
    try:
        config = resolve_image_provider(db)
        start_prompt, _ = get_start_prompt(db)
        prompt = build_character_sheet_prompt(
            style_name=style_name,
            style_content=style_content,
            name=payload.character_name,
            appearance=str(card.get("appearance") or ""),
        )
        prompt = build_provider_prompt(
            prompt,
            start_prompt=start_prompt,
            story_name=story.name or "",
            story_content=story.content or "",
            style_name=style_name,
            style_content=style_content,
        )
        generated = generate_image(config, prompt)
        row = save_generation(
            db,
            upload_dir,
            story_id,
            target,
            model=config.model,
            size=config.size,
            quality=config.quality,
            prompt=prompt,
            reference_names=[],
            data=generated.data,
            extension=generated.extension,
            sha256=generated.sha256,
            elapsed_ms=generated.elapsed_ms,
            request_id=generated.request_id,
        )
        old_url = character_asset_url(
            upload_dir, story_id, card.get("asset_filename")
        )
        return _preview(row, target, old_url, generated.elapsed_ms)
    finally:
        lock.release()


@router.post(
    "/{story_id}/breakdown/chapters/{chapter_number}/cover/generate",
    response_model=ImageGenerationPreview,
)
def generate_chapter_cover(
    story_id: int,
    request: Request,
    chapter_number: int,
    db: Session = Depends(get_db),
) -> ImageGenerationPreview:
    """生成章节封面；必须使用提示词中的角色资产图作为参考图。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    chapter = _get_chapter_or_404(breakdown, chapter_number)
    prompt = str((chapter.get("cover") or {}).get("image_prompt") or "").strip()
    if not prompt:
        raise AppError(409, "章节封面还没有生图提示词", "IMAGE_PROMPT_EMPTY")
    names = extract_character_names(prompt)
    if not names:
        raise AppError(
            409,
            "封面提示词里没有 {{角色名}} 变量，无法使用角色资产图垫图",
            "CHARACTER_REFERENCE_REQUIRED",
        )

    style = _resolve_story_style(db, story)
    style_name, style_content = _style_for(breakdown, style)
    upload_dir = request.app.state.app_settings.upload_dir
    references = _load_references(breakdown, upload_dir, names)
    target = _target("chapter_cover", None, chapter_number, None)
    lock = _acquire_lock(f"{story_id}:chapter_cover:{chapter_number}")
    try:
        config = resolve_image_provider(db)
        mapped_prompt = build_reference_prompt(prompt, names)
        start_prompt, _ = get_start_prompt(db)
        mapped_prompt = build_provider_prompt(
            mapped_prompt,
            start_prompt=start_prompt,
            story_name=story.name or "",
            story_content=story.content or "",
            style_name=style_name,
            style_content=style_content,
        )
        generated = generate_image(config, mapped_prompt, references)
        row = save_generation(
            db,
            upload_dir,
            story_id,
            target,
            model=config.model,
            size=config.size,
            quality=config.quality,
            prompt=mapped_prompt,
            reference_names=names,
            data=generated.data,
            extension=generated.extension,
            sha256=generated.sha256,
            elapsed_ms=generated.elapsed_ms,
            request_id=generated.request_id,
        )
        old_url = chapter_asset_url(upload_dir, story_id, chapter_number, "cover")
        return _preview(row, target, old_url, generated.elapsed_ms)
    finally:
        lock.release()


@router.get("/{story_id}/image-generations", response_model=ImageGenerationList)
def read_image_generations(
    story_id: int,
    request: Request,
    target_type: ImageGenerationTarget = Query(...),
    character_name: str | None = Query(default=None),
    chapter_number: int | None = Query(default=None, ge=1),
    page_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> ImageGenerationList:
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    target = _target(target_type, character_name, chapter_number, page_number)
    items, total_bytes = list_generations(
        db,
        request.app.state.app_settings.upload_dir,
        story_id,
        target,
        breakdown,
    )
    return ImageGenerationList(items=items, total_bytes=total_bytes)


@router.post(
    "/{story_id}/image-generations/{generation_id}/use",
    response_model=StoryBreakdownRead,
)
def use_image_generation(
    story_id: int,
    generation_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> StoryBreakdownRead:
    """使用历史图：复制到正式路径，不重新调用生图接口。"""
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    row = db.get(ImageGeneration, generation_id)
    if row is None or row.story_id != story_id:
        raise AppError(404, "生图记录不存在", "IMAGE_HISTORY_NOT_FOUND")
    upload_dir = request.app.state.app_settings.upload_dir
    target = _target(
        row.target_type,
        row.character_name,
        row.chapter_number,
        row.page_number,
    )
    lock = _acquire_lock(f"{story_id}:use:{generation_id}")
    try:
        commit_generation(db, upload_dir, story_id, breakdown, row)
    finally:
        lock.release()
    return _to_breakdown_read(
        breakdown, story, _resolve_story_style(db, story), upload_dir
    )


@router.delete(
    "/{story_id}/image-generations", response_model=ImageGenerationClearResult
)
def clear_image_generations(
    story_id: int,
    request: Request,
    target_type: ImageGenerationTarget = Query(...),
    character_name: str | None = Query(default=None),
    chapter_number: int | None = Query(default=None, ge=1),
    page_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> ImageGenerationClearResult:
    """清空目标的历史文件；当前正式图不受影响。"""
    _get_story_or_404(db, story_id)
    target = _target(target_type, character_name, chapter_number, page_number)
    deleted, freed = clear_generations(
        db, request.app.state.app_settings.upload_dir, story_id, target
    )
    return ImageGenerationClearResult(deleted=deleted, freed_bytes=freed)


@router.delete("/{story_id}/image-generations/{generation_id}", status_code=204)
def remove_image_generation(
    story_id: int,
    generation_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    _get_story_or_404(db, story_id)
    delete_generation(
        db, request.app.state.app_settings.upload_dir, story_id, generation_id
    )
    return Response(status_code=204)
