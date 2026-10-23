"""原文 → 优化文 AI 解读接口测试（DeepSeek 全部 mock）。"""

from __future__ import annotations

import json

from tests.conftest import make_response

STYLE = {"id": "style-a", "name": "唯美彩铅", "content": "韩式唯美彩铅手绘"}

ANALYSIS_PAYLOAD = {
    "summary": "把开头改成提问，先制造悬念，再强化情绪爆点。",
    "changes": [
        {
            "kind": "钩子",
            "original": "",
            "optimized": "一个女生开口问你有没有 A8，你会怎么回答？",
            "why": "先抛问题，让读者想继续看女主怎么回答。",
        },
        {
            "kind": "保留",
            "original": "小八老师：你应该有A8吧？",
            "optimized": "小八老师：你应该有A8吧？",
            "why": "原句本身就是爆点，直接保留了这句有冲击力的台词。",
        },
    ],
}


def _prepare(client, content: str = "第一次相亲的故事。"):
    """准备画风、故事与优化后文章。"""
    response = client.put(
        "/api/settings/art-styles",
        json={"styles": [STYLE], "active_id": "style-a"},
    )
    assert response.status_code == 200, response.text

    response = client.post(
        "/api/stories",
        json={
            "name": "拆解故事",
            "content": content,
            "art_style_id": "style-a",
        },
    )
    assert response.status_code == 201, response.text
    story = response.json()

    response = client.patch(
        f"/api/stories/{story['id']}/breakdown",
        json={"optimized_content": "优化后的故事……"},
    )
    assert response.status_code == 200, response.text
    return story


def _analyze(client, story_id: int):
    return client.post(f"/api/stories/{story_id}/breakdown/analyze")


def _analysis_response(payload: dict | None = None, **kwargs):
    return make_response(
        raw_content=json.dumps(payload or ANALYSIS_PAYLOAD, ensure_ascii=False),
        **kwargs,
    )


def test_analyze_requires_key(client, mock_deepseek):
    story = _prepare(client)
    response = _analyze(client, story["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "DEEPSEEK_KEY_MISSING"
    # 未配置 Key 时不应发起任何外部请求
    assert mock_deepseek["calls"] == []


def test_analyze_story_not_found(client, configure_key, mock_deepseek):
    response = _analyze(client, 9999)
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"
    assert mock_deepseek["calls"] == []


def test_analyze_without_breakdown(client, configure_key, mock_deepseek):
    client.put(
        "/api/settings/art-styles",
        json={"styles": [STYLE], "active_id": "style-a"},
    )
    story = client.post(
        "/api/stories",
        json={"name": "新故事", "content": "原文", "art_style_id": "style-a"},
    ).json()

    response = _analyze(client, story["id"])
    assert response.status_code == 404
    assert response.json()["code"] == "BREAKDOWN_NOT_FOUND"
    assert mock_deepseek["calls"] == []


def test_analyze_success(client, configure_key, mock_deepseek):
    story = _prepare(client)
    mock_deepseek["response"] = _analysis_response()

    response = _analyze(client, story["id"])
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["summary"] == ANALYSIS_PAYLOAD["summary"]
    assert [item["kind"] for item in data["changes"]] == ["钩子", "保留"]
    assert data["changes"][1]["why"] == "原句本身就是爆点，直接保留了这句有冲击力的台词。"

    # 校验上游请求：使用 SQLite 中的 Key，两篇文本都要发送，且要求 JSON 输出
    api_key, messages = mock_deepseek["calls"][0]
    assert api_key == "sk-test-abcd"
    user_prompt = messages[1]["content"]
    assert "第一次相亲的故事。" in user_prompt
    assert "优化后的故事……" in user_prompt
    assert "json" in messages[0]["content"]


def test_analyze_too_long(client, configure_key, mock_deepseek):
    story = _prepare(client, content="字" * 30_000)
    response = client.patch(
        f"/api/stories/{story['id']}/breakdown",
        json={"optimized_content": "改" * 20_000},
    )
    assert response.status_code == 200, response.text

    response = _analyze(client, story["id"])
    assert response.status_code == 422
    assert response.json()["code"] == "OPTIMIZE_ANALYZE_TOO_LONG"
    assert mock_deepseek["calls"] == []


def test_analyze_bad_output_retries_once(client, configure_key, mock_deepseek):
    story = _prepare(client)
    mock_deepseek["response"] = [
        make_response(raw_content="这不是 JSON"),
        make_response(raw_content="仍然不是 JSON"),
    ]

    response = _analyze(client, story["id"])
    assert response.status_code == 502
    assert response.json()["code"] == "DEEPSEEK_BAD_OUTPUT"
    assert len(mock_deepseek["calls"]) == 2


def test_analyze_bad_output_then_success(client, configure_key, mock_deepseek):
    story = _prepare(client)
    mock_deepseek["response"] = [
        make_response(raw_content="不是 JSON"),
        _analysis_response(),
    ]

    response = _analyze(client, story["id"])
    assert response.status_code == 200
    assert response.json()["summary"] == ANALYSIS_PAYLOAD["summary"]
    assert len(mock_deepseek["calls"]) == 2


def test_analyze_markdown_fenced_json(client, configure_key, mock_deepseek):
    story = _prepare(client)
    fenced = f"```json\n{json.dumps(ANALYSIS_PAYLOAD, ensure_ascii=False)}\n```"
    mock_deepseek["response"] = make_response(raw_content=fenced)

    response = _analyze(client, story["id"])
    assert response.status_code == 200
    assert response.json()["changes"][0]["kind"] == "钩子"


def test_analyze_reuses_cache_when_content_unchanged(
    client, configure_key, mock_deepseek
):
    """原文与优化文不变时，第二次解读直接读缓存，不再调用模型。"""
    story = _prepare(client)
    mock_deepseek["response"] = _analysis_response()

    first = _analyze(client, story["id"])
    assert first.status_code == 200, first.text
    assert len(mock_deepseek["calls"]) == 1

    second = _analyze(client, story["id"])
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert len(mock_deepseek["calls"]) == 1


def test_analyze_force_bypasses_cache(client, configure_key, mock_deepseek):
    """「重新解读」传 force=true 时忽略缓存，重新调用模型。"""
    story = _prepare(client)
    mock_deepseek["response"] = _analysis_response()

    assert _analyze(client, story["id"]).status_code == 200
    response = client.post(
        f"/api/stories/{story['id']}/breakdown/analyze?force=true"
    )
    assert response.status_code == 200, response.text
    assert len(mock_deepseek["calls"]) == 2


def test_analyze_cache_invalidated_when_optimized_changes(
    client, configure_key, mock_deepseek
):
    """优化文被编辑后，旧解读缓存失效并重新生成。"""
    story = _prepare(client)
    mock_deepseek["response"] = _analysis_response()

    assert _analyze(client, story["id"]).status_code == 200

    response = client.patch(
        f"/api/stories/{story['id']}/breakdown",
        json={"optimized_content": "又改了一版优化后的故事……"},
    )
    assert response.status_code == 200, response.text

    assert _analyze(client, story["id"]).status_code == 200
    assert len(mock_deepseek["calls"]) == 2


def test_analyze_cache_invalidated_when_original_changes(
    client, configure_key, mock_deepseek
):
    """故事原文被修改后，旧解读缓存同样失效。"""
    story = _prepare(client)
    mock_deepseek["response"] = _analysis_response()

    assert _analyze(client, story["id"]).status_code == 200

    response = client.put(
        f"/api/stories/{story['id']}",
        json={
            "name": story["name"],
            "content": "第一次相亲的故事，原文补了一段。",
            "art_style_id": "style-a",
        },
    )
    assert response.status_code == 200, response.text

    assert _analyze(client, story["id"]).status_code == 200
    assert len(mock_deepseek["calls"]) == 2

