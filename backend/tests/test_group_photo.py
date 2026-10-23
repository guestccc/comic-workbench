"""人物合照测试：上传、覆盖、删除与故事 / 拆解级联清理。

合照与分镜成品图一样只保存在本地 uploads 目录，
绑定关系由文件是否存在决定，不写进数据库。
"""

from __future__ import annotations

from tests.test_breakdowns import _prepare
from tests.test_uploads import JPEG_BYTES, PNG_BYTES


def _upload_group_photo(client, story_id, data=PNG_BYTES, name="photo.png"):
    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".webp": "image/webp",
    }["." + name.rsplit(".", 1)[-1]]
    return client.post(
        f"/api/stories/{story_id}/breakdown/group-photo",
        files={"file": (name, data, content_type)},
    )


def _get_group_photo_url(client, story_id):
    response = client.get(f"/api/stories/{story_id}/breakdown")
    assert response.status_code == 200, response.text
    return response.json()["group_photo_url"]


def test_upload_group_photo_and_static_access(client):
    story, _ = _prepare(client)

    # 上传前没有合照
    assert _get_group_photo_url(client, story["id"]) is None

    response = _upload_group_photo(client, story["id"])
    assert response.status_code == 200, response.text
    assert (
        response.json()["group_photo_url"]
        == f"/uploads/group-photos/{story['id']}.png"
    )

    # GET breakdown 时携带合照地址，且静态可访问
    url = _get_group_photo_url(client, story["id"])
    assert url == response.json()["group_photo_url"]
    assert client.get(url).status_code == 200


def test_upload_rejects_invalid_image(client):
    story, _ = _prepare(client)

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/group-photo",
        files={"file": ("evil.png", b"<html></html>", "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_IMAGE_TYPE"

    # 扩展名与内容不一致
    response = client.post(
        f"/api/stories/{story['id']}/breakdown/group-photo",
        files={"file": ("photo.png", JPEG_BYTES, "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "IMAGE_TYPE_MISMATCH"


def test_upload_rejects_oversized_image(client):
    story, _ = _prepare(client)

    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (15 * 1024 * 1024)
    response = _upload_group_photo(client, story["id"], oversized)
    assert response.status_code == 413
    assert response.json()["code"] == "FILE_TOO_LARGE"


def test_upload_requires_existing_breakdown(client):
    story, _ = _prepare(client)

    # 拆解被清空后不能上传合照
    assert client.delete(f"/api/stories/{story['id']}/breakdown").status_code == 204
    response = _upload_group_photo(client, story["id"])
    assert response.status_code == 404
    assert response.json()["code"] == "BREAKDOWN_NOT_FOUND"

    # 故事本身不存在
    response = _upload_group_photo(client, 999)
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"


def test_reupload_replaces_old_photo(client, app_settings):
    story, _ = _prepare(client)
    _upload_group_photo(client, story["id"], PNG_BYTES)

    # 换成 JPG 后旧 PNG 被清理，URL 指向新文件
    response = _upload_group_photo(
        client, story["id"], JPEG_BYTES, name="photo.jpg"
    )
    assert response.json()["group_photo_url"].endswith(f"{story['id']}.jpg")
    old_png = app_settings.upload_dir / "group-photos" / f"{story['id']}.png"
    assert not old_png.exists()
    assert client.get(response.json()["group_photo_url"]).status_code == 200


def test_delete_group_photo(client):
    story, _ = _prepare(client)
    _upload_group_photo(client, story["id"])

    response = client.delete(f"/api/stories/{story['id']}/breakdown/group-photo")
    assert response.status_code == 204
    assert _get_group_photo_url(client, story["id"]) is None
    # 重复删除保持幂等
    assert (
        client.delete(f"/api/stories/{story['id']}/breakdown/group-photo").status_code
        == 204
    )


def test_delete_breakdown_removes_group_photo(client, app_settings):
    story, _ = _prepare(client)
    _upload_group_photo(client, story["id"])

    assert client.delete(f"/api/stories/{story['id']}/breakdown").status_code == 204
    photo_dir = app_settings.upload_dir / "group-photos"
    assert not list(photo_dir.glob(f"{story['id']}.*"))


def test_delete_story_removes_group_photo(client, app_settings):
    story, _ = _prepare(client)
    _upload_group_photo(client, story["id"])

    assert client.delete(f"/api/stories/{story['id']}").status_code == 204
    photo_dir = app_settings.upload_dir / "group-photos"
    assert not list(photo_dir.glob(f"{story['id']}.*"))
