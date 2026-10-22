"""封面上传测试：类型、大小、文件名安全。"""

from __future__ import annotations

import re

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 128
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"0" * 128
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"0" * 128


def _upload(client, filename: str, data: bytes, content_type: str = "image/png"):
    return client.post(
        "/api/uploads", files={"file": (filename, data, content_type)}
    )


def test_upload_png_and_static_access(client):
    response = _upload(client, "cover.png", PNG_BYTES)
    assert response.status_code == 201
    data = response.json()
    assert re.fullmatch(r"[0-9a-f]{32}\.png", data["filename"])
    assert data["url"] == f"/uploads/{data['filename']}"
    # 通过静态目录可访问
    assert client.get(data["url"]).status_code == 200


def test_upload_jpeg(client):
    response = _upload(client, "cover.jpeg", JPEG_BYTES, "image/jpeg")
    assert response.status_code == 201
    assert response.json()["filename"].endswith(".jpg")


def test_upload_webp(client):
    response = _upload(client, "cover.webp", WEBP_BYTES, "image/webp")
    assert response.status_code == 201
    assert response.json()["filename"].endswith(".webp")


def test_extension_and_content_mismatch(client):
    response = _upload(client, "cover.png", JPEG_BYTES)
    assert response.status_code == 422
    assert response.json()["code"] == "IMAGE_TYPE_MISMATCH"


def test_disguised_html_rejected(client):
    response = _upload(client, "evil.png", b"<html><script>alert(1)</script></html>")
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_IMAGE_TYPE"


def test_unsupported_extension_rejected(client):
    response = _upload(client, "evil.svg", b"<svg></svg>", "image/svg+xml")
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_IMAGE_TYPE"


def test_empty_file_rejected(client):
    response = _upload(client, "empty.png", b"")
    assert response.status_code == 422


def test_file_too_large_rejected(client):
    # 恰好超过 5 MiB
    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024)
    response = _upload(client, "big.png", oversized)
    assert response.status_code == 413
    assert response.json()["code"] == "FILE_TOO_LARGE"


def test_path_traversal_filename_is_ignored(client):
    response = _upload(client, "../../evil.png", PNG_BYTES)
    assert response.status_code == 201
    filename = response.json()["filename"]
    assert ".." not in filename
    assert "/" not in filename
    assert re.fullmatch(r"[0-9a-f]{32}\.png", filename)
