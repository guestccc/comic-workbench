"""封面图片的校验、存储与删除。"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from ..config import MAX_UPLOAD_BYTES
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


def detect_image_type(head: bytes) -> str | None:
    """通过文件头 magic bytes 判断图片类型（imghdr 在 Python 3.13 已移除）。"""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def save_cover(upload: UploadFile, upload_dir: Path) -> tuple[str, str]:
    """校验并保存封面，返回 (文件名, 访问 URL)。

    安全策略：扩展名白名单 + magic bytes 双重校验、字节数硬限制、
    UUID 重命名、先写临时文件再原子替换。
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
        # 不信任 Content-Length，按实际读取字节数限制
        if len(data) > MAX_UPLOAD_BYTES:
            raise AppError(413, "图片大小不能超过 5MB", "FILE_TOO_LARGE")
    if not data:
        raise AppError(422, "上传文件为空", "EMPTY_FILE")

    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{actual_type}"
    target = upload_dir / filename
    temp_path = target.with_name(target.name + ".tmp")
    temp_path.write_bytes(bytes(data))
    temp_path.replace(target)
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
