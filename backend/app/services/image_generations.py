"""生图历史与正式图提交。

生成结果先写入 image-history/<故事>/<目标类型>/<id>.<ext>；
只有用户确认后才复制到角色资产图 / 章节封面 / 分镜图的正式路径。
清除历史只删除历史目录与记录，不影响正式图。
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    IMAGE_HISTORY_DIR,
    IMAGE_HISTORY_MAX_ITEMS,
    MAX_IMAGE_REFERENCES,
    MAX_PAGE_IMAGE_BYTES,
)
from ..errors import AppError
from ..models import ImageGeneration, StoryBreakdown
from .files import (
    _chapter_asset_path,
    _page_image_files,
    character_asset_path,
    character_asset_url,
    chapter_asset_url,
    detect_image_type,
    page_image_url,
    save_chapter_asset_bytes,
    save_character_asset_bytes,
    save_page_image_bytes,
)

logger = logging.getLogger("comic_workbench")

TARGET_TYPES = ("character_asset", "chapter_cover", "chapter_guide", "page")


@dataclass(slots=True)
class GenerationTarget:
    target_type: str
    character_name: str | None = None
    chapter_number: int | None = None
    page_number: int | None = None

    def validate(self) -> None:
        if self.target_type not in TARGET_TYPES:
            raise AppError(422, "不支持的生图目标", "INVALID_IMAGE_TARGET")
        if self.target_type == "character_asset" and not self.character_name:
            raise AppError(422, "角色生图必须指定角色名", "INVALID_IMAGE_TARGET")
        if self.target_type in ("chapter_cover", "chapter_guide") and not self.chapter_number:
            raise AppError(422, "章节生图必须指定章节号", "INVALID_IMAGE_TARGET")
        if self.target_type == "page" and not self.page_number:
            raise AppError(422, "分镜生图必须指定页码", "INVALID_IMAGE_TARGET")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _history_root(upload_dir: Path, story_id: int) -> Path:
    return upload_dir / IMAGE_HISTORY_DIR / str(story_id)


def _history_path(
    upload_dir: Path, story_id: int, target_type: str, generation_id: str, extension: str
) -> Path:
    return _history_root(upload_dir, story_id) / target_type / f"{generation_id}.{extension}"


def history_url(row: ImageGeneration) -> str:
    return f"/uploads/{row.filename}"


def save_generation(
    db: Session,
    upload_dir: Path,
    story_id: int,
    target: GenerationTarget,
    *,
    model: str,
    size: str,
    quality: str,
    prompt: str,
    reference_names: list[str],
    data: bytes,
    extension: str,
    sha256: str,
    elapsed_ms: int,
    request_id: str | None,
) -> ImageGeneration:
    """把生成结果写入历史目录并记录；不触碰正式图。"""
    target.validate()
    if len(data) > MAX_PAGE_IMAGE_BYTES:
        raise AppError(413, "生成图片超过大小上限", "FILE_TOO_LARGE")
    generation_id = uuid.uuid4().hex
    path = _history_path(upload_dir, story_id, target.target_type, generation_id, extension)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    row = ImageGeneration(
        id=generation_id,
        story_id=story_id,
        target_type=target.target_type,
        character_name=target.character_name,
        chapter_number=target.chapter_number,
        page_number=target.page_number,
        model=model,
        size=size,
        quality=quality,
        prompt=prompt,
        reference_names=reference_names,
        filename=path.relative_to(upload_dir).as_posix(),
        file_bytes=len(data),
        sha256=sha256,
        status="generated",
        provider_request_id=request_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def target_matches(row: ImageGeneration, target: GenerationTarget) -> bool:
    if row.target_type != target.target_type:
        return False
    if target.character_name is not None and row.character_name != target.character_name:
        return False
    if target.chapter_number is not None and row.chapter_number != target.chapter_number:
        return False
    if target.page_number is not None and row.page_number != target.page_number:
        return False
    return True


def _current_path(
    upload_dir: Path,
    story_id: int,
    breakdown: StoryBreakdown | None,
    target: GenerationTarget,
) -> Path | None:
    if target.target_type == "character_asset":
        card = next(
            (
                item
                for item in (breakdown.characters or [])
                if item.get("name") == target.character_name
            ),
            None,
        )
        return character_asset_path(
            upload_dir, story_id, (card or {}).get("asset_filename")
        )
    if target.target_type in ("chapter_cover", "chapter_guide"):
        kind = "cover" if target.target_type == "chapter_cover" else "guide"
        for extension in ("jpg", "png", "webp"):
            path = _chapter_asset_path(
                upload_dir, story_id, target.chapter_number or 0, kind, extension
            )
            if path.is_file():
                return path
        return None
    if target.target_type == "page":
        files = _page_image_files(upload_dir, story_id, target.page_number or 0)
        return files[0] if files else None
    return None


def _current_url(
    upload_dir: Path,
    story_id: int,
    breakdown: StoryBreakdown | None,
    target: GenerationTarget,
) -> str | None:
    if target.target_type == "character_asset":
        card = next(
            (
                item
                for item in (breakdown.characters or [])
                if item.get("name") == target.character_name
            ),
            None,
        )
        return character_asset_url(
            upload_dir, story_id, (card or {}).get("asset_filename")
        )
    if target.target_type in ("chapter_cover", "chapter_guide"):
        kind = "cover" if target.target_type == "chapter_cover" else "guide"
        return chapter_asset_url(
            upload_dir, story_id, target.chapter_number or 0, kind
        )
    if target.target_type == "page":
        return page_image_url(upload_dir, story_id, target.page_number or 0)
    return None


def _sha256_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_generations(
    db: Session,
    upload_dir: Path,
    story_id: int,
    target: GenerationTarget,
    breakdown: StoryBreakdown | None,
) -> tuple[list[dict], int]:
    """列出目标的历史记录；is_current 通过正式图哈希判断。"""
    target.validate()
    rows = db.scalars(
        select(ImageGeneration)
        .where(
            ImageGeneration.story_id == story_id,
            ImageGeneration.target_type == target.target_type,
        )
        .order_by(ImageGeneration.created_at.desc())
        .limit(IMAGE_HISTORY_MAX_ITEMS)
    ).all()
    current_hash = _sha256_file(_current_path(upload_dir, story_id, breakdown, target))
    items: list[dict] = []
    total_bytes = 0
    for row in rows:
        if not target_matches(row, target):
            continue
        path = upload_dir / row.filename
        if not path.is_file():
            continue
        total_bytes += row.file_bytes
        items.append(
            {
                "id": row.id,
                "target_type": row.target_type,
                "url": history_url(row),
                "created_at": row.created_at,
                "model": row.model,
                "size": row.size,
                "file_bytes": row.file_bytes,
                "used_at": row.used_at,
                "is_current": bool(current_hash and row.sha256 == current_hash),
                "prompt": row.prompt or "",
                "reference_names": row.reference_names or [],
            }
        )
    return items, total_bytes


def current_url(
    upload_dir: Path,
    story_id: int,
    breakdown: StoryBreakdown | None,
    target: GenerationTarget,
) -> str | None:
    return _current_url(upload_dir, story_id, breakdown, target)


def _archive_chapter_asset(
    upload_dir: Path, story_id: int, chapter_number: int, kind: str
) -> None:
    """覆盖前把旧封面 / 引导卡复制到归档目录。"""
    stamp = _now().strftime("%Y%m%d%H%M%S")
    for extension in ("jpg", "png", "webp"):
        source = _chapter_asset_path(
            upload_dir, story_id, chapter_number, kind, extension
        )
        if not source.is_file():
            continue
        target_dir = upload_dir / "chapters-archive" / str(story_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            source,
            target_dir / f"chapter-{chapter_number}-{kind}-{stamp}.{extension}",
        )


def commit_generation(
    db: Session,
    upload_dir: Path,
    story_id: int,
    breakdown: StoryBreakdown,
    row: ImageGeneration,
) -> None:
    """把历史图复制到正式路径；角色资产图写回角色卡。"""
    path = upload_dir / row.filename
    if not path.is_file():
        raise AppError(404, "历史图片文件不存在，可能已被清理", "IMAGE_HISTORY_NOT_FOUND")
    data = path.read_bytes()
    if len(data) > MAX_PAGE_IMAGE_BYTES:
        raise AppError(413, "历史图片超过大小上限", "FILE_TOO_LARGE")
    extension = detect_image_type(data[:16])
    if extension is None:
        raise AppError(422, "历史文件不是有效图片", "INVALID_IMAGE_TYPE")

    if row.target_type == "character_asset":
        characters = list(breakdown.characters or [])
        index = next(
            (
                position
                for position, item in enumerate(characters)
                if item.get("name") == row.character_name
            ),
            None,
        )
        if index is None:
            raise AppError(404, "角色卡不存在", "CHARACTER_NOT_FOUND")
        card = dict(characters[index])
        card["asset_filename"] = save_character_asset_bytes(
            data, upload_dir, story_id, card.get("asset_filename")
        )
        characters[index] = card
        breakdown.characters = characters
    elif row.target_type in ("chapter_cover", "chapter_guide"):
        kind = "cover" if row.target_type == "chapter_cover" else "guide"
        save_chapter_asset_bytes(
            data,
            upload_dir,
            story_id,
            row.chapter_number or 0,
            kind,
            filename=f"generated.{extension}",
            content_type=f"image/{extension}",
        )
    elif row.target_type == "page":
        save_page_image_bytes(
            data,
            upload_dir,
            story_id,
            row.page_number or 0,
            row.chapter_number,
            filename=f"generated.{extension}",
            content_type=f"image/{extension}",
        )
    else:
        raise AppError(422, "不支持的生图目标", "INVALID_IMAGE_TARGET")

    row.status = "used"
    row.used_at = _now()
    db.commit()


def _safe_unlink(upload_dir: Path, filename: str) -> int:
    """只删除历史目录内的文件，返回释放字节数。"""
    root = (upload_dir / IMAGE_HISTORY_DIR).resolve()
    path = (upload_dir / filename).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return 0
    size = path.stat().st_size
    path.unlink(missing_ok=True)
    return size


def clear_generations(
    db: Session,
    upload_dir: Path,
    story_id: int,
    target: GenerationTarget,
) -> tuple[int, int]:
    """清空目标的历史文件与记录；正式图不受影响。"""
    target.validate()
    rows = db.scalars(
        select(ImageGeneration).where(
            ImageGeneration.story_id == story_id,
            ImageGeneration.target_type == target.target_type,
        )
    ).all()
    deleted = 0
    freed = 0
    for row in rows:
        if not target_matches(row, target):
            continue
        freed += _safe_unlink(upload_dir, row.filename)
        db.delete(row)
        deleted += 1
    db.commit()
    return deleted, freed


def delete_generation(
    db: Session, upload_dir: Path, story_id: int, generation_id: str
) -> int:
    row = db.get(ImageGeneration, generation_id)
    if row is None or row.story_id != story_id:
        raise AppError(404, "生图记录不存在", "IMAGE_HISTORY_NOT_FOUND")
    freed = _safe_unlink(upload_dir, row.filename)
    db.delete(row)
    db.commit()
    return freed


def delete_story_history(upload_dir: Path, story_id: int) -> None:
    """删除故事的全部历史文件；失败只记录日志。"""
    try:
        shutil.rmtree(_history_root(upload_dir, story_id), ignore_errors=True)
    except OSError:
        logger.warning("删除生图历史目录失败: story=%s", story_id, exc_info=True)
