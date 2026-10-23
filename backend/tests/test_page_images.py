"""分镜成品图测试：上传、覆盖、删除、清空重挂与故事级联清理。"""

from __future__ import annotations

from tests.test_breakdowns import _prepare, _put_page
from tests.test_uploads import JPEG_BYTES, PNG_BYTES, WEBP_BYTES


def _upload_page_image(client, story_id, page_number, data=PNG_BYTES, name="page.png"):
    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".webp": "image/webp",
    }["." + name.rsplit(".", 1)[-1]]
    return client.post(
        f"/api/stories/{story_id}/breakdown/pages/{page_number}/image",
        files={"file": (name, data, content_type)},
    )


def _get_pages(client, story_id):
    response = client.get(f"/api/stories/{story_id}/breakdown")
    assert response.status_code == 200, response.text
    return response.json()["pages"]


def test_upload_marks_page_done_and_static_access(client):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)

    # 上传前没有成品图
    assert _get_pages(client, story["id"])[0]["image_url"] is None

    response = _upload_page_image(client, story["id"], 1)
    assert response.status_code == 200, response.text
    assert response.json()["image_url"] == f"/uploads/pages/{story['id']}/page-1.png"

    # GET breakdown 时携带成品图地址，且静态可访问
    page = _get_pages(client, story["id"])[0]
    assert page["image_url"] == response.json()["image_url"]
    assert client.get(page["image_url"]).status_code == 200


def test_upload_rejects_invalid_image(client):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/pages/1/image",
        files={"file": ("evil.png", b"<html></html>", "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_IMAGE_TYPE"

    # 扩展名与内容不一致
    response = client.post(
        f"/api/stories/{story['id']}/breakdown/pages/1/image",
        files={"file": ("page.png", JPEG_BYTES, "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "IMAGE_TYPE_MISMATCH"


def test_upload_rejects_oversized_image(client):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)

    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (15 * 1024 * 1024)
    response = _upload_page_image(client, story["id"], 1, oversized)
    assert response.status_code == 413
    assert response.json()["code"] == "FILE_TOO_LARGE"


def test_upload_requires_existing_page(client):
    story, _ = _prepare(client)

    # 页码还没有分镜
    response = _upload_page_image(client, story["id"], 9)
    assert response.status_code == 404
    assert response.json()["code"] == "PAGE_NOT_FOUND"

    # 故事本身不存在
    response = _upload_page_image(client, 999, 1)
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"


def test_reupload_replaces_old_image(client, app_settings):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    _upload_page_image(client, story["id"], 1, PNG_BYTES)

    # 换成 JPG 后旧 PNG 被清理，URL 指向新文件
    response = _upload_page_image(
        client, story["id"], 1, JPEG_BYTES, name="page.jpg"
    )
    assert response.json()["image_url"].endswith("page-1.jpg")
    old_png = app_settings.upload_dir / "pages" / str(story["id"]) / "page-1.png"
    assert not old_png.exists()
    assert client.get(response.json()["image_url"]).status_code == 200


def test_delete_image_clears_done_mark(client):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    _upload_page_image(client, story["id"], 1)

    response = client.delete(
        f"/api/stories/{story['id']}/breakdown/pages/1/image"
    )
    assert response.status_code == 204
    assert _get_pages(client, story["id"])[0]["image_url"] is None
    # 重复删除保持幂等
    assert (
        client.delete(f"/api/stories/{story['id']}/breakdown/pages/1/image").status_code
        == 204
    )


def test_clear_pages_keeps_images_and_reattaches(client):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    _upload_page_image(client, story["id"], 1)

    # 清空分镜页不删成品图；同页码重新写入后自动挂回
    assert client.delete(f"/api/stories/{story['id']}/breakdown/pages").status_code == 204
    _put_page(client, story["id"], 1)
    assert _get_pages(client, story["id"])[0]["image_url"] is not None


def test_delete_page_removes_image(client, app_settings):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    _upload_page_image(client, story["id"], 1)

    assert (
        client.delete(f"/api/stories/{story['id']}/breakdown/pages/1").status_code
        == 204
    )
    image_dir = app_settings.upload_dir / "pages" / str(story["id"])
    assert not any(image_dir.glob("page-1.*"))


def test_delete_breakdown_removes_all_images(client, app_settings):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    _put_page(client, story["id"], 2)
    _upload_page_image(client, story["id"], 1)
    _upload_page_image(client, story["id"], 2, WEBP_BYTES, name="page.webp")

    assert client.delete(f"/api/stories/{story['id']}/breakdown").status_code == 204
    assert not (app_settings.upload_dir / "pages" / str(story["id"])).exists()


def test_delete_story_removes_images(client, app_settings):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    _upload_page_image(client, story["id"], 1)

    assert client.delete(f"/api/stories/{story['id']}").status_code == 204
    assert not (app_settings.upload_dir / "pages" / str(story["id"])).exists()
