"""分镜成品图测试：上传、覆盖、删除、清空与故事级联清理。"""

from __future__ import annotations

import io
import zipfile

from app.services.files import organize_page_images
from tests.test_breakdowns import (
    _chapter_payload,
    _mapping_items,
    _patch_breakdown,
    _prepare,
    _put_page,
)
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


def test_story_cover_falls_back_to_first_page_image(client):
    """没有单独上传封面时，故事封面默认用第 1 页镜头的成品图。"""
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)

    # 第 1 页还没出图时没有封面
    assert client.get(f"/api/stories/{story['id']}").json()["cover_url"] is None

    _upload_page_image(client, story["id"], 1)
    expected = f"/uploads/pages/{story['id']}/page-1.png"

    # 详情与列表都回退到第 1 页成品图
    assert client.get(f"/api/stories/{story['id']}").json()["cover_url"] == expected
    listed = client.get("/api/stories").json()
    assert next(item for item in listed if item["id"] == story["id"])[
        "cover_url"
    ] == expected


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


def test_clear_pages_removes_images(client, app_settings):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    _upload_page_image(client, story["id"], 1)

    # 脚本可能重新编号，旧成品图不能按页码挂回错误页面
    assert (
        client.delete(f"/api/stories/{story['id']}/breakdown/pages").status_code
        == 204
    )
    image_dir = app_settings.upload_dir / "pages" / str(story["id"])
    assert not any(image_dir.glob("page-1.*"))

    _put_page(client, story["id"], 1)
    assert _get_pages(client, story["id"])[0]["image_url"] is None


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


def _configure_chapters(client, story_id):
    assert (
        _patch_breakdown(
            client, story_id, mapping=_mapping_items([1, 2, 3])
        ).status_code
        == 200
    )
    response = _patch_breakdown(
        client,
        story_id,
        chapters=[_chapter_payload(1, [1, 2]), _chapter_payload(2, [3])],
    )
    assert response.status_code == 200, response.text


def test_chapter_cover_and_guide_images(client, app_settings):
    story, _ = _prepare(client)
    story_id = story["id"]
    _configure_chapters(client, story_id)

    response = client.post(
        f"/api/stories/{story_id}/breakdown/chapters/1/cover/image",
        files={"file": ("cover.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 200, response.text
    cover_url = f"/uploads/chapters/{story_id}/chapter-1-cover.png"
    assert response.json()["chapters"][0]["cover"]["image_url"] == cover_url
    assert client.get(cover_url).status_code == 200

    response = client.post(
        f"/api/stories/{story_id}/breakdown/chapters/1/guide/image",
        files={"file": ("guide.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 200, response.text
    guide_url = f"/uploads/chapters/{story_id}/chapter-1-guide.png"
    assert response.json()["chapters"][0]["guide"]["image_url"] == guide_url
    assert client.get(guide_url).status_code == 200

    # 删除封面图，引导卡图不受影响
    assert (
        client.delete(
            f"/api/stories/{story_id}/breakdown/chapters/1/cover/image"
        ).status_code
        == 204
    )
    breakdown = client.get(f"/api/stories/{story_id}/breakdown").json()
    assert breakdown["chapters"][0]["cover"]["image_url"] is None
    assert breakdown["chapters"][0]["guide"]["image_url"] == guide_url
    assert not (
        app_settings.upload_dir
        / "chapters"
        / str(story_id)
        / "chapter-1-cover.png"
    ).exists()


def test_clear_pages_keeps_chapter_assets(client, app_settings):
    """清空正文页可以重新生成，但已经做好的封面/引导卡不能丢。"""
    story, _ = _prepare(client)
    story_id = story["id"]
    _configure_chapters(client, story_id)

    client.post(
        f"/api/stories/{story_id}/breakdown/chapters/1/cover/image",
        files={"file": ("cover.png", PNG_BYTES, "image/png")},
    )
    client.post(
        f"/api/stories/{story_id}/breakdown/chapters/1/guide/image",
        files={"file": ("guide.png", PNG_BYTES, "image/png")},
    )

    assert (
        client.delete(f"/api/stories/{story_id}/breakdown/pages").status_code
        == 204
    )
    breakdown = client.get(f"/api/stories/{story_id}/breakdown").json()
    assert breakdown["chapters"][0]["cover"]["image_url"] is not None
    assert breakdown["chapters"][0]["guide"]["image_url"] is not None


def test_export_chapter_images_zip(client):
    """导出按章节分文件夹：封面 → 正文（页序）→ 引导卡。"""
    story, _ = _prepare(client)
    story_id = story["id"]
    _configure_chapters(client, story_id)

    # 第 1 章：封面 / 第 1、2 页正文 / 引导卡
    client.post(
        f"/api/stories/{story_id}/breakdown/chapters/1/cover/image",
        files={"file": ("cover.png", PNG_BYTES, "image/png")},
    )
    _put_page(
        client,
        story_id,
        1,
        mapping_page_number=1,
        chapter_number=1,
        chapter_page_number=1,
    )
    _put_page(
        client,
        story_id,
        2,
        mapping_page_number=2,
        chapter_number=1,
        chapter_page_number=2,
    )
    _upload_page_image(client, story_id, 1)
    _upload_page_image(client, story_id, 2)
    client.post(
        f"/api/stories/{story_id}/breakdown/chapters/1/guide/image",
        files={"file": ("guide.png", PNG_BYTES, "image/png")},
    )

    # 正文图按章节目录存放，文件名用四位全局页码
    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert pages[0]["image_url"] == (
        f"/uploads/pages/{story_id}/chapter-1/page-0001.png"
    )
    assert pages[1]["image_url"] == (
        f"/uploads/pages/{story_id}/chapter-1/page-0002.png"
    )

    response = client.get(
        f"/api/stories/{story_id}/breakdown/chapters/1/export"
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
    assert names == [
        "第1章_第1章/01_封面.png",
        "第1章_第1章/02_第1页.png",
        "第1章_第1章/03_第2页.png",
        "第1章_第1章/04_引导卡.png",
    ]

    # 全部章节导出：没有图片的第 2 章不生成空文件夹
    response = client.get(
        f"/api/stories/{story_id}/breakdown/export-images"
    )
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == names

    # 没有任何图片的章节导出时给出明确错误
    response = client.get(
        f"/api/stories/{story_id}/breakdown/chapters/2/export"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NO_CHAPTER_IMAGES"


def test_organize_page_images_moves_legacy_flat_files(app_settings):
    """启动迁移：旧版平铺的 page-1.png 应归入对应章节目录。"""
    story_id = 3
    root = app_settings.upload_dir / "pages" / str(story_id)
    root.mkdir(parents=True)
    (root / "page-1.png").write_bytes(PNG_BYTES)
    (root / "page-2.jpg").write_bytes(JPEG_BYTES)

    organize_page_images(
        app_settings.upload_dir,
        story_id,
        [
            {"page_number": 1, "chapter_number": 2},
            {"page_number": 2, "mapping_page_number": 9},
        ],
        [{"chapter_number": 3, "mapping_page_numbers": [9]}],
    )

    assert (root / "chapter-2" / "page-0001.png").is_file()
    assert (root / "chapter-3" / "page-0002.jpg").is_file()
    assert not (root / "page-1.png").exists()
    assert not (root / "page-2.jpg").exists()


def test_delete_breakdown_removes_chapter_assets(client, app_settings):
    story, _ = _prepare(client)
    story_id = story["id"]
    _configure_chapters(client, story_id)
    client.post(
        f"/api/stories/{story_id}/breakdown/chapters/1/cover/image",
        files={"file": ("cover.png", PNG_BYTES, "image/png")},
    )

    assert (
        client.delete(f"/api/stories/{story_id}/breakdown").status_code == 204
    )
    assert not (
        app_settings.upload_dir / "chapters" / str(story_id)
    ).exists()
