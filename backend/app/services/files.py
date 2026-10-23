"""封面与分镜成品图的校验、存储与删除。"""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from ..config import MAX_PAGE_IMAGE_BYTES, MAX_UPLOAD_BYTES
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


def _page_image_path(
    upload_dir: Path, story_id: int, page_number: int, extension: str
) -> Path:
    return (
        upload_dir / "pages" / str(story_id) / f"page-{page_number}.{extension}"
    )


def page_image_url(
    upload_dir: Path, story_id: int, page_number: int
) -> str | None:
    """该页已有成品图时返回访问 URL，否则返回 None。

    绑定关系完全由文件是否存在决定：重跑拆解清空分镜页后，
    同页码的页面写回时成品图会自动挂回，不会丢失。
    """
    for extension in PAGE_IMAGE_EXTENSIONS:
        if _page_image_path(
            upload_dir, story_id, page_number, extension
        ).is_file():
            return f"/uploads/pages/{story_id}/page-{page_number}.{extension}"
    return None


def save_page_image(
    upload: UploadFile, upload_dir: Path, story_id: int, page_number: int
) -> str:
    """保存某页的成品图并返回访问 URL；同页重复上传时覆盖旧图。

    成品图来自生图 AI，体积可能明显大于封面，单独使用 15MB 上限。
    """
    actual_type, data = _validate_and_read_image(upload, MAX_PAGE_IMAGE_BYTES)
    # 先清掉其他扩展名的旧图，保证同页只有一份成品图
    for extension in PAGE_IMAGE_EXTENSIONS:
        if extension != actual_type:
            _page_image_path(
                upload_dir, story_id, page_number, extension
            ).unlink(missing_ok=True)
    target = _page_image_path(upload_dir, story_id, page_number, actual_type)
    _write_atomic(target, data)
    return f"/uploads/pages/{story_id}/page-{page_number}.{actual_type}"


def delete_page_image(
    upload_dir: Path, story_id: int, page_number: int
) -> None:
    """删除某页的成品图；不存在时静默返回，保持幂等。"""
    for extension in PAGE_IMAGE_EXTENSIONS:
        try:
            _page_image_path(
                upload_dir, story_id, page_number, extension
            ).unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "删除分镜成品图失败: story=%s page=%s",
                story_id,
                page_number,
                exc_info=True,
            )


def delete_story_page_images(upload_dir: Path, story_id: int) -> None:
    """删除故事的全部成品图目录；失败只记录日志，不阻塞主流程。"""
    try:
        shutil.rmtree(upload_dir / "pages" / str(story_id), ignore_errors=True)
    except OSError:
        logger.warning("删除故事成品图目录失败: story=%s", story_id, exc_info=True)


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
