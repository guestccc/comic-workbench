"""结构化设计规则接口测试。"""

from __future__ import annotations

from tests.test_design_feedbacks import _create_feedback, _create_styled_story


def _create_rule(client, feedback_id, **overrides):
    payload = {
        "title": "正文每页必须有强情绪",
        "kind": "prompt",
        "target": "body",
        "slot": "scene",
        "scope_type": "chapter",
        "story_id": 1,
        "chapter_numbers": [1],
        "priority": "hard",
        "requirement": "人物必须出现强情绪，至少一项",
        "created_by": "claude",
    }
    payload.update(overrides)
    response = client.post(
        f"/api/design-feedbacks/{feedback_id}/rules", json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_design_rule_draft_activate_update_rollback(client):
    story = _create_styled_story(client)
    feedback = _create_feedback(client)
    rule = _create_rule(client, feedback["id"], story_id=story["id"])
    assert rule["status"] == "draft"
    assert rule["version"] == 1
    assert rule["scope_type"] == "chapter"
    assert rule["chapter_numbers"] == [1]

    preview = client.post(
        "/api/design-rules/preview",
        json={
            "target": "body",
            "scope_type": "chapter",
            "story_id": story["id"],
            "chapter_numbers": [1],
        },
    )
    assert preview.status_code == 200, preview.text
    assert "total" in preview.json()

    activated = client.post(f"/api/design-rules/{rule['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"

    render = client.post(
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
    assert render.status_code == 200, render.text
    result = render.json()
    assert "【规则要求】" in result["prompt"]
    assert result["applied_rules"][0]["id"] == rule["id"]

    updated = client.patch(
        f"/api/design-rules/{rule['id']}",
        json={"requirement": "人物必须含泪或下颌绷紧"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 3
    assert updated.json()["requirement"] == "人物必须含泪或下颌绷紧"

    rolled = client.post(f"/api/design-rules/{rule['id']}/rollback")
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["version"] == 4
    assert rolled.json()["requirement"] == "人物必须出现强情绪，至少一项"

    disabled = client.post(f"/api/design-rules/{rule['id']}/disable")
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"


def test_design_rule_page_scope(client):
    story = _create_styled_story(client)
    feedback = _create_feedback(client)
    rule = _create_rule(
        client,
        feedback["id"],
        story_id=story["id"],
        scope_type="pages",
        chapter_numbers=[1],
        page_numbers=[3],
    )
    client.post(f"/api/design-rules/{rule['id']}/activate")

    def render(page_number: int):
        response = client.post(
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
                    "page_number": page_number,
                    "chapter_number": 1,
                },
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert render(3)["applied_rules"]
    assert render(4)["applied_rules"] == []


def test_design_rule_scope_validation(client):
    story = _create_styled_story(client)
    feedback = _create_feedback(client)
    response = client.post(
        f"/api/design-feedbacks/{feedback['id']}/rules",
        json={
            "title": "缺章节",
            "kind": "prompt",
            "target": "body",
            "scope_type": "chapter",
            "story_id": story["id"],
            "requirement": "必须有表情",
        },
    )
    assert response.status_code == 422

    response = client.post(
        f"/api/design-feedbacks/{feedback['id']}/rules",
        json={
            "title": "封面不能用页码范围",
            "kind": "prompt",
            "target": "cover",
            "scope_type": "pages",
            "story_id": story["id"],
            "chapter_numbers": [1],
            "page_numbers": [1],
            "requirement": "必须有表情",
        },
    )
    assert response.status_code == 422


def test_design_rule_check_and_result(client):
    story = _create_styled_story(client)
    feedback = _create_feedback(client)
    rule = _create_rule(
        client,
        feedback["id"],
        title="封面禁止平静",
        kind="check",
        target="cover",
        scope_type="global",
        requirement="",
        negative_terms=[],
        review_check="",
        check_spec={"type": "forbidden_terms", "terms": ["平静"]},
        created_by="claude",
    )
    client.post(f"/api/design-rules/{rule['id']}/activate")

    def render(content: str):
        response = client.post(
            "/api/settings/prompt-templates/render",
            json={
                "template_type": "cover",
                "story_id": story["id"],
                "context": {
                    "content": content,
                    "character_consistency": "遵循角色卡",
                    "narration_main": "她抬起头",
                    "narration_sub": "这一次她不再退让",
                    "narration_highlight": "抬头",
                    "label": "第1章 · 测试",
                    "chapter_number": 1,
                },
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    failed = render("人物表情平静地看向镜头")
    assert failed["rule_checks"][0]["passed"] is False
    assert "平静" in failed["rule_checks"][0]["message"]

    passed = render("人物含泪看向镜头")
    assert passed["rule_checks"][0]["passed"] is True

    result = client.post(
        f"/api/design-rules/{rule['id']}/results",
        json={
            "result": "failed",
            "story_id": story["id"],
            "target_type": "cover",
            "chapter_number": 1,
            "message": "生成图仍然平静",
            "reviewer": "claude",
        },
    )
    assert result.status_code == 201, result.text
    results = client.get(f"/api/design-rules/{rule['id']}/results").json()
    assert results[0]["result"] == "failed"

    rules = client.get(f"/api/design-feedbacks/{feedback['id']}/rules").json()
    assert rules[0]["check_count"] == 1
    assert rules[0]["failed_count"] == 1
    assert rules[0]["latest_result"] == "failed"


def test_design_rule_write_to_template(client):
    story = _create_styled_story(client)
    feedback = _create_feedback(client)
    rule = _create_rule(
        client,
        feedback["id"],
        title="封面必须出现关键道具",
        target="cover",
        scope_type="global",
        story_id=None,
        chapter_numbers=[],
        requirement="封面必须出现一件关键道具",
    )
    client.post(f"/api/design-rules/{rule['id']}/activate")

    preview = client.post(
        f"/api/design-rules/{rule['id']}/template-preview"
    )
    assert preview.status_code == 200, preview.text
    items = preview.json()["items"]
    assert len(items) == 1
    assert items[0]["template_type"] == "cover"
    assert "【固定规则】" in items[0]["after"]
    assert "封面必须出现一件关键道具" in items[0]["after"]

    applied = client.post(
        f"/api/design-rules/{rule['id']}/apply-to-template"
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result["rule"]["status"] == "disabled"
    assert result["rule"]["template_applied_at"] is not None
    assert "【固定规则】" in result["templates"]["cover"]

    versions = client.get(
        "/api/settings/prompt-templates/versions",
        params={"template_type": "cover"},
    ).json()
    assert versions

    reactivate = client.post(f"/api/design-rules/{rule['id']}/activate")
    assert reactivate.status_code == 422


def test_design_rule_apply_once(client):
    from tests.test_prompt_snapshots import _prepare_story

    story = _prepare_story(client)
    feedback = _create_feedback(client)
    rule = _create_rule(
        client,
        feedback["id"],
        title="仅本次加一条封面要求",
        target="cover",
        scope_type="global",
        story_id=None,
        chapter_numbers=[],
        requirement="封面必须出现关键道具",
    )

    target = {
        "target_type": "cover",
        "story_id": story["id"],
        "chapter_number": 1,
    }
    preview = client.post(
        f"/api/design-rules/{rule['id']}/apply-once/preview", json=target
    )
    assert preview.status_code == 200, preview.text
    assert "【本次规则】" in preview.json()["after"]

    applied = client.post(
        f"/api/design-rules/{rule['id']}/apply-once", json=target
    )
    assert applied.status_code == 200, applied.text
    assert "【本次规则】" in applied.json()["prompt"]

    breakdown = client.get(f"/api/stories/{story['id']}/breakdown").json()
    assert "【本次规则】" in breakdown["chapters"][0]["cover"]["image_prompt"]

    rules = client.get(f"/api/design-feedbacks/{feedback['id']}/rules").json()
    assert rules[0]["status"] == "draft"
    results = client.get(f"/api/design-rules/{rule['id']}/results").json()
    assert results[0]["result"] == "unknown"
    assert results[0]["message"] == "仅本次应用"
