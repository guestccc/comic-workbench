"""设计建议库接口测试。"""

from __future__ import annotations

from tests.test_uploads import PNG_BYTES


def _create_feedback(client, **overrides):
    payload = {
        "title": "封面表情太克制",
        "content": "小红书建议：人物表情要更有冲击力，不要安静克制。",
        "source": "xiaohongshu",
        "category": "cover",
        "scope": "global",
        "priority": "high",
        "tags": [" 表情 ", "冲击力", "表情"],
    }
    payload.update(overrides)
    response = client.post("/api/design-feedbacks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_design_feedback_crud(client):
    created = _create_feedback(client)
    assert created["status"] == "open"
    assert created["application_count"] == 0
    assert created["tags"] == ["表情", "冲击力"]

    listed = client.get("/api/design-feedbacks").json()
    assert [item["id"] for item in listed] == [created["id"]]

    got = client.get(f"/api/design-feedbacks/{created['id']}").json()
    assert got["title"] == "封面表情太克制"
    assert got["applications"] == []

    updated = client.patch(
        f"/api/design-feedbacks/{created['id']}",
        json={"title": "封面表情要有冲击力", "status": "verified"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "封面表情要有冲击力"
    assert updated.json()["status"] == "verified"

    deleted = client.delete(f"/api/design-feedbacks/{created['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/design-feedbacks/{created['id']}").status_code == 404


def test_design_feedback_scope_validation(client, story):
    missing_story = client.post(
        "/api/design-feedbacks",
        json={
            "title": "缺故事",
            "content": "指定故事但没有故事 id",
            "scope": "story",
        },
    )
    assert missing_story.status_code == 422

    missing_chapter = client.post(
        "/api/design-feedbacks",
        json={
            "title": "缺章节",
            "content": "指定章节但没有章节号",
            "scope": "chapter",
            "story_id": story["id"],
        },
    )
    assert missing_chapter.status_code == 422

    normalized = _create_feedback(
        client,
        scope="global",
        story_id=story["id"],
        chapter_number=3,
    )
    assert normalized["story_id"] is None
    assert normalized["chapter_number"] is None

    scoped = _create_feedback(
        client,
        scope="chapter",
        story_id=story["id"],
        chapter_number=3,
    )
    assert scoped["story_id"] == story["id"]
    assert scoped["chapter_number"] == 3


def test_design_feedback_screenshot_cleanup(client, app_settings):
    upload = client.post(
        "/api/uploads",
        files={"file": ("shot.png", PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 201, upload.text
    filename = upload.json()["filename"]

    created = _create_feedback(client, screenshot_filename=filename)
    assert created["screenshot_url"] == f"/uploads/{filename}"
    assert (app_settings.upload_dir / filename).is_file()

    assert client.delete(f"/api/design-feedbacks/{created['id']}").status_code == 204
    assert not (app_settings.upload_dir / filename).exists()


def test_design_feedback_screenshot_only(client):
    """用户只给截图时，标题自动生成，正文可以为空。"""
    upload = client.post(
        "/api/uploads",
        files={"file": ("shot-only.png", PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 201, upload.text
    filename = upload.json()["filename"]

    response = client.post(
        "/api/design-feedbacks",
        json={"screenshot_filename": filename, "source": "xiaohongshu"},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["content"] == ""
    assert created["title"].startswith("截图建议")

    cleared = client.patch(
        f"/api/design-feedbacks/{created['id']}",
        json={"screenshot_filename": None, "content": ""},
    )
    assert cleared.status_code == 422


def test_design_feedback_requires_material(client):
    """截图和原文都没有时拒绝创建，避免空建议。"""
    response = client.post(
        "/api/design-feedbacks",
        json={"title": "空建议", "content": ""},
    )
    assert response.status_code == 422


def test_design_feedback_application_status(client, story):
    created = _create_feedback(client)
    response = client.post(
        f"/api/design-feedbacks/{created['id']}/applications",
        json={
            "target_type": "cover",
            "story_id": story["id"],
            "chapter_number": 1,
            "summary": "把副标题改成悬念句，主标题保留",
            "before_prompt": "旧提示词",
            "after_prompt": "新提示词",
            "before_image_url": "/uploads/before.png",
            "after_image_url": "/uploads/after.png",
        },
    )
    assert response.status_code == 201, response.text
    application = response.json()
    assert application["story_name"] == story["name"]

    detail = client.get(f"/api/design-feedbacks/{created['id']}").json()
    assert detail["status"] == "applied"
    assert detail["application_count"] == 1
    assert detail["applications"][0]["summary"].startswith("把副标题")

    deleted = client.delete(
        f"/api/design-feedbacks/{created['id']}/applications/{application['id']}"
    )
    assert deleted.status_code == 204
    detail = client.get(f"/api/design-feedbacks/{created['id']}").json()
    assert detail["status"] == "open"
    assert detail["application_count"] == 0


def test_design_feedback_application_validation(client, story):
    created = _create_feedback(client)
    base = {
        "target_type": "cover",
        "story_id": story["id"],
        "summary": "改封面",
    }
    missing_chapter = client.post(
        f"/api/design-feedbacks/{created['id']}/applications", json=base
    )
    assert missing_chapter.status_code == 422

    missing_page = client.post(
        f"/api/design-feedbacks/{created['id']}/applications",
        json={"target_type": "page", "story_id": story["id"], "summary": "改正文"},
    )
    assert missing_page.status_code == 422

    page_with_page = client.post(
        f"/api/design-feedbacks/{created['id']}/applications",
        json={
            "target_type": "cover",
            "story_id": story["id"],
            "chapter_number": 1,
            "page_number": 2,
            "summary": "错误组合",
        },
    )
    assert page_with_page.status_code == 422

    missing_story = client.post(
        f"/api/design-feedbacks/{created['id']}/applications",
        json={
            "target_type": "cover",
            "story_id": 99999,
            "chapter_number": 1,
            "summary": "不存在的故事",
        },
    )
    assert missing_story.status_code == 404


def test_delete_feedback_cascades_applications(client, story):
    created = _create_feedback(client)
    application = client.post(
        f"/api/design-feedbacks/{created['id']}/applications",
        json={
            "target_type": "cover",
            "story_id": story["id"],
            "chapter_number": 1,
            "summary": "删除建议前的应用",
        },
    )
    assert application.status_code == 201, application.text

    assert client.delete(f"/api/design-feedbacks/{created['id']}").status_code == 204
    assert (
        client.get(f"/api/design-feedbacks/{created['id']}").status_code == 404
    )


def test_delete_story_keeps_feedback_and_removes_applications(client, story):
    created = _create_feedback(
        client, scope="story", story_id=story["id"]
    )
    application = client.post(
        f"/api/design-feedbacks/{created['id']}/applications",
        json={
            "target_type": "cover",
            "story_id": story["id"],
            "chapter_number": 1,
            "summary": "删除故事前的应用",
        },
    )
    assert application.status_code == 201, application.text

    assert client.delete(f"/api/stories/{story['id']}").status_code == 204

    detail = client.get(f"/api/design-feedbacks/{created['id']}").json()
    assert detail["story_id"] is None
    assert detail["applications"] == []


def test_design_feedback_filters(client, story):
    first = _create_feedback(client, title="封面建议", category="cover")
    second = _create_feedback(
        client,
        title="漫画建议",
        category="comic",
        scope="story",
        story_id=story["id"],
    )
    client.patch(
        f"/api/design-feedbacks/{second['id']}", json={"status": "archived"}
    )

    by_category = client.get(
        "/api/design-feedbacks", params={"category": "comic"}
    ).json()
    assert [item["id"] for item in by_category] == [second["id"]]

    by_status = client.get(
        "/api/design-feedbacks", params={"status": "archived"}
    ).json()
    assert [item["id"] for item in by_status] == [second["id"]]

    by_story = client.get(
        "/api/design-feedbacks", params={"story_id": story["id"]}
    ).json()
    assert [item["id"] for item in by_story] == [second["id"]]

    by_keyword = client.get(
        "/api/design-feedbacks", params={"keyword": "封面建议"}
    ).json()
    assert [item["id"] for item in by_keyword] == [first["id"]]


STYLE = {"id": "style-a", "name": "唯美彩铅", "content": "韩式唯美彩铅手绘"}


def _create_styled_story(client):
    response = client.put(
        "/api/settings/art-styles",
        json={"styles": [STYLE], "active_id": "style-a"},
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/stories",
        json={
            "name": "排版测试故事",
            "content": "故事原文",
            "art_style_id": "style-a",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_design_feedback_promote_and_render_rule(client):
    story = _create_styled_story(client)
    created = _create_feedback(client)
    rule_text = "封面人物必须出现强情绪，禁止平静克制"

    promoted = client.post(
        f"/api/design-feedbacks/{created['id']}/promote",
        json={"rule_text": rule_text, "rule_target": "cover"},
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["is_rule"] is True
    assert promoted.json()["status"] == "verified"
    assert promoted.json()["rule_text"] == rule_text

    cover = client.post(
        "/api/settings/prompt-templates/render",
        json={
            "template_type": "cover",
            "story_id": story["id"],
            "context": {
                "content": "近景，人物含泪看向镜头",
                "character_consistency": "遵循角色卡",
                "narration_main": "她终于抬头",
                "narration_sub": "这一次她不再退让",
                "narration_highlight": "抬头",
                "label": "第1章 · 测试",
                "chapter_number": 1,
            },
        },
    )
    assert cover.status_code == 200, cover.text
    assert "【规则要求】" in cover.json()["prompt"]
    assert rule_text in cover.json()["prompt"]

    body = client.post(
        "/api/settings/prompt-templates/render",
        json={
            "template_type": "body",
            "story_id": story["id"],
            "context": {
                "content": "中景，人物站在窗边",
                "character_consistency": "遵循角色卡",
                "narration_main": "窗外下雨",
                "narration_sub": "她想起那天",
                "narration_highlight": "下雨",
                "page_number": 1,
                "chapter_number": 1,
            },
        },
    )
    assert body.status_code == 200, body.text
    assert rule_text not in body.json()["prompt"]


def test_design_feedback_remove_rule(client):
    created = _create_feedback(client)
    client.post(
        f"/api/design-feedbacks/{created['id']}/promote",
        json={"rule_text": "封面必须用悬念句", "rule_target": "all"},
    )
    removed = client.delete(f"/api/design-feedbacks/{created['id']}/promote")
    assert removed.status_code == 200, removed.text
    assert removed.json()["is_rule"] is False
    assert removed.json()["rule_text"] == ""
    assert removed.json()["status"] == "open"
