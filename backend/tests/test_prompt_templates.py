"""正文 / 封面提示词模板：默认值、校验、统一渲染。"""

from __future__ import annotations

from tests.test_breakdowns import (
    STYLE_A,
    _create_styled_story,
    _save_art_styles,
)

BODY_CONTEXT = {
    "content": "火车站候车厅，白天，{{我}}站在安检机旁。",
    "character_consistency": "严格遵循 {{我}} 的角色卡与参考垫图。",
    "narration_main": "这一次我不等了",
    "narration_sub": "我站在站台上；\n风很冷。",
    "narration_highlight": "不等了",
    "dialogues": ["我：走吧。"],
    "page_number": 3,
}

COVER_CONTEXT = {
    "content": "3:4竖版封面，{{韩春晓}}在安检口回头。",
    "character_consistency": "严格遵循 {{韩春晓}} 的角色卡与参考垫图。",
    "narration_main": "箱子里出现了两把枪",
    "narration_sub": "拉链一开，两把枪。",
    "narration_highlight": "两把枪",
    "dialogues": [],
    "label": "第4章 · 两把枪",
}


def _prepare(client):
    _save_art_styles(client, [STYLE_A], active_id="style-a")
    return _create_styled_story(client)


def test_prompt_templates_defaults(client):
    response = client.get("/api/settings/prompt-templates")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["body_is_default"] is True
    assert data["cover_is_default"] is True
    assert data["body_default"] != data["cover_default"]
    for key in ("art_style", "content", "text_zone", "negative_prompt"):
        assert "{" + key + "}" in data["body"]
        assert "{" + key + "}" in data["cover"]
    assert "{page_number}" in data["body"]
    assert "{cover_mode}" in data["cover"]


def test_render_body_injects_style_text_zone_and_page(client):
    story = _prepare(client)
    response = client.post(
        "/api/settings/prompt-templates/render",
        json={
            "template_type": "body",
            "story_id": story["id"],
            "context": BODY_CONTEXT,
        },
    )
    assert response.status_code == 200, response.text
    prompt = response.json()["prompt"]
    assert STYLE_A["content"] in prompt
    assert "【画面】火车站候车厅" in prompt
    assert "「这一次我不等了」" in prompt
    assert "「不等了」3字为红色手写加粗" in prompt
    assert "第一行「我站在站台上；」" in prompt
    assert "第二行「风很冷。」" in prompt
    assert "气泡文字：走吧。｜说话人：我" in prompt
    assert "纯白色实心填充" in prompt
    assert "「第3页」" in prompt
    assert "纯黑背景" in prompt
    assert "额外页码" in prompt
    assert "多余对话气泡" in prompt
    assert "页码，对话气泡" not in prompt
    assert "角色性别、年龄与体态以角色卡" in prompt
    assert "不得套用画风描述中的女性基准" in prompt
    assert "至少 3 条" not in prompt
    assert "冲击线铺满全图" not in prompt
    assert "冲击线像贴图" not in prompt


def test_body_highlight_in_both_marks_main_only(client):
    story = _prepare(client)
    context = dict(BODY_CONTEXT)
    context.update(
        {
            "narration_main": "连墓碑都没有",
            "narration_sub": "四十年过去，坟丘只剩半人高的土堆。\n连一块墓碑都没有。",
            "narration_highlight": "墓碑",
            "dialogues": [],
        }
    )
    response = client.post(
        "/api/settings/prompt-templates/render",
        json={
            "template_type": "body",
            "story_id": story["id"],
            "context": context,
        },
    )
    assert response.status_code == 200, response.text
    prompt = response.json()["prompt"]
    assert prompt.count("字为红色手写加粗") == 1
    assert "除主旁白外不得出现任何其他红色文字" in prompt
    assert "除副旁白外不得出现任何其他红色文字" not in prompt


def test_render_cover_injects_cover_mode_and_label(client):
    story = _prepare(client)
    response = client.post(
        "/api/settings/prompt-templates/render",
        json={
            "template_type": "cover",
            "story_id": story["id"],
            "context": COVER_CONTEXT,
        },
    )
    assert response.status_code == 200, response.text
    prompt = response.json()["prompt"]
    assert STYLE_A["content"] in prompt
    assert "【封面模式】原画风 + 封面专用冲击层" in prompt
    assert "人物周围加入漫画黑色震动短线" in prompt
    assert "冲击线和关键轮廓用较粗的黑色手绘线" in prompt
    assert "人物面部与皮肤仍保持淡色铅笔的柔和质感" in prompt
    assert "至少 3 条" in prompt
    assert "手绘抖动" in prompt
    assert "至少 2 处" in prompt
    assert "至少 2 处尺寸清晰可辨的锯齿情绪漫符" in prompt
    assert "页码，对话气泡" in prompt
    assert "额外页码" not in prompt
    assert "角色性别、年龄与体态以角色卡" in prompt
    assert "冲击线铺满全图" in prompt
    assert "冲击线像贴图" in prompt
    assert "顶部小字：第4章 · 两把枪" in prompt
    assert "主标题：箱子里出现了两把枪" in prompt
    assert "「两把枪」3字为红色手写加粗" in prompt
    assert "【页码】" not in prompt
    assert "不整体提高对比度" in prompt


def test_save_templates_rejects_missing_placeholder(client):
    response = client.put(
        "/api/settings/prompt-templates",
        json={
            "body": "【画风】{art_style}\n{content}\n{page_number}",
            "cover": "【画风】{art_style}\n{content}\n{text_zone}\n{cover_mode}\n{negative_prompt}",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PROMPT_TEMPLATE_MISSING_PLACEHOLDER"


def test_save_templates_rejects_unknown_placeholder(client):
    response = client.put(
        "/api/settings/prompt-templates",
        json={
            "body": (
                "【画风】{art_style}\n{content}\n{text_zone}\n"
                "{page_number}\n{negative_prompt}\n{unknown}"
            ),
            "cover": (
                "【画风】{art_style}\n{content}\n{text_zone}\n"
                "{cover_mode}\n{negative_prompt}"
            ),
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PROMPT_TEMPLATE_UNKNOWN_PLACEHOLDER"


def test_save_and_render_custom_templates(client):
    story = _prepare(client)
    body = (
        "【画风】{art_style}\n【画面】{content}\n"
        "【角色一致性】{character_consistency}\n{text_zone}\n"
        "【页码】第{page_number}页\n【负面提示词】{negative_prompt}"
    )
    cover = (
        "【画风】{art_style}\n【画面】{content}\n"
        "【角色一致性】{character_consistency}\n【封面模式】{cover_mode}\n"
        "{text_zone}\n【负面提示词】{negative_prompt}"
    )
    saved = client.put(
        "/api/settings/prompt-templates",
        json={"body": body, "cover": cover},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["body_is_default"] is False

    rendered = client.post(
        "/api/settings/prompt-templates/render",
        json={
            "template_type": "body",
            "story_id": story["id"],
            "context": BODY_CONTEXT,
        },
    )
    assert rendered.status_code == 200, rendered.text
    prompt = rendered.json()["prompt"]
    assert "【画面】火车站候车厅" in prompt
    assert "第3页" in prompt


def test_render_requires_valid_style(client):
    story = client.post(
        "/api/stories",
        json={"name": "无画风", "content": "没有选择画风的故事。"},
    ).json()
    response = client.post(
        "/api/settings/prompt-templates/render",
        json={
            "template_type": "body",
            "story_id": story["id"],
            "context": BODY_CONTEXT,
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ART_STYLE_REQUIRED"


def test_template_versions_and_restore(client):
    current = client.get("/api/settings/prompt-templates").json()
    new_body = current["body"] + "\n【自定义段落】测试版本"
    saved = client.put(
        "/api/settings/prompt-templates",
        json={"body": new_body, "cover": current["cover"]},
    )
    assert saved.status_code == 200, saved.text

    versions = client.get(
        "/api/settings/prompt-templates/versions",
        params={"template_type": "body"},
    )
    assert versions.status_code == 200, versions.text
    items = versions.json()
    assert items
    assert items[0]["content"] == new_body
    assert items[0]["template_type"] == "body"

    restored = client.post(
        f"/api/settings/prompt-templates/versions/{items[0]['id']}/restore"
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["body"] == new_body
