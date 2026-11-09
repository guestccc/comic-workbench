"""提示词渲染快照与恢复测试。"""

from __future__ import annotations

STYLE = {"id": "style-a", "name": "唯美彩铅", "content": "韩式唯美彩铅手绘"}


def _prepare_story(client):
    client.put(
        "/api/settings/art-styles",
        json={"styles": [STYLE], "active_id": "style-a"},
    )
    story = client.post(
        "/api/stories",
        json={
            "name": "快照测试故事",
            "content": "原文",
            "art_style_id": "style-a",
        },
    ).json()
    breakdown = client.patch(
        f"/api/stories/{story['id']}/breakdown",
        json={
            "optimized_content": "原文",
            "mapping": [
                {
                    "page_number": 1,
                    "source_text": "原文",
                    "summary": "主角站在原地",
                    "paragraph": "第1段",
                    "part": "1/1",
                    "excluded": False,
                }
            ],
            "chapters": [
                {
                    "chapter_number": 1,
                    "title": "第一章",
                    "mapping_page_numbers": [1],
                    "cover": {
                        "label": "第1章 · 第一章",
                        "narration_main": "她抬起头",
                        "narration_highlight": "抬头",
                        "narration_sub": "这一次她不再退让",
                        "image_prompt": "",
                    },
                    "guide": {
                        "text": "关注我，看更多重生爽文",
                        "sub_text": "下一章：他来了",
                        "image_prompt": "",
                    },
                }
            ],
        },
    )
    assert breakdown.status_code == 200, breakdown.text
    return story


def _render_cover(client, story_id: int, content: str):
    response = client.post(
        "/api/settings/prompt-templates/render",
        json={
            "template_type": "cover",
            "story_id": story_id,
            "context": {
                "content": content,
                "character_consistency": "遵循角色卡",
                "narration_main": "她抬起头",
                "narration_sub": "这一次她不再退让",
                "narration_highlight": "抬头",
                "label": "第1章 · 第一章",
                "chapter_number": 1,
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_prompt_snapshot_and_restore_cover(client):
    story = _prepare_story(client)
    first = _render_cover(client, story["id"], "近景，人物含泪")
    assert first["snapshot_id"] is not None

    second = _render_cover(client, story["id"], "近景，人物微笑")
    assert second["snapshot_id"] != first["snapshot_id"]

    snapshots = client.get(
        f"/api/stories/{story['id']}/prompt-snapshots",
        params={"target_type": "cover", "chapter_number": 1},
    )
    assert snapshots.status_code == 200, snapshots.text
    items = snapshots.json()
    assert len(items) == 2
    assert items[0]["id"] == second["snapshot_id"]

    restored = client.post(
        f"/api/prompt-snapshots/{first['snapshot_id']}/restore"
    )
    assert restored.status_code == 200, restored.text
    result = restored.json()
    assert result["target_type"] == "cover"
    assert result["snapshot"]["restored_from_id"] == first["snapshot_id"]

    breakdown = client.get(f"/api/stories/{story['id']}/breakdown").json()
    assert (
        breakdown["chapters"][0]["cover"]["image_prompt"]
        == first["prompt"]
    )


def test_prompt_snapshot_preview_does_not_write(client):
    story = _prepare_story(client)
    response = client.post(
        "/api/settings/prompt-templates/render",
        json={
            "template_type": "cover",
            "story_id": story["id"],
            "preview": True,
            "context": {
                "content": "预览画面",
                "narration_main": "预览",
                "narration_sub": "预览副标题",
                "narration_highlight": "预览",
                "label": "第1章 · 第一章",
                "chapter_number": 1,
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["snapshot_id"] is None

    snapshots = client.get(
        f"/api/stories/{story['id']}/prompt-snapshots"
    ).json()
    assert snapshots == []
