"""图片别名水印：原地加字、备份与恢复。"""

from __future__ import annotations

import io

from PIL import Image

from tests.test_breakdowns import (
    _chapter_payload,
    _mapping_items,
    _patch_breakdown,
    _prepare,
    _put_page,
)

ALIAS = "测试别名六个字"


def _valid_png(size=(600, 800), color="white") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload_page(client, story_id, page_number, data=None):
    return client.post(
        f"/api/stories/{story_id}/breakdown/pages/{page_number}/image",
        files={"file": ("page.png", data or _valid_png(), "image/png")},
    )


def _image_path(app_settings, image_url):
    return app_settings.upload_dir / image_url.removeprefix("/uploads/")


def test_alias_stamp_then_restore(client, app_settings):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    uploaded = _upload_page(client, story["id"], 1)
    assert uploaded.status_code == 200, uploaded.text
    image_url = uploaded.json()["image_url"]
    path = _image_path(app_settings, image_url)
    original = path.read_bytes()

    response = client.post(
        f"/api/stories/{story['id']}/alias-stamp",
        json={"alias": ALIAS, "page_numbers": [1]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["stamped"] == 1
    assert data["failed"] == 0
    assert path.read_bytes() != original

    backup = (
        app_settings.upload_dir.parent
        / "alias-backups"
        / str(story["id"])
        / "pages"
        / str(story["id"])
        / "page-1.png"
    )
    assert backup.read_bytes() == original

    restored = client.post(
        f"/api/stories/{story['id']}/alias-stamp/restore",
        json={"page_numbers": [1]},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"] == 1
    assert path.read_bytes() == original


def test_alias_stamp_replaces_backup_after_image_reupload(client, app_settings):
    """已加字的图被换掉后，下一次加字应使用新图，而不是旧备份。"""
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    first = _upload_page(client, story["id"], 1)
    assert first.status_code == 200, first.text
    path = _image_path(app_settings, first.json()["image_url"])

    stamped = client.post(
        f"/api/stories/{story['id']}/alias-stamp",
        json={"alias": ALIAS, "page_numbers": [1]},
    )
    assert stamped.status_code == 200, stamped.text

    replacement = _valid_png(size=(700, 900), color="red")
    reuploaded = _upload_page(client, story["id"], 1, replacement)
    assert reuploaded.status_code == 200, reuploaded.text

    restamped = client.post(
        f"/api/stories/{story['id']}/alias-stamp",
        json={"alias": ALIAS, "page_numbers": [1]},
    )
    assert restamped.status_code == 200, restamped.text

    backup = (
        app_settings.upload_dir.parent
        / "alias-backups"
        / str(story["id"])
        / "pages"
        / str(story["id"])
        / "page-1.png"
    )
    assert backup.read_bytes() == replacement
    with Image.open(path) as image:
        assert image.size == (700, 900)


def test_alias_stamp_can_limit_to_one_chapter(client, app_settings):
    """只指定某一章时，不动其他章的图片。"""
    story, _ = _prepare(client)
    patched = _patch_breakdown(
        client,
        story["id"],
        mapping=_mapping_items([1, 2]),
        chapters=[_chapter_payload(1, [1]), _chapter_payload(2, [2])],
    )
    assert patched.status_code == 200, patched.text
    _put_page(
        client, story["id"], 1,
        mapping_page_number=1, chapter_number=1, chapter_page_number=1,
    )
    _put_page(
        client, story["id"], 2,
        mapping_page_number=2, chapter_number=2, chapter_page_number=1,
    )

    first = _upload_page(client, story["id"], 1)
    second = _upload_page(client, story["id"], 2)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    first_path = _image_path(app_settings, first.json()["image_url"])
    second_path = _image_path(app_settings, second.json()["image_url"])
    second_before = second_path.read_bytes()

    response = client.post(
        f"/api/stories/{story['id']}/alias-stamp",
        json={"alias": ALIAS, "chapter_numbers": [1]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["stamped"] == 1
    assert all(item["page_number"] == 1 for item in data["items"])
    assert first_path.read_bytes() != second_before
    assert second_path.read_bytes() == second_before


def test_alias_stamp_requires_alias(client):
    story, _ = _prepare(client)
    _put_page(client, story["id"], 1)
    _upload_page(client, story["id"], 1)

    response = client.post(
        f"/api/stories/{story['id']}/alias-stamp",
        json={"page_numbers": [1]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ZHIHU_ALIAS_REQUIRED"
