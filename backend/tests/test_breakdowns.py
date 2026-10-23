"""故事拆解结果接口测试。"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import StoryBreakdown, StoryPostConfig

STYLE_A = {"id": "style-a", "name": "唯美彩铅", "content": "韩式唯美彩铅手绘"}
STYLE_B = {"id": "style-b", "name": "日系赛璐璐", "content": "日系赛璐璐平涂"}


def _save_art_styles(client, styles, active_id=None):
    response = client.put(
        "/api/settings/art-styles",
        json={"styles": styles, "active_id": active_id},
    )
    assert response.status_code == 200, response.text


def _create_styled_story(client, style_id="style-a", content="第一次相亲的故事"):
    response = client.post(
        "/api/stories",
        json={
            "name": "拆解故事",
            "content": content,
            "art_style_id": style_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _page_payload(**overrides):
    payload = {
        "is_flashback": False,
        "story_content": "第一页：女老师提问 A8",
        "characters": ["我", "小八老师"],
        "character_review": "我：短发、休闲装；小八老师：鹅蛋脸、衬衫。",
        "scene": "高档餐厅，靠窗座位",
        "action_state": "小八老师倾身发问，我一脸困惑",
        "change_note": "抛出让男主困惑的问题",
        "narration_main": "如果一个女生开口问你有没有A8",
        "narration_highlight": "A8",
        "narration_sub": "第一次相亲，小八老师问出了这句话。",
        "dialogues": ["小八老师：你应该有A8吧？"],
        "shot_type": "特写",
        "image_prompt": "韩式唯美彩铅手绘，米色素描纸，餐厅特写……",
    }
    payload.update(overrides)
    return payload


def _patch_breakdown(client, story_id, **payload):
    return client.patch(f"/api/stories/{story_id}/breakdown", json=payload)


def _put_page(client, story_id, page_number, **overrides):
    return client.put(
        f"/api/stories/{story_id}/breakdown/pages/{page_number}",
        json=_page_payload(**overrides),
    )


def _prepare(client):
    """准备画风、带画风的故事以及拆解头部信息。"""
    _save_art_styles(client, [STYLE_A, STYLE_B], active_id="style-a")
    story = _create_styled_story(client)
    response = _patch_breakdown(
        client,
        story["id"],
        optimized_content="优化后的完整故事……",
        characters=[
            {"name": "我", "role": "男主", "appearance": "短发，休闲装。"},
            {"name": "小八老师", "role": "女主", "appearance": "鹅蛋脸，衬衫。"},
        ],
    )
    assert response.status_code == 200, response.text
    return story, response.json()


def _count(app, model) -> int:
    with app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_get_breakdown_missing_returns_null(client, story):
    response = client.get(f"/api/stories/{story['id']}/breakdown")
    assert response.status_code == 200
    assert response.json() is None


def test_breakdown_story_not_found(client):
    assert (
        client.get("/api/stories/9999/breakdown").json()["code"]
        == "STORY_NOT_FOUND"
    )
    response = _patch_breakdown(client, 9999, optimized_content="x")
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"


def test_patch_requires_art_style(client, story):
    """没有有效画风时不能创建拆解结果。"""
    response = _patch_breakdown(client, story["id"], optimized_content="优化文")
    assert response.status_code == 422
    assert response.json()["code"] == "ART_STYLE_REQUIRED"


def test_patch_creates_and_snapshots_style(client):
    story, breakdown = _prepare(client)

    assert breakdown["story_id"] == story["id"]
    assert breakdown["optimized_content"] == "优化后的完整故事……"
    assert [card["name"] for card in breakdown["characters"]] == [
        "我",
        "小八老师",
    ]
    assert breakdown["art_style_id"] == "style-a"
    assert breakdown["art_style_name"] == "唯美彩铅"
    assert breakdown["art_style_content"] == "韩式唯美彩铅手绘"
    assert breakdown["is_content_stale"] is False
    assert breakdown["is_art_style_stale"] is False
    assert breakdown["pages"] == []
    assert breakdown["created_at"].endswith("Z")


def test_patch_partial_update_keeps_fields(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    response = _patch_breakdown(
        client, story_id, group_photo_prompt="人物合影提示词……"
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["group_photo_prompt"] == "人物合影提示词……"
    # 未提供的字段保持不变
    assert data["optimized_content"] == "优化后的完整故事……"
    assert len(data["characters"]) == 2


def test_patch_empty_payload_rejected(client):
    story, _ = _prepare(client)
    response = client.patch(
        f"/api/stories/{story['id']}/breakdown", json={}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_breakdown_stale_flags(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    # 修改原文后提示内容过期
    updated = client.put(
        f"/api/stories/{story_id}",
        json={
            "name": "拆解故事",
            "content": "新的原文内容",
            "cover_filename": None,
            "art_style_id": "style-a",
        },
    )
    assert updated.status_code == 200, updated.text
    got = client.get(f"/api/stories/{story_id}/breakdown").json()
    assert got["is_content_stale"] is True
    assert got["is_art_style_stale"] is False

    # 更换画风后提示画风过期
    updated = client.put(
        f"/api/stories/{story_id}",
        json={
            "name": "拆解故事",
            "content": "新的原文内容",
            "cover_filename": None,
            "art_style_id": "style-b",
        },
    )
    assert updated.status_code == 200, updated.text
    got = client.get(f"/api/stories/{story_id}/breakdown").json()
    assert got["is_art_style_stale"] is True


def test_patch_refreshes_style_snapshot_on_rerun(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    client.put(
        f"/api/stories/{story_id}",
        json={
            "name": "拆解故事",
            "content": "第一次相亲的故事",
            "cover_filename": None,
            "art_style_id": "style-b",
        },
    )
    response = _patch_breakdown(client, story_id, group_photo_prompt="新合影")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["art_style_id"] == "style-b"
    assert data["art_style_name"] == "日系赛璐璐"
    assert data["is_art_style_stale"] is False


def test_dangling_style_still_allows_editing(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    # 删除画风后，既有拆解仍可编辑，但会标记画风过期
    _save_art_styles(client, [], active_id=None)
    response = _patch_breakdown(client, story_id, group_photo_prompt="继续编辑")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["art_style_id"] == "style-a"
    assert data["is_art_style_stale"] is True


def test_page_upsert_sorted_and_replaced(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    assert _put_page(client, story_id, 2).status_code == 200
    assert _put_page(client, story_id, 1).status_code == 200

    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert [page["page_number"] for page in pages] == [1, 2]

    response = _put_page(
        client, story_id, 1, narration_main="改写后的首图提问"
    )
    assert response.status_code == 200
    assert response.json()["page_number"] == 1

    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert len(pages) == 2
    assert pages[0]["narration_main"] == "改写后的首图提问"


def test_page_role_saved_and_optional(client):
    """页面作用写回后原样返回；未传时默认为空字符串（兼容旧拆解）。"""
    story, _ = _prepare(client)
    story_id = story["id"]

    response = _put_page(client, story_id, 1, page_role="  钩子封面  ")
    assert response.status_code == 200
    assert response.json()["page_role"] == "钩子封面"

    # 旧数据或未标注的页面不传该字段，仍可正常写入并读回空字符串
    response = _put_page(client, story_id, 2)
    assert response.status_code == 200
    assert response.json()["page_role"] == ""

    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert [page["page_role"] for page in pages] == ["钩子封面", ""]

    # 超过长度限制会被拒绝，避免写入异常值
    assert _put_page(client, story_id, 3, page_role="x" * 21).status_code == 422


def test_page_requires_breakdown(client):
    _save_art_styles(client, [STYLE_A])
    story = _create_styled_story(client)

    response = _put_page(client, story["id"], 1)
    assert response.status_code == 404
    assert response.json()["code"] == "BREAKDOWN_NOT_FOUND"


def test_page_validation(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    invalid_shot = _put_page(client, story_id, 1, shot_type="近景")
    assert invalid_shot.status_code == 422

    empty_prompt = _put_page(client, story_id, 1, image_prompt="   ")
    assert empty_prompt.status_code == 422

    too_many_dialogues = _put_page(
        client, story_id, 1, dialogues=["a", "b", "c"]
    )
    assert too_many_dialogues.status_code == 422

    assert (
        client.put(
            f"/api/stories/{story_id}/breakdown/pages/0",
            json=_page_payload(),
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/stories/{story_id}/breakdown/pages/201",
            json=_page_payload(),
        ).status_code
        == 422
    )


def test_delete_page_and_clear_pages(client):
    story, _ = _prepare(client)
    story_id = story["id"]
    for number in (1, 2, 3):
        assert _put_page(client, story_id, number).status_code == 200

    assert (
        client.delete(
            f"/api/stories/{story_id}/breakdown/pages/2"
        ).status_code
        == 204
    )
    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert [page["page_number"] for page in pages] == [1, 3]

    # 重复删除同一页码保持幂等
    assert (
        client.delete(
            f"/api/stories/{story_id}/breakdown/pages/2"
        ).status_code
        == 204
    )

    assert (
        client.delete(
            f"/api/stories/{story_id}/breakdown/pages"
        ).status_code
        == 204
    )
    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert pages == []


def test_delete_breakdown_is_idempotent(client):
    story, _ = _prepare(client)
    story_id = story["id"]
    _put_page(client, story_id, 1)

    assert (
        client.delete(f"/api/stories/{story_id}/breakdown").status_code == 204
    )
    assert client.get(f"/api/stories/{story_id}/breakdown").json() is None
    assert (
        client.delete(f"/api/stories/{story_id}/breakdown").status_code == 204
    )


def test_delete_story_cascades_breakdown_and_post_config(client, app):
    story, _ = _prepare(client)
    story_id = story["id"]
    _put_page(client, story_id, 1)
    response = client.put(
        f"/api/stories/{story_id}/post-config",
        json={"title": "标题", "content": "正文"},
    )
    assert response.status_code == 200

    assert _count(app, StoryBreakdown) == 1
    assert _count(app, StoryPostConfig) == 1

    assert client.delete(f"/api/stories/{story_id}").status_code == 204
    assert _count(app, StoryBreakdown) == 0
    assert _count(app, StoryPostConfig) == 0


def test_delete_story_blocked_by_posts_keeps_breakdown(client, app):
    story, _ = _prepare(client)
    story_id = story["id"]
    post = client.post(
        "/api/posts",
        json={"story_id": story_id, "title": "标题", "content": "正文"},
    )
    assert post.status_code == 201

    response = client.delete(f"/api/stories/{story_id}")
    assert response.status_code == 409
    assert response.json()["code"] == "STORY_HAS_POSTS"
    assert _count(app, StoryBreakdown) == 1
