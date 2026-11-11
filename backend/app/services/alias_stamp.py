"""图片别名水印：原地在底部居中写入【别名】，并保留可恢复的原图备份。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ..errors import AppError

# 优先使用可商用的中文字体；Windows 自带字体只作为本机回退。
FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)

# 字号 / 底边距按画面宽度、高度自适应
FONT_SIZE_RATIO = 0.037
BOTTOM_RATIO = 0.982
STROKE_WIDTH = 2


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size=size, index=0)
        except OSError:
            continue
    raise AppError(
        500,
        "没有找到可用的中文字体，无法给图片加别名",
        "ALIAS_FONT_MISSING",
    )


def _save_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return "JPEG"
    if suffix == ".webp":
        return "WEBP"
    return "PNG"


def _atomic_save(image: Image.Image, path: Path) -> None:
    fmt = _save_format(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}-", suffix=path.suffix, dir=path.parent
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        if fmt == "JPEG":
            image.convert("RGB").save(
                temp_path, format="JPEG", quality=95, optimize=True
            )
        elif fmt == "WEBP":
            image.convert("RGB").save(
                temp_path, format="WEBP", quality=95, method=6
            )
        else:
            image.save(temp_path, format="PNG", optimize=True)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def alias_backup_root(upload_dir: Path, story_id: int) -> Path:
    """别名水印备份根目录：uploads/alias-backups/<故事ID>。"""
    return upload_dir.parent / "alias-backups" / str(story_id)


def backup_path_for(
    upload_dir: Path, backup_root: Path, image_path: Path
) -> Path:
    """备份目录保持 uploads 下的相对结构，便于整故事恢复。"""
    relative = image_path.resolve().relative_to(upload_dir.resolve())
    return backup_root / relative


def stamped_alias(
    image_path: Path,
    *,
    upload_dir: Path,
    backup_root: Path,
    current_hash: str | None = None,
) -> str | None:
    """图片当前内容是否就是某别名加过水印的版本；返回该别名或 None。

    只读：不修改图片、不写备份。只能识别本工作台生成的水印，
    外部工具加的别名会返回 None，不会误判为已加。
    """
    try:
        backup = backup_path_for(upload_dir, backup_root, image_path)
    except (OSError, ValueError):
        return None
    meta = _read_meta(backup)
    stamped_hash = str(meta.get("stamped_sha256") or "")
    alias = str(meta.get("alias") or "")
    if not stamped_hash or not alias:
        return None
    if current_hash is None:
        if not image_path.is_file():
            return None
        current_hash = _sha256(image_path)
    return alias if current_hash == stamped_hash else None


def _meta_path(backup: Path) -> Path:
    return backup.with_name(f"{backup.name}.alias.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_meta(backup: Path) -> dict:
    path = _meta_path(backup)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_meta(
    backup: Path, *, original_hash: str, stamped_hash: str, alias: str
) -> None:
    path = _meta_path(backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "original_sha256": original_hash,
        "stamped_sha256": stamped_hash,
        "alias": alias,
        "stamped_at": datetime.now(timezone.utc).isoformat(),
    }
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temp, path)


def _replace_with(source: Path, target: Path) -> None:
    """原子复制，用于把新换的图重新作为备份原图。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.stem}-", suffix=target.suffix, dir=target.parent
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)


def stamp_alias(
    image_path: Path,
    alias: str,
    *,
    upload_dir: Path,
    backup_root: Path,
) -> Path:
    """在图片底部居中写【别名】；第一次处理前先备份原图。

    每次都从备份原图重新合成，因此换别名不会把文字叠两层；
    备份不存在时才把当前文件当作原图备份。
    """
    if not image_path.is_file():
        raise AppError(404, "图片不存在", "IMAGE_NOT_FOUND")

    backup = backup_path_for(upload_dir, backup_root, image_path)
    current_hash = _sha256(image_path)

    if not backup.is_file():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, backup)
    else:
        meta = _read_meta(backup)
        stamped_hash = str(meta.get("stamped_sha256") or "")
        # 图片在加字之后被替换/编辑过：把当前文件当作新的原图重新备份，
        # 避免下一次加字又把旧备份顶回新图。
        if current_hash != stamped_hash:
            if not stamped_hash or current_hash != _sha256(backup):
                _replace_with(image_path, backup)
    source = backup
    original_hash = _sha256(source)

    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
        width, height = image.size
        font = _load_font(max(22, int(width * FONT_SIZE_RATIO)))
        text = f"【{alias}】"

        probe = ImageDraw.Draw(image)
        bbox = probe.textbbox((0, 0), text, font=font, stroke_width=STROKE_WIDTH)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = int(height * BOTTOM_RATIO) - text_height

        # 轻阴影：保证浅色背景上也能看清，不额外加黑底遮挡画面。
        shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.text(
            (x + 2, y + 3),
            text,
            font=font,
            fill=(0, 0, 0, 170),
            stroke_width=STROKE_WIDTH,
            stroke_fill=(0, 0, 0, 170),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(3))
        image = Image.alpha_composite(image, shadow)

        draw = ImageDraw.Draw(image)
        draw.text(
            (x, y),
            text,
            font=font,
            fill=(255, 255, 255, 245),
            stroke_width=STROKE_WIDTH,
            stroke_fill=(0, 0, 0, 210),
        )

    _atomic_save(image, image_path)
    _write_meta(
        backup,
        original_hash=original_hash,
        stamped_hash=_sha256(image_path),
        alias=alias,
    )
    return image_path


def restore_alias(
    image_path: Path,
    *,
    upload_dir: Path,
    backup_root: Path,
) -> bool:
    """从备份恢复原图；没有备份时返回 False。"""
    backup = backup_path_for(upload_dir, backup_root, image_path)
    if not backup.is_file():
        return False
    image_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{image_path.stem}-", suffix=image_path.suffix, dir=image_path.parent
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        shutil.copy2(backup, temp_path)
        os.replace(temp_path, image_path)
    finally:
        temp_path.unlink(missing_ok=True)
    _meta_path(backup).unlink(missing_ok=True)
    return True
