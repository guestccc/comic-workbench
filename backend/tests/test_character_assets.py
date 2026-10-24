"""角色资产图测试：单角色上传、替换、删除与级联清理。

资产图只保存在本地 uploads 目录；文件名写进角色卡的 asset_filename，
访问地址由服务端按文件是否存在计算，与角色名解耦。
"""

from __future__ import annotations

from tests.test_breakdowns import _prepare
from tests.test_uploads import JPEG_BYTES, PNG_BYTES


def _asset_path(app_settings, story_id: int, filename: str):
    return (
        app_settings.upload_dir
        / "character-assets"
        / str(story_id)
        / filename
    )


def _upload_asset(client, story_id, index, data=PNG_BYTES, name="asset.png"):
    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".webp": "image/webp",
    }["." + name.rsplit(".", 1)[-1]]
    return client.post(
        f"/api/stories/{story_id}/breakdown/characters/{index}/asset-image",
        files={"file": (name, data, content_type)},
    )


def _get_cards(client, story_id):
    response = client.get(f"/api/stories/{story_id}/breakdown")
    assert response.status_code == 200, response.text
    return response.json()["characters"]


def test_upload_character_asset_and_static_access(client):
    story, _ = _prepare(client)
    assert _get_cards(client, story["id"])[0]["asset_url"] is None

    response = _upload_asset(client, story["id"], 0)
    assert response.status_code == 200, response.text
    card = response.json()["characters"][0]
    assert card["asset_filename"].endswith(".png")
    assert card["asset_url"] == (
        f"/uploads/character-assets/{story['id']}/{card['asset_filename']}"
    )
    # 只影响目标角色
    assert response.json()["characters"][1]["asset_url"] is None

    # GET breakdown 时携带地址，且静态可访问
    assert _get_cards(client, story["id"])[0]["asset_url"] == card["asset_url"]
    assert client.get(card["asset_url"]).status_code == 200


def test_replace_character_asset_deletes_old_file(client, app_settings):
    story, _ = _prepare(client)

    first = _upload_asset(client, story["id"], 0).json()["characters"][0]
    old_path = _asset_path(app_settings, story["id"], first["asset_filename"])
    assert old_path.is_file()

    second = _upload_asset(
        client, story["id"], 0, JPEG_BYTES, "asset.jpg"
    ).json()["characters"][0]
    assert second["asset_filename"] != first["asset_filename"]
    assert not old_path.exists()
    files = list(old_path.parent.iterdir())
    assert len(files) == 1


def test_delete_character_asset_is_idempotent(client, app_settings):
    story, _ = _prepare(client)
    card = _upload_asset(client, story["id"], 0).json()["characters"][0]
    path = _asset_path(app_settings, story["id"], card["asset_filename"])

    response = client.delete(
        f"/api/stories/{story['id']}/breakdown/characters/0/asset-image"
    )
    assert response.status_code == 204
    assert not path.exists()
    assert _get_cards(client, story["id"])[0]["asset_url"] is None

    # 重复删除同样返回 204
    response = client.delete(
        f"/api/stories/{story['id']}/breakdown/characters/0/asset-image"
    )
    assert response.status_code == 204


def test_upload_character_asset_validation(client):
    story, _ = _prepare(client)

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/characters/0/asset-image",
        files={"file": ("evil.png", b"<html></html>", "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_IMAGE_TYPE"

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/characters/0/asset-image",
        files={"file": ("asset.png", JPEG_BYTES, "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "IMAGE_TYPE_MISMATCH"

    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (15 * 1024 * 1024)
    response = client.post(
        f"/api/stories/{story['id']}/breakdown/characters/0/asset-image",
        files={"file": ("asset.png", oversized, "image/png")},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "FILE_TOO_LARGE"


def test_upload_character_asset_requires_existing_character(client):
    story, _ = _prepare(client)

    response = _upload_asset(client, story["id"], 9)
    assert response.status_code == 404
    assert response.json()["code"] == "CHARACTER_NOT_FOUND"

    assert (
        client.delete(f"/api/stories/{story['id']}/breakdown").status_code == 204
    )
    response = _upload_asset(client, story["id"], 0)
    assert response.status_code == 404
    assert response.json()["code"] == "BREAKDOWN_NOT_FOUND"


def test_patch_preserves_asset_by_character_name(client):
    """重新拆解 / 编辑卡片时，按角色名继承资产图，不会丢图。"""
    story, _ = _prepare(client)
    uploaded = _upload_asset(client, story["id"], 0).json()["characters"][0]

    response = client.patch(
        f"/api/stories/{story['id']}/breakdown",
        json={
            "characters": [
                {"name": "我", "role": "主角", "appearance": "新的外形描述。"},
                {
                    "name": "小八老师",
                    "role": "女主",
                    "appearance": "新的外形描述。",
                },
            ]
        },
    )
    assert response.status_code == 200, response.text
    cards = response.json()["characters"]
    assert cards[0]["asset_filename"] == uploaded["asset_filename"]
    assert cards[0]["asset_url"] == uploaded["asset_url"]
    assert cards[1]["asset_url"] is None


def test_patch_deletes_assets_of_removed_characters(client, app_settings):
    story, _ = _prepare(client)
    uploaded = _upload_asset(client, story["id"], 0).json()["characters"][0]
    path = _asset_path(app_settings, story["id"], uploaded["asset_filename"])
    assert path.is_file()

    # 新角色卡里不再有「我」，对应资产图应被清理
    response = client.patch(
        f"/api/stories/{story['id']}/breakdown",
        json={
            "characters": [
                {
                    "name": "小八老师",
                    "role": "女主",
                    "appearance": "新的外形描述。",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert not path.exists()


def test_story_and_breakdown_cleanup_remove_character_assets(client, app_settings):
    story, _ = _prepare(client)
    _upload_asset(client, story["id"], 0)
    asset_dir = app_settings.upload_dir / "character-assets" / str(story["id"])
    assert asset_dir.exists()

    # 清空拆解
    assert (
        client.delete(f"/api/stories/{story['id']}/breakdown").status_code == 204
    )
    assert not asset_dir.exists()

    # 重新拆解同一故事后上传，再删故事
    response = client.patch(
        f"/api/stories/{story['id']}/breakdown",
        json={
            "optimized_content": "重新拆解后的优化文。",
            "characters": [
                {"name": "我", "role": "主角", "appearance": "外形描述。"}
            ],
        },
    )
    assert response.status_code == 200, response.text
    _upload_asset(client, story["id"], 0)
    assert asset_dir.exists()
    assert client.delete(f"/api/stories/{story['id']}").status_code == 204
    assert not asset_dir.exists()
