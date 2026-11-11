"""图片别名水印接口：原地批量加字，并从备份恢复。"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import AppError
from ..schemas import (
    AliasRestoreResult,
    AliasStampItem,
    AliasStampRequest,
    AliasStampResult,
)
from ..services.alias_stamp import (
    alias_backup_root,
    restore_alias,
    stamp_alias,
)
from ..services.files import (
    chapter_asset_url,
    page_image_url,
    upload_url_to_path,
)
from .breakdowns import _get_breakdown, _get_story_or_404

router = APIRouter(prefix="/api/stories", tags=["图片别名"])

ALIAS_PATTERN = re.compile(r"[一-鿿]{6,8}")
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _acquire_lock(story_id: int) -> threading.Lock:
    with _locks_guard:
        lock = _locks.setdefault(story_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise AppError(
            409, "这个故事的图片正在处理中，请稍后重试", "ALIAS_STAMP_IN_PROGRESS"
        )
    return lock


def _alias_for(story, payload: AliasStampRequest) -> str:
    alias = (payload.alias or story.zhihu_alias or "").strip()
    if not alias:
        raise AppError(
            422,
            "请先在「知乎推广」中填写最终别名，或在请求里传 alias",
            "ZHIHU_ALIAS_REQUIRED",
        )
    if not ALIAS_PATTERN.fullmatch(alias):
        raise AppError(
            422,
            "别名必须是 6–8 个汉字，不能包含字母、数字、标点或空格",
            "INVALID_ZHIHU_ALIAS",
        )
    return alias


def _targets(
    story_id: int,
    breakdown,
    upload_dir: Path,
    payload: AliasStampRequest,
) -> list[dict]:
    """按封面 → 正文页 → 引导卡的发布顺序收集目标图片。"""
    pages = {page.get("page_number"): page for page in (breakdown.pages or [])}
    chapters = sorted(
        breakdown.chapters or [], key=lambda item: item.get("chapter_number", 0)
    )
    targets: list[dict] = []

    if payload.page_numbers is not None:
        for page_number in sorted(set(payload.page_numbers)):
            page = pages.get(page_number)
            if page is None:
                targets.append(
                    {
                        "target": "page",
                        "page_number": page_number,
                        "chapter_number": None,
                        "url": None,
                        "error": f"第 {page_number} 页不存在",
                    }
                )
                continue
            targets.append(
                {
                    "target": "page",
                    "page_number": page_number,
                    "chapter_number": page.get("chapter_number"),
                    "url": page_image_url(upload_dir, story_id, page_number),
                }
            )
        return targets

    requested = set(
        payload.chapter_numbers
        or (
            []
            if payload.chapter_number is None
            else [payload.chapter_number]
        )
    )
    selected = [
        chapter
        for chapter in chapters
        if not requested or chapter.get("chapter_number") in requested
    ]

    if selected:
        for chapter in selected:
            chapter_number = chapter.get("chapter_number")
            cover_url = chapter_asset_url(
                upload_dir, story_id, chapter_number, "cover"
            )
            if cover_url:
                targets.append(
                    {
                        "target": "cover",
                        "chapter_number": chapter_number,
                        "page_number": None,
                        "url": cover_url,
                    }
                )
            for mapping_number in chapter.get("mapping_page_numbers") or []:
                page = next(
                    (
                        item
                        for item in (breakdown.pages or [])
                        if item.get("mapping_page_number") == mapping_number
                    ),
                    None,
                )
                if page is None:
                    continue
                page_number = page.get("page_number")
                url = page_image_url(upload_dir, story_id, page_number)
                if url:
                    targets.append(
                        {
                            "target": "page",
                            "chapter_number": chapter_number,
                            "page_number": page_number,
                            "url": url,
                        }
                    )
            guide_url = chapter_asset_url(
                upload_dir, story_id, chapter_number, "guide"
            )
            if guide_url:
                targets.append(
                    {
                        "target": "guide",
                        "chapter_number": chapter_number,
                        "page_number": None,
                        "url": guide_url,
                    }
                )
        return targets

    # 还没有章节规划时，处理全部有图的正文页。
    if requested:
        return []
    for page_number in sorted(pages):
        url = page_image_url(upload_dir, story_id, page_number)
        if url:
            targets.append(
                {
                    "target": "page",
                    "chapter_number": pages[page_number].get("chapter_number"),
                    "page_number": page_number,
                    "url": url,
                }
            )
    return targets


@router.post(
    "/{story_id}/alias-stamp",
    response_model=AliasStampResult,
    summary="批量给图片底部加别名",
    description=(
        "原地覆盖正文页 / 章节封面 / 引导卡，在底部居中写【别名】。"
        "首次处理前会把原图备份到 uploads/alias-backups/<故事ID>/，"
        "可通过 /alias-stamp/restore 恢复。"
    ),
)
def stamp_story_alias(
    story_id: int,
    payload: AliasStampRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AliasStampResult:
    story = _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    alias = _alias_for(story, payload)
    upload_dir = request.app.state.app_settings.upload_dir
    targets = _targets(story_id, breakdown, upload_dir, payload)
    if not targets:
        raise AppError(404, "没有找到可加别名的图片", "NO_IMAGES")

    lock = _acquire_lock(story_id)
    backup_root = alias_backup_root(upload_dir, story_id)
    items: list[AliasStampItem] = []
    try:
        for target in targets:
            url = target.get("url")
            if not url:
                items.append(
                    AliasStampItem(
                        target=target["target"],
                        chapter_number=target.get("chapter_number"),
                        page_number=target.get("page_number"),
                        ok=False,
                        error=target.get("error") or "该目标还没有成品图",
                    )
                )
                continue
            path = upload_url_to_path(upload_dir, url)
            if path is None:
                items.append(
                    AliasStampItem(
                        target=target["target"],
                        chapter_number=target.get("chapter_number"),
                        page_number=target.get("page_number"),
                        ok=False,
                        error="图片文件不存在",
                    )
                )
                continue
            try:
                stamp_alias(
                    path,
                    alias,
                    upload_dir=upload_dir,
                    backup_root=backup_root,
                )
                items.append(
                    AliasStampItem(
                        target=target["target"],
                        chapter_number=target.get("chapter_number"),
                        page_number=target.get("page_number"),
                        ok=True,
                    )
                )
            except AppError as exc:
                items.append(
                    AliasStampItem(
                        target=target["target"],
                        chapter_number=target.get("chapter_number"),
                        page_number=target.get("page_number"),
                        ok=False,
                        error=exc.message,
                    )
                )
    finally:
        lock.release()

    stamped = sum(1 for item in items if item.ok)
    return AliasStampResult(
        alias=alias,
        stamped=stamped,
        failed=len(items) - stamped,
        items=items,
        backup_dir=f"backend/alias-backups/{story_id}",
    )


@router.post(
    "/{story_id}/alias-stamp/restore",
    response_model=AliasRestoreResult,
    summary="从备份恢复加过别名的图片",
)
def restore_story_alias(
    story_id: int,
    payload: AliasStampRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AliasRestoreResult:
    _get_story_or_404(db, story_id)
    breakdown = _get_breakdown(db, story_id)
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    upload_dir = request.app.state.app_settings.upload_dir
    targets = _targets(story_id, breakdown, upload_dir, payload)
    if not targets:
        raise AppError(404, "没有找到可恢复的图片", "NO_IMAGES")

    lock = _acquire_lock(story_id)
    backup_root = alias_backup_root(upload_dir, story_id)
    items: list[AliasStampItem] = []
    try:
        for target in targets:
            url = target.get("url")
            path = upload_url_to_path(upload_dir, url)
            if path is None:
                items.append(
                    AliasStampItem(
                        target=target["target"],
                        chapter_number=target.get("chapter_number"),
                        page_number=target.get("page_number"),
                        ok=False,
                        error="图片文件不存在",
                    )
                )
                continue
            ok = restore_alias(
                path, upload_dir=upload_dir, backup_root=backup_root
            )
            items.append(
                AliasStampItem(
                    target=target["target"],
                    chapter_number=target.get("chapter_number"),
                    page_number=target.get("page_number"),
                    ok=ok,
                    error=None if ok else "没有找到原图备份",
                )
            )
    finally:
        lock.release()

    restored = sum(1 for item in items if item.ok)
    return AliasRestoreResult(
        restored=restored,
        failed=len(items) - restored,
        items=items,
    )
