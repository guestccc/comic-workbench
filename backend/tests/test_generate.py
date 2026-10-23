"""AI 文案生成接口测试（DeepSeek 全部 mock，不发真实请求）。"""

from __future__ import annotations

import json

import httpx
import pytest

from tests.conftest import make_copy_options, make_response


def _generate(client, story_id: int):
    return client.post("/api/posts/generate", json={"story_id": story_id})


def test_generate_requires_key(client, story, mock_deepseek):
    response = _generate(client, story["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "DEEPSEEK_KEY_MISSING"
    # 未配置 Key 时不应发起任何外部请求
    assert mock_deepseek["calls"] == []


def test_story_not_found(client, configure_key, mock_deepseek):
    response = _generate(client, 9999)
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"
    assert mock_deepseek["calls"] == []


def test_generate_success_not_persisted(client, story, configure_key, mock_deepseek):
    mock_deepseek["response"] = make_response()
    response = _generate(client, story["id"])
    assert response.status_code == 200
    data = response.json()
    assert data["story_id"] == story["id"]
    options = data["options"]
    assert len(options) == 3
    assert options[0]["style"] == "悬念反差"
    assert options[0]["feature"]
    assert options[0]["title"] == "测试标题"
    assert options[0]["content"] == "这是测试正文。#条漫"
    # 有且只有一个推荐方案，并附带推荐理由
    assert sum(item["recommended"] for item in options) == 1
    assert options[0]["recommended"] is True
    assert options[0]["recommend_reason"]

    # 生成结果不自动入库
    assert client.get("/api/posts").json() == []

    # 校验请求内容：使用 SQLite 中的 Key、故事内容与固定 JSON 契约
    api_key, messages = mock_deepseek["calls"][0]
    assert api_key == "sk-test-abcd"
    assert story["content"] in messages[1]["content"]
    assert "json" in messages[0]["content"]
    assert "重要输出要求" in messages[0]["content"]
    # 新契约要求一次给出多个方案，而不是单个 title/content
    assert "options" in messages[0]["content"]
    assert "3 个" in messages[0]["content"]


def test_prompt_placeholders_are_replaced(client, story, configure_key, mock_deepseek):
    client.put(
        "/api/settings/prompt",
        json={"content": "围绕 {story_name} 写小红书，素材：{story_content}"},
    )
    mock_deepseek["response"] = make_response()
    assert _generate(client, story["id"]).status_code == 200

    _, messages = mock_deepseek["calls"][0]
    system_prompt = messages[0]["content"]
    assert "测试故事" in system_prompt
    assert story["content"] in system_prompt
    assert "{story_content}" not in system_prompt


def test_story_art_style_takes_priority(
    client, configure_key, mock_deepseek
):
    """生成文案优先使用故事自己的画风，而不是全局当前画风。"""
    client.put(
        "/api/settings/art-styles",
        json={
            "styles": [
                {"id": "style-a", "name": "唯美彩铅", "content": "韩式唯美彩铅"},
                {"id": "style-b", "name": "日系赛璐璐", "content": "日系赛璐璐平涂"},
            ],
            "active_id": "style-a",
        },
    )
    client.put(
        "/api/settings/prompt",
        json={"content": "画风：{art_style_name} / {art_style}"},
    )
    story = client.post(
        "/api/stories",
        json={"name": "画风故事", "content": "内容", "art_style_id": "style-b"},
    ).json()

    mock_deepseek["response"] = make_response()
    assert _generate(client, story["id"]).status_code == 200

    _, messages = mock_deepseek["calls"][0]
    system_prompt = messages[0]["content"]
    assert "日系赛璐璐" in system_prompt
    assert "日系赛璐璐平涂" in system_prompt
    assert "唯美彩铅" not in system_prompt


def test_generate_falls_back_to_active_style(
    client, story, configure_key, mock_deepseek
):
    """故事未选画风时回退到全局当前画风。"""
    client.put(
        "/api/settings/art-styles",
        json={
            "styles": [
                {"id": "style-a", "name": "唯美彩铅", "content": "韩式唯美彩铅"}
            ],
            "active_id": "style-a",
        },
    )
    client.put(
        "/api/settings/prompt",
        json={"content": "画风：{art_style_name} / {art_style}"},
    )

    mock_deepseek["response"] = make_response()
    assert _generate(client, story["id"]).status_code == 200

    _, messages = mock_deepseek["calls"][0]
    system_prompt = messages[0]["content"]
    assert "唯美彩铅" in system_prompt
    assert "韩式唯美彩铅" in system_prompt


def test_env_key_takes_priority(client, story, configure_key, mock_deepseek, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-9999")
    mock_deepseek["response"] = make_response()
    assert _generate(client, story["id"]).status_code == 200
    assert mock_deepseek["calls"][0][0] == "sk-env-9999"


@pytest.mark.parametrize(
    ("upstream_status", "expected_status", "expected_code"),
    [
        (401, 502, "DEEPSEEK_AUTH_FAILED"),
        (402, 502, "DEEPSEEK_INSUFFICIENT_BALANCE"),
        (400, 502, "DEEPSEEK_UPSTREAM_REJECTED"),
        (429, 429, "DEEPSEEK_RATE_LIMITED"),
        (500, 503, "DEEPSEEK_UNAVAILABLE"),
        (503, 503, "DEEPSEEK_UNAVAILABLE"),
    ],
)
def test_upstream_errors_mapped(
    client,
    story,
    configure_key,
    mock_deepseek,
    upstream_status,
    expected_status,
    expected_code,
):
    mock_deepseek["response"] = httpx.Response(
        upstream_status,
        json={"error": "upstream"},
        request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
    )
    response = _generate(client, story["id"])
    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
    # 鉴权、限流、服务错误不自动重试
    assert len(mock_deepseek["calls"]) == 1


def test_timeout_mapped(client, story, configure_key, monkeypatch):
    from app.services import deepseek

    def fake_post(url, headers, payload, timeout):
        raise httpx.TimeoutException(
            "timeout",
            request=httpx.Request(
                "POST", "https://api.deepseek.com/chat/completions"
            ),
        )

    monkeypatch.setattr(deepseek, "_post", fake_post)
    response = _generate(client, story["id"])
    assert response.status_code == 504
    assert response.json()["code"] == "DEEPSEEK_TIMEOUT"


def test_network_error_mapped(client, story, configure_key, monkeypatch):
    from app.services import deepseek

    def fake_post(url, headers, payload, timeout):
        raise httpx.ConnectError(
            "network down",
            request=httpx.Request(
                "POST", "https://api.deepseek.com/chat/completions"
            ),
        )

    monkeypatch.setattr(deepseek, "_post", fake_post)
    response = _generate(client, story["id"])
    assert response.status_code == 502
    assert response.json()["code"] == "DEEPSEEK_NETWORK_ERROR"


def test_bad_output_retries_once_then_fails(
    client, story, configure_key, mock_deepseek
):
    mock_deepseek["response"] = [
        make_response(raw_content="这不是 JSON"),
        make_response(raw_content="仍然不是 JSON"),
    ]
    response = _generate(client, story["id"])
    assert response.status_code == 502
    assert response.json()["code"] == "DEEPSEEK_BAD_OUTPUT"
    assert len(mock_deepseek["calls"]) == 2


def test_bad_output_then_success(client, story, configure_key, mock_deepseek):
    mock_deepseek["response"] = [
        make_response(raw_content="不是 JSON"),
        make_response(),
    ]
    response = _generate(client, story["id"])
    assert response.status_code == 200
    assert response.json()["options"][0]["title"] == "测试标题"
    assert len(mock_deepseek["calls"]) == 2


def test_markdown_fenced_json_accepted(client, story, configure_key, mock_deepseek):
    payload = {"options": make_copy_options("围栏标题", "围栏正文")}
    fenced = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    mock_deepseek["response"] = make_response(raw_content=fenced)
    response = _generate(client, story["id"])
    assert response.status_code == 200
    assert response.json()["options"][0]["title"] == "围栏标题"


def _raw_options(options: list[dict], **kwargs) -> str:
    return make_response(
        raw_content=json.dumps({"options": options}, ensure_ascii=False), **kwargs
    )


def test_missing_recommendation_falls_back_to_first(
    client, story, configure_key, mock_deepseek
):
    """模型漏标推荐时，保留第一个方案为推荐，不让整次生成失败。"""
    options = make_copy_options()
    for item in options:
        item["recommended"] = False
    mock_deepseek["response"] = _raw_options(options)

    response = _generate(client, story["id"])
    assert response.status_code == 200
    data = response.json()["options"]
    assert [item["recommended"] for item in data] == [True, False, False]


def test_multiple_recommendations_kept_only_first(
    client, story, configure_key, mock_deepseek
):
    """模型标了多个推荐时，只保留第一个，避免前端出现多个「推荐」。"""
    options = make_copy_options()
    options[1]["recommended"] = True
    mock_deepseek["response"] = _raw_options(options)

    response = _generate(client, story["id"])
    assert response.status_code == 200
    data = response.json()["options"]
    assert [item["recommended"] for item in data] == [True, False, False]


def test_too_few_options_is_bad_output(client, story, configure_key, mock_deepseek):
    """只有 1 个方案没有可选性，按格式异常重试后报错。"""
    options = [make_copy_options()[0]]
    mock_deepseek["response"] = [_raw_options(options), _raw_options(options)]

    response = _generate(client, story["id"])
    assert response.status_code == 502
    assert response.json()["code"] == "DEEPSEEK_BAD_OUTPUT"
    assert len(mock_deepseek["calls"]) == 2


def test_truncated_output_retries_and_fails(client, story, configure_key, mock_deepseek):
    mock_deepseek["response"] = [
        make_response(finish_reason="length"),
        make_response(finish_reason="length"),
    ]
    response = _generate(client, story["id"])
    assert response.status_code == 502
    assert response.json()["code"] == "DEEPSEEK_BAD_OUTPUT"
    assert len(mock_deepseek["calls"]) == 2


def test_empty_content_is_bad_output(client, story, configure_key, mock_deepseek):
    mock_deepseek["response"] = [
        make_response(raw_content=""),
        make_response(raw_content=""),
    ]
    response = _generate(client, story["id"])
    assert response.status_code == 502
    assert response.json()["code"] == "DEEPSEEK_BAD_OUTPUT"


def test_missing_fields_is_bad_output(client, story, configure_key, mock_deepseek):
    mock_deepseek["response"] = [
        make_response(raw_content='{"title": "只有标题"}'),
        make_response(raw_content='{"title": "只有标题"}'),
    ]
    response = _generate(client, story["id"])
    assert response.status_code == 502
    assert response.json()["code"] == "DEEPSEEK_BAD_OUTPUT"
