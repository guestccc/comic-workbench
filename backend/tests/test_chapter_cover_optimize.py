"""AI 优化章节封面三项（主标题 / 副标题 / 画面提示词）的接口测试。"""

from __future__ import annotations

import json

from tests.conftest import make_response
from tests.test_breakdowns import (
    _chapter_payload,
    _mapping_items,
    _patch_breakdown,
    _prepare,
)

MAIN = "这一次，我先按了警报"
SUB = "我在车站做了三年安检，重生回拦下五个学生的这一天。"
LABEL = "第1章 · 这次先按警报"
HIGHLIGHT = "先按了警报"
IMAGE_PROMPT = (
    "【画风】韩式唯美彩铅手绘。\n"
    f"【画面】安检口，主角按下红色警报按钮，文字区写「{LABEL}」。\n"
    f"【文字区】主旁白「{MAIN}」，副旁白「{SUB}」。\n"
    "【负面提示词】低俗。"
)


def _prepare_with_chapters(client):
    story, _ = _prepare(client)
    story_id = story["id"]
    assert (
        _patch_breakdown(
            client, story_id, mapping=_mapping_items([1, 2, 3, 4])
        ).status_code
        == 200
    )
    assert (
        _patch_breakdown(
            client,
            story_id,
            chapters=[
                _chapter_payload(1, [1, 2]),
                _chapter_payload(2, [3, 4]),
            ],
        ).status_code
        == 200
    )
    return story


def _payload(**overrides) -> dict:
    data = {
        "chapter_title": "这次先按警报",
        "cover_label": LABEL,
        "cover_main": MAIN,
        "cover_sub": SUB,
        "cover_highlight": HIGHLIGHT,
        "current_prompt": "旧封面提示词。",
        "suggestion": "让封面更有悬念，突出主角按警报的瞬间。",
    }
    data.update(overrides)
    return data


def _result(**overrides) -> dict:
    data = {
        "narration_main": MAIN,
        "narration_sub": SUB,
        "image_prompt": IMAGE_PROMPT,
    }
    data.update(overrides)
    return data


def test_missing_key_returns_409(client):
    story = _prepare_with_chapters(client)
    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/optimize",
        json=_payload(),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DEEPSEEK_KEY_MISSING"


def test_requires_breakdown_and_chapter(client, story):
    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/optimize",
        json=_payload(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "BREAKDOWN_NOT_FOUND"

    story = _prepare_with_chapters(client)
    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/9/cover/optimize",
        json=_payload(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "CHAPTER_NOT_FOUND"


def test_story_not_found(client):
    response = client.post(
        "/api/stories/9999/breakdown/chapters/1/cover/optimize",
        json=_payload(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"


def test_validation(client, configure_key):
    story = _prepare_with_chapters(client)
    url = f"/api/stories/{story['id']}/breakdown/chapters/1/cover/optimize"

    # 当前提示词允许为空（直接新生成），但建议不能为空
    assert (
        client.post(url, json=_payload(suggestion="   ")).status_code == 422
    )


def test_empty_current_prompt_can_generate_from_scratch(
    client, configure_key, mock_deepseek
):
    story = _prepare_with_chapters(client)
    mock_deepseek["response"] = make_response(
        raw_content=json.dumps(_result(), ensure_ascii=False)
    )

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/optimize",
        json=_payload(current_prompt=""),
    )
    assert response.status_code == 200, response.text
    system_prompt = mock_deepseek["calls"][0][1][0]["content"]
    assert "当前画面提示词" in system_prompt
    assert "直接生成一份完整新版封面提示词" in system_prompt


def test_success_returns_three_fields(
    client, configure_key, mock_deepseek
):
    story = _prepare_with_chapters(client)
    mock_deepseek["response"] = make_response(
        raw_content=json.dumps(_result(), ensure_ascii=False)
    )

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/optimize",
        json=_payload(),
    )

    assert response.status_code == 200, response.text
    assert response.json() == _result()

    api_key, messages = mock_deepseek["calls"][0]
    assert api_key == "sk-test-abcd"
    system_prompt = messages[0]["content"]
    assert "拆解故事" in system_prompt
    assert "这次先按警报" in system_prompt
    assert "唯美彩铅" in system_prompt
    assert LABEL in system_prompt
    assert MAIN in system_prompt
    assert HIGHLIGHT in system_prompt
    assert SUB in system_prompt
    assert "旧封面提示词" in system_prompt
    assert "只允许你修改三项" in system_prompt
    assert messages[-1] == {
        "role": "user",
        "content": "让封面更有悬念，突出主角按警报的瞬间。",
    }

    # 非流式 JSON 模式
    assert mock_deepseek["calls"][0][1][0]["role"] == "system"
    assert response.json()["narration_main"] == MAIN


def test_highlight_must_stay_in_new_titles(
    client, configure_key, mock_deepseek
):
    story = _prepare_with_chapters(client)
    mock_deepseek["response"] = make_response(
        raw_content=json.dumps(
            _result(narration_main="这一次我按下了警报"),
            ensure_ascii=False,
        )
    )

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/optimize",
        json=_payload(),
    )
    assert response.status_code == 502
    assert response.json()["code"] == "AI_COVER_HIGHLIGHT_MISSING"


def test_main_title_length_is_enforced(
    client, configure_key, mock_deepseek
):
    story = _prepare_with_chapters(client)
    long_main = "这一次" + "我" * 20
    mock_deepseek["response"] = make_response(
        raw_content=json.dumps(
            _result(narration_main=long_main),
            ensure_ascii=False,
        )
    )

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/optimize",
        json=_payload(),
    )
    assert response.status_code == 502
    assert response.json()["code"] == "AI_COVER_TEXT_INVALID"


def test_image_prompt_must_keep_label(
    client, configure_key, mock_deepseek
):
    story = _prepare_with_chapters(client)
    mock_deepseek["response"] = make_response(
        raw_content=json.dumps(
            _result(image_prompt="【画面】没有保留顶部小字。"),
            ensure_ascii=False,
        )
    )

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/optimize",
        json=_payload(),
    )
    assert response.status_code == 502
    assert response.json()["code"] == "AI_COVER_RESULT_INVALID"
