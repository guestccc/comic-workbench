"""生图服务：配置、角色资产图、封面参考图、历史与清除。"""

from __future__ import annotations

import hashlib

import pytest

from app.services.image_provider import GeneratedImage
from tests.test_breakdowns import (
    _chapter_payload,
    _mapping_items,
    _patch_breakdown,
    _prepare,
)
from tests.test_uploads import PNG_BYTES

MODEL = "gpt-image-2.5-sunburst"


def _configure_image_provider(client):
    response = client.put(
        "/api/settings/image-provider",
        json={
            "base_url": "https://scpyx.com",
            "model": MODEL,
            "size": "1024x1536",
            "quality": "high",
            "api_key": "sk-image-test",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _fake_generated() -> GeneratedImage:
    return GeneratedImage(
        data=PNG_BYTES,
        content_type="image/png",
        extension="png",
        sha256=hashlib.sha256(PNG_BYTES).hexdigest(),
        width=1086,
        height=1448,
        elapsed_ms=1200,
        request_id="req-test",
        model=MODEL,
        size="1024x1536",
    )


@pytest.fixture()
def mock_image(monkeypatch):
    calls: list[dict] = []

    def fake_generate(config, prompt, references=None):
        calls.append(
            {
                "base_url": config.base_url,
                "prompt": prompt,
                "references": [item.name for item in (references or [])],
            }
        )
        return _fake_generated()

    monkeypatch.setattr(
        "app.routers.image_generation.generate_image", fake_generate
    )
    return calls


def _upload_character_asset(client, story_id, index=0):
    response = client.post(
        f"/api/stories/{story_id}/breakdown/characters/{index}/asset-image",
        files={"file": ("asset.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _setup_cover_chapter(client):
    story, breakdown = _prepare(client)
    mapping = _mapping_items([1, 2])
    chapter = _chapter_payload(1, [1, 2])
    chapter["cover"]["image_prompt"] = "【画面】{{我}}站在车站，3:4竖版，无文字。"
    response = _patch_breakdown(
        client,
        story["id"],
        mapping=mapping,
        chapters=[chapter],
    )
    assert response.status_code == 200, response.text
    return story, response.json()


def test_image_provider_settings_masks_key(client):
    data = _configure_image_provider(client)
    provider = data["image_provider"]
    assert provider["configured"] is True
    assert provider["source"] == "db"
    assert provider["masked_key"] == "****test"
    assert "sk-image-test" not in str(data)


def test_character_asset_generate_use_and_clear_keeps_current(
    client, mock_image
):
    story, _ = _prepare(client)
    _configure_image_provider(client)

    response = client.post(
        f"/api/stories/{story['id']}/character-assets/generate",
        json={"character_name": "我"},
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["target_type"] == "character_asset"
    assert preview["old_url"] is None
    assert preview["new_url"].startswith("/uploads/image-history/")
    assert client.get(preview["new_url"]).status_code == 200
    assert preview["model"] == MODEL
    assert mock_image[0]["references"] == []

    history = client.get(
        f"/api/stories/{story['id']}/image-generations",
        params={"target_type": "character_asset", "character_name": "我"},
    )
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert len(items) == 1
    assert items[0]["is_current"] is False

    used = client.post(
        f"/api/stories/{story['id']}/image-generations/"
        f"{preview['generation_id']}/use"
    )
    assert used.status_code == 200, used.text
    asset_url = used.json()["characters"][0]["asset_url"]
    assert asset_url
    assert client.get(asset_url).status_code == 200

    history = client.get(
        f"/api/stories/{story['id']}/image-generations",
        params={"target_type": "character_asset", "character_name": "我"},
    )
    assert history.json()["items"][0]["is_current"] is True

    cleared = client.delete(
        f"/api/stories/{story['id']}/image-generations",
        params={"target_type": "character_asset", "character_name": "我"},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["deleted"] == 1
    # 清历史不能删除当前正式资产图
    breakdown = client.get(f"/api/stories/{story['id']}/breakdown")
    assert breakdown.json()["characters"][0]["asset_url"] == asset_url
    assert client.get(asset_url).status_code == 200


def _set_start_prompt(client, content):
    response = client.put("/api/settings/prompt", json={"content": content})
    assert response.status_code == 200, response.text


def test_character_asset_generate_prepends_start_prompt(client, mock_image):
    """工作台调上游生图 API 时，每次请求都自带启动提示词。"""
    story, _ = _prepare(client)
    _configure_image_provider(client)
    _set_start_prompt(client, "【全局生图规则】画风={art_style_name}；{art_style}")

    response = client.post(
        f"/api/stories/{story['id']}/character-assets/generate",
        json={"character_name": "我"},
    )
    assert response.status_code == 200, response.text
    prompt = mock_image[0]["prompt"]
    assert prompt.startswith("【全局生图规则】画风=唯美彩铅；韩式唯美彩铅手绘")
    # 启动提示词在最前面，目标提示词仍在后面
    assert "三视角" in prompt or "全身" in prompt


def test_cover_generate_prepends_start_prompt(client, mock_image):
    story, _ = _setup_cover_chapter(client)
    _configure_image_provider(client)
    _upload_character_asset(client, story["id"], 0)
    _set_start_prompt(
        client, "【生图总规则】故事={story_name}；画风={art_style_name}"
    )

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/generate"
    )
    assert response.status_code == 200, response.text
    prompt = mock_image[0]["prompt"]
    assert prompt.startswith("【生图总规则】故事=拆解故事；画风=唯美彩铅")
    assert "参考图1" in prompt

    history = client.get(
        f"/api/stories/{story['id']}/image-generations",
        params={"target_type": "chapter_cover", "chapter_number": 1},
    )
    assert history.status_code == 200, history.text
    item = history.json()["items"][0]
    assert item["prompt"] == prompt
    assert item["reference_names"] == ["我"]


def test_cover_generate_requires_character_asset(client, mock_image):
    story, _ = _setup_cover_chapter(client)
    _configure_image_provider(client)

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/generate"
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "CHARACTER_ASSET_MISSING"
    assert mock_image == []


def test_cover_generate_uses_assets_and_maps_prompt(client, mock_image):
    story, _ = _setup_cover_chapter(client)
    _configure_image_provider(client)
    _upload_character_asset(client, story["id"], 0)

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/generate"
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["target_type"] == "chapter_cover"
    assert mock_image[0]["references"] == ["我"]
    assert "参考图1" in mock_image[0]["prompt"]
    assert "{{我}}" not in mock_image[0]["prompt"]
    assert "不要照搬参考图的排版" in mock_image[0]["prompt"]

    used = client.post(
        f"/api/stories/{story['id']}/image-generations/"
        f"{preview['generation_id']}/use"
    )
    assert used.status_code == 200, used.text
    cover_url = used.json()["chapters"][0]["cover"]["image_url"]
    assert cover_url
    assert client.get(cover_url).status_code == 200

    # 历史清除后封面仍然可用
    cleared = client.delete(
        f"/api/stories/{story['id']}/image-generations",
        params={"target_type": "chapter_cover", "chapter_number": 1},
    )
    assert cleared.status_code == 200, cleared.text
    breakdown = client.get(f"/api/stories/{story['id']}/breakdown")
    assert breakdown.json()["chapters"][0]["cover"]["image_url"] == cover_url


def test_cover_generate_without_prompt_rejected(client, mock_image):
    story, _ = _setup_cover_chapter(client)
    _configure_image_provider(client)
    _upload_character_asset(client, story["id"], 0)
    # 清空封面提示词
    chapters = client.get(f"/api/stories/{story['id']}/breakdown").json()["chapters"]
    chapters[0]["cover"]["image_prompt"] = ""
    _patch_breakdown(client, story["id"], chapters=chapters)

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/generate"
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "IMAGE_PROMPT_EMPTY"
    assert mock_image == []


def test_image_generation_rejects_unknown_story(client, mock_image):
    _configure_image_provider(client)
    response = client.post(
        "/api/stories/999/character-assets/generate",
        json={"character_name": "我"},
    )
    assert response.status_code == 404
    assert mock_image == []
