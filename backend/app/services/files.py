"""封面与分镜成品图的校验、存储与删除。"""

from __future__ import annotations

import io
import logging
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import UploadFile

from ..config import (
    CHARACTER_ASSET_FILENAME_PATTERN,
    MAX_PAGE_IMAGE_BYTES,
    MAX_UPLOAD_BYTES,
)
from ..errors import AppError

logger = logging.getLogger("comic_workbench")

# 服务端生成的封面文件名：32 位十六进制 + 规范扩展名
COVER_FILENAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")

# 允许的扩展名 -> 规范图片类型
_EXTENSION_TO_TYPE = {
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
    ".webp": "webp",
}

# 分镜成品图按「故事 ID + 页码」落在固定路径：pages/<story_id>/page-<页码>.<ext>
# 绑定关系由文件是否存在决定，不写进数据库；重跑拆解后同页码自动挂回
PAGE_IMAGE_EXTENSIONS = ("jpg", "png", "webp")


def detect_image_type(head: bytes) -> str | None:
    """通过文件头 magic bytes 判断图片类型（imghdr 在 Python 3.13 已移除）。"""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _validate_and_read_image(
    upload: UploadFile, max_bytes: int
) -> tuple[str, bytes]:
    """校验扩展名 + magic bytes 并读入全部字节，返回 (规范类型, 内容)。

    安全策略：扩展名白名单与文件内容双重校验、按实际读取字节数硬限制
    （不信任 Content-Length）。
    """
    original_name = Path(upload.filename or "").name
    extension = Path(original_name).suffix.lower()
    expected_type = _EXTENSION_TO_TYPE.get(extension)
    if expected_type is None:
        raise AppError(422, "仅支持 JPG、PNG、WebP 格式的图片", "INVALID_IMAGE_TYPE")

    head = upload.file.read(16) or b""
    actual_type = detect_image_type(head)
    if actual_type is None:
        raise AppError(422, "文件内容不是有效的 JPG、PNG 或 WebP 图片", "INVALID_IMAGE_TYPE")
    if actual_type != expected_type:
        raise AppError(422, "文件扩展名与图片内容不一致", "IMAGE_TYPE_MISMATCH")

    data = bytearray(head)
    while True:
        chunk = upload.file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise AppError(
                413,
                f"图片大小不能超过 {max_bytes // (1024 * 1024)}MB",
                "FILE_TOO_LARGE",
            )
    if not data:
        raise AppError(422, "上传文件为空", "EMPTY_FILE")
    return actual_type, bytes(data)


def _write_atomic(target: Path, data: bytes) -> None:
    """先写临时文件再原子替换，避免中断时留下半个文件。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(target.name + ".tmp")
    temp_path.write_bytes(data)
    temp_path.replace(target)


def save_cover(upload: UploadFile, upload_dir: Path) -> tuple[str, str]:
    """校验并保存封面，返回 (文件名, 访问 URL)。"""
    actual_type, data = _validate_and_read_image(upload, MAX_UPLOAD_BYTES)
    filename = f"{uuid.uuid4().hex}.{actual_type}"
    _write_atomic(upload_dir / filename, data)
    return filename, f"/uploads/{filename}"


def validate_cover_filename(filename: str | None, upload_dir: Path) -> None:
    """校验故事提交的封面文件名确实由本服务生成且文件存在。"""
    if filename is None:
        return
    if not COVER_FILENAME_PATTERN.fullmatch(filename):
        raise AppError(422, "封面文件名不合法", "INVALID_COVER_FILENAME")
    if not (upload_dir / filename).is_file():
        raise AppError(422, "封面文件不存在，请重新上传", "COVER_FILE_NOT_FOUND")


def delete_cover_file(filename: str | None, upload_dir: Path) -> None:
    """删除封面文件；失败只记录日志，不影响已提交的数据库操作。"""
    if not filename or not COVER_FILENAME_PATTERN.fullmatch(filename):
        return
    try:
        (upload_dir / filename).unlink(missing_ok=True)
    except OSError:
        logger.warning("删除封面文件失败: %s", filename, exc_info=True)


# ---------- 分镜成品图 ----------


_PAGE_FILENAME_PATTERN = re.compile(
    r"^page-(\d{1,4})\.(jpg|png|webp)$"
)


def _page_root(upload_dir: Path, story_id: int) -> Path:
    return upload_dir / "pages" / str(story_id)


def _page_image_name(
    page_number: int, extension: str, padded: bool = True
) -> str:
    # 章节目录内用四位页码，文件管理器按名称排序时不会乱序
    prefix = f"{page_number:04d}" if padded else str(page_number)
    return f"page-{prefix}.{extension}"


def _page_image_path(
    upload_dir: Path,
    story_id: int,
    page_number: int,
    extension: str,
    chapter_number: int | None = None,
) -> Path:
    root = _page_root(upload_dir, story_id)
    if chapter_number is not None:
        return (
            root
            / f"chapter-{chapter_number}"
            / _page_image_name(page_number, extension)
        )
    # 未分章的历史数据仍放在故事根目录
    return root / _page_image_name(page_number, extension, padded=False)


def _page_image_files(
    upload_dir: Path, story_id: int, page_number: int
) -> list[Path]:
    """列出该页所有已存在的图片（章节目录 + 旧平铺目录、全部扩展名）。"""
    root = _page_root(upload_dir, story_id)
    if not root.is_dir():
        return []

    names: set[str] = set()
    for extension in PAGE_IMAGE_EXTENSIONS:
        names.add(_page_image_name(page_number, extension, padded=False))
        names.add(_page_image_name(page_number, extension))

    found: list[Path] = []
    for name in names:
        flat = root / name
        if flat.is_file():
            found.append(flat)
        for chapter_dir in root.glob("chapter-*"):
            if chapter_dir.is_dir():
                candidate = chapter_dir / name
                if candidate.is_file():
                    found.append(candidate)
    return found


def _upload_url(upload_dir: Path, path: Path) -> str:
    return f"/uploads/{path.relative_to(upload_dir).as_posix()}"


def page_chapter_number(
    page: dict, chapters: list[dict] | None
) -> int | None:
    """解析页面所属章节：优先页面自身字段，其次按对照段反查章节。"""
    chapter_number = page.get("chapter_number")
    if chapter_number is not None:
        return chapter_number
    mapping_number = page.get("mapping_page_number")
    for chapter in chapters or []:
        if mapping_number in (chapter.get("mapping_page_numbers") or []):
            return chapter.get("chapter_number")
    return None


def page_image_url(
    upload_dir: Path, story_id: int, page_number: int
) -> str | None:
    """该页已有成品图时返回访问 URL，否则返回 None。

    兼容两种布局：章节目录 chapter-N/page-XXXX.ext 与旧平铺 page-X.ext。
    绑定关系完全由文件是否存在决定，重跑拆解后同页码的图会自动挂回。
    """
    files = _page_image_files(upload_dir, story_id, page_number)
    if not files:
        return None
    # 章节布局优先；同页存在多份时取排序后的第一份
    files.sort(
        key=lambda path: (
            0 if path.parent.name.startswith("chapter-") else 1,
            str(path),
        )
    )
    return _upload_url(upload_dir, files[0])


def save_page_image(
    upload: UploadFile,
    upload_dir: Path,
    story_id: int,
    page_number: int,
    chapter_number: int | None = None,
) -> str:
    """保存某页的成品图并返回访问 URL；同页重复上传时覆盖旧图。

    成品图来自生图 AI，体积可能明显大于封面，单独使用 15MB 上限。
    """
    actual_type, data = _validate_and_read_image(upload, MAX_PAGE_IMAGE_BYTES)
    # 先清掉该页所有旧图（旧平铺 / 其他章节目录 / 其他扩展名）
    for old in _page_image_files(upload_dir, story_id, page_number):
        try:
            old.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "删除旧分镜成品图失败: story=%s page=%s",
                story_id,
                page_number,
                exc_info=True,
            )
    target = _page_image_path(
        upload_dir, story_id, page_number, actual_type, chapter_number
    )
    _write_atomic(target, data)
    _prune_empty_chapter_dirs(upload_dir, story_id)
    return _upload_url(upload_dir, target)


def delete_page_image(
    upload_dir: Path, story_id: int, page_number: int
) -> None:
    """删除某页的成品图；不存在时静默返回，保持幂等。"""
    for path in _page_image_files(upload_dir, story_id, page_number):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "删除分镜成品图失败: story=%s page=%s",
                story_id,
                page_number,
                exc_info=True,
            )
    _prune_empty_chapter_dirs(upload_dir, story_id)


def _prune_empty_chapter_dirs(upload_dir: Path, story_id: int) -> None:
    root = _page_root(upload_dir, story_id)
    if not root.is_dir():
        return
    for directory in root.glob("chapter-*"):
        if not directory.is_dir():
            continue
        try:
            if not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            logger.warning(
                "清理空章节图片目录失败: story=%s dir=%s",
                story_id,
                directory,
                exc_info=True,
            )


def organize_page_images(
    upload_dir: Path,
    story_id: int,
    pages: list[dict],
    chapters: list[dict] | None = None,
) -> None:
    """把已上传的页图移动到对应的章节目录：pages/<故事>/chapter-N/page-XXXX.ext。

    章节重新规划、页面写回、服务启动时都会调用；重复执行是安全的。
    """
    root = _page_root(upload_dir, story_id)
    if not root.is_dir():
        return

    mapping_to_chapter: dict[int, int] = {}
    for chapter in chapters or []:
        for mapping_number in chapter.get("mapping_page_numbers") or []:
            mapping_to_chapter[mapping_number] = chapter.get("chapter_number")

    pages_by_number = {
        page.get("page_number"): page
        for page in pages
        if page.get("page_number") is not None
    }
    moved = 0
    for path in list(root.rglob("page-*.*")):
        if not path.is_file():
            continue
        matched = _PAGE_FILENAME_PATTERN.fullmatch(path.name)
        if matched is None:
            continue
        page_number = int(matched.group(1))
        extension = matched.group(2)
        page = pages_by_number.get(page_number, {})
        chapter_number = page.get("chapter_number")
        if chapter_number is None:
            chapter_number = mapping_to_chapter.get(
                page.get("mapping_page_number")
            )
        if chapter_number is None:
            continue

        target = _page_image_path(
            upload_dir, story_id, page_number, extension, chapter_number
        )
        if path == target:
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                path.unlink(missing_ok=True)
            else:
                path.replace(target)
            moved += 1
        except OSError:
            logger.warning(
                "整理分镜成品图失败: story=%s page=%s",
                story_id,
                page_number,
                exc_info=True,
            )

    _prune_empty_chapter_dirs(upload_dir, story_id)
    if moved:
        logger.info(
            "已把 %s 张分镜成品图归入章节目录: story=%s", moved, story_id
        )


def delete_story_page_images(upload_dir: Path, story_id: int) -> None:
    """删除故事的全部成品图目录；失败只记录日志，不阻塞主流程。"""
    try:
        shutil.rmtree(upload_dir / "pages" / str(story_id), ignore_errors=True)
    except OSError:
        logger.warning("删除故事成品图目录失败: story=%s", story_id, exc_info=True)


# ---------- 章节封面 / 引导卡 ----------

# 章节资产与正文成品图分开存放：清空正文页时不能误删已做好的封面和引导卡。
# 路径：chapters/<story_id>/chapter-<章节号>-<cover|guide>.<ext>
CHAPTER_ASSET_KINDS = ("cover", "guide")


def _chapter_asset_path(
    upload_dir: Path,
    story_id: int,
    chapter_number: int,
    kind: str,
    extension: str,
) -> Path:
    return (
        upload_dir
        / "chapters"
        / str(story_id)
        / f"chapter-{chapter_number}-{kind}.{extension}"
    )


def chapter_asset_url(
    upload_dir: Path,
    story_id: int,
    chapter_number: int,
    kind: str,
) -> str | None:
    """章节封面 / 引导卡已有图时返回访问 URL，否则返回 None。"""
    if kind not in CHAPTER_ASSET_KINDS:
        return None
    for extension in PAGE_IMAGE_EXTENSIONS:
        if _chapter_asset_path(
            upload_dir, story_id, chapter_number, kind, extension
        ).is_file():
            return (
                f"/uploads/chapters/{story_id}/"
                f"chapter-{chapter_number}-{kind}.{extension}"
            )
    return None


def save_chapter_asset(
    upload: UploadFile,
    upload_dir: Path,
    story_id: int,
    chapter_number: int,
    kind: str,
) -> str:
    """保存章节封面 / 引导卡；同一章节同类型重复上传覆盖旧图。"""
    if kind not in CHAPTER_ASSET_KINDS:
        raise AppError(422, "不支持的章节图片类型", "INVALID_CHAPTER_ASSET_KIND")
    actual_type, data = _validate_and_read_image(upload, MAX_PAGE_IMAGE_BYTES)
    for extension in PAGE_IMAGE_EXTENSIONS:
        if extension != actual_type:
            _chapter_asset_path(
                upload_dir, story_id, chapter_number, kind, extension
            ).unlink(missing_ok=True)
    target = _chapter_asset_path(
        upload_dir, story_id, chapter_number, kind, actual_type
    )
    _write_atomic(target, data)
    return (
        f"/uploads/chapters/{story_id}/"
        f"chapter-{chapter_number}-{kind}.{actual_type}"
    )


def delete_chapter_asset(
    upload_dir: Path,
    story_id: int,
    chapter_number: int,
    kind: str,
) -> None:
    """删除章节封面 / 引导卡；不存在时静默返回。"""
    if kind not in CHAPTER_ASSET_KINDS:
        return
    for extension in PAGE_IMAGE_EXTENSIONS:
        try:
            _chapter_asset_path(
                upload_dir, story_id, chapter_number, kind, extension
            ).unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "删除章节图片失败: story=%s chapter=%s kind=%s",
                story_id,
                chapter_number,
                kind,
                exc_info=True,
            )


def delete_story_chapter_assets(upload_dir: Path, story_id: int) -> None:
    """删除故事的全部章节封面 / 引导卡。"""
    try:
        shutil.rmtree(upload_dir / "chapters" / str(story_id), ignore_errors=True)
    except OSError:
        logger.warning(
            "删除故事章节图片目录失败: story=%s", story_id, exc_info=True
        )


# ---------- 角色资产图 ----------

# 每个角色一张资产图：character-assets/<story_id>/<uuid>.<ext>
# 文件名写进角色卡的 asset_filename，与角色名解耦，改名不会丢图


def _character_asset_dir(upload_dir: Path, story_id: int) -> Path:
    return upload_dir / "character-assets" / str(story_id)


def character_asset_url(
    upload_dir: Path, story_id: int, filename: str | None
) -> str | None:
    """角色资产图的访问 URL；文件不存在或文件名不合法时返回 None。"""
    if not filename or not CHARACTER_ASSET_FILENAME_PATTERN.fullmatch(filename):
        return None
    if not (_character_asset_dir(upload_dir, story_id) / filename).is_file():
        return None
    return f"/uploads/character-assets/{story_id}/{filename}"


def save_character_asset(
    upload: UploadFile,
    upload_dir: Path,
    story_id: int,
    old_filename: str | None = None,
) -> str:
    """保存角色资产图并返回文件名；替换时删除旧图。"""
    actual_type, data = _validate_and_read_image(upload, MAX_PAGE_IMAGE_BYTES)
    filename = f"{uuid.uuid4().hex}.{actual_type}"
    _write_atomic(_character_asset_dir(upload_dir, story_id) / filename, data)
    if old_filename:
        delete_character_asset(upload_dir, story_id, old_filename)
    return filename


def delete_character_asset(
    upload_dir: Path, story_id: int, filename: str | None
) -> None:
    """删除角色资产图；文件名不合法或文件不存在时静默返回。"""
    if not filename or not CHARACTER_ASSET_FILENAME_PATTERN.fullmatch(filename):
        return
    try:
        (_character_asset_dir(upload_dir, story_id) / filename).unlink(
            missing_ok=True
        )
    except OSError:
        logger.warning(
            "删除角色资产图失败: story=%s file=%s",
            story_id,
            filename,
            exc_info=True,
        )


def delete_story_character_assets(upload_dir: Path, story_id: int) -> None:
    """删除故事的全部角色资产图；失败只记录日志，不阻塞主流程。"""
    try:
        shutil.rmtree(
            _character_asset_dir(upload_dir, story_id), ignore_errors=True
        )
    except OSError:
        logger.warning(
            "删除角色资产图目录失败: story=%s", story_id, exc_info=True
        )


# ---------- 人物合照 ----------

# 最终确认的人物合照按「故事 ID」落在固定路径：group-photos/<story_id>.<ext>
# 与分镜成品图一致：绑定关系由文件是否存在决定，不写进数据库；
# 一个故事只有一张合照，重复上传直接覆盖旧图


def _group_photo_path(upload_dir: Path, story_id: int, extension: str) -> Path:
    return upload_dir / "group-photos" / f"{story_id}.{extension}"


def group_photo_url(upload_dir: Path, story_id: int) -> str | None:
    """该故事已有合照时返回访问 URL，否则返回 None。"""
    for extension in PAGE_IMAGE_EXTENSIONS:
        if _group_photo_path(upload_dir, story_id, extension).is_file():
            return f"/uploads/group-photos/{story_id}.{extension}"
    return None


def save_group_photo(upload: UploadFile, upload_dir: Path, story_id: int) -> str:
    """保存人物合照并返回访问 URL；重复上传时覆盖旧图。

    合照同样来自生图 AI，与分镜成品图共用 15MB 上限。
    """
    actual_type, data = _validate_and_read_image(upload, MAX_PAGE_IMAGE_BYTES)
    # 先清掉其他扩展名的旧图，保证一个故事只有一份合照
    for extension in PAGE_IMAGE_EXTENSIONS:
        if extension != actual_type:
            _group_photo_path(upload_dir, story_id, extension).unlink(
                missing_ok=True
            )
    target = _group_photo_path(upload_dir, story_id, actual_type)
    _write_atomic(target, data)
    return f"/uploads/group-photos/{story_id}.{actual_type}"


def delete_group_photo(upload_dir: Path, story_id: int) -> None:
    """删除人物合照；不存在时静默返回，保持幂等。"""
    for extension in PAGE_IMAGE_EXTENSIONS:
        try:
            _group_photo_path(upload_dir, story_id, extension).unlink(
                missing_ok=True
            )
        except OSError:
            logger.warning("删除人物合照失败: story=%s", story_id, exc_info=True)


# ---------- 章节图片导出 ----------

# 导出时按「第N章_标题/序号_名称.ext」组织，序号按小红书发布顺序：
# 01 封面 → 02.. 正文（章内页码顺序）→ 最后一张引导卡
_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')


def _safe_filename_part(value: str, fallback: str) -> str:
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", (value or "").strip())
    cleaned = cleaned.strip(" .")
    return cleaned or fallback


def _upload_url_to_path(upload_dir: Path, url: str | None) -> Path | None:
    """把 /uploads/... 访问地址还原成本地文件路径，并防止越出上传目录。"""
    if not url or not url.startswith("/uploads/"):
        return None
    try:
        path = (upload_dir / url[len("/uploads/") :]).resolve()
        path.relative_to(upload_dir.resolve())
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def build_chapter_images_zip(
    upload_dir: Path,
    story_name: str,
    chapters: list[dict],
    pages: list[dict],
    only_chapter: int | None = None,
) -> tuple[bytes, str] | None:
    """把章节图片打包成 ZIP，按章节分文件夹、按发布顺序编号。

    返回 (zip 字节, 下载文件名)；没有任何图片时返回 None。
    """
    pages_by_mapping = {
        page.get("mapping_page_number"): page
        for page in pages
        if page.get("mapping_page_number") is not None
    }
    selected = [
        chapter
        for chapter in sorted(
            chapters, key=lambda item: item.get("chapter_number", 0)
        )
        if only_chapter is None
        or chapter.get("chapter_number") == only_chapter
    ]

    buffer = io.BytesIO()
    written = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for chapter in selected:
            number = chapter.get("chapter_number")
            title = _safe_filename_part(
                chapter.get("title", ""), f"第{number}章"
            )
            folder = f"第{number}章_{title}"
            entries: list[tuple[str, str]] = []

            cover_url = (chapter.get("cover") or {}).get("image_url")
            if cover_url:
                entries.append(("封面", cover_url))

            for mapping_number in chapter.get("mapping_page_numbers") or []:
                page = pages_by_mapping.get(mapping_number)
                if page and page.get("image_url"):
                    entries.append(
                        (
                            f"第{page.get('chapter_page_number')}页",
                            page["image_url"],
                        )
                    )

            guide_url = (chapter.get("guide") or {}).get("image_url")
            if guide_url:
                entries.append(("引导卡", guide_url))

            for index, (label, url) in enumerate(entries, start=1):
                path = _upload_url_to_path(upload_dir, url)
                if path is None:
                    continue
                archive.write(
                    path,
                    f"{folder}/{index:02d}_{label}{path.suffix.lower()}",
                )
                written += 1

    if written == 0:
        return None

    story_part = _safe_filename_part(story_name, "故事")
    if only_chapter is not None:
        chapter = next(
            (
                item
                for item in selected
                if item.get("chapter_number") == only_chapter
            ),
            None,
        )
        chapter_title = _safe_filename_part(
            (chapter or {}).get("title", ""), f"第{only_chapter}章"
        )
        filename = f"{story_part}_第{only_chapter}章_{chapter_title}.zip"
    else:
        filename = f"{story_part}_章节图片.zip"
    return buffer.getvalue(), filename
