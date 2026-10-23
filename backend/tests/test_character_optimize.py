"""AI 优化角色设定卡外形描述的流式接口测试。"""

from __future__ import annotations

import httpx

from tests.test_breakdowns import _prepare
from tests.test_prompt_optimize import _chunk, _events


def _payload(**overrides) -> dict:
    data = {
        "character_name": "小八老师",
        "character_role": "女主",
        "current_appearance": "鹅蛋脸、细框眼镜、深棕低马尾、米白针织开衫。",
        "messages": [{"role": "user", "content": "把低马尾改成锁骨短发"}],
    }
    data.update(overrides)
    return data


def test_missing_key_returns_409(client):
    story, _ = _prepare(client)
    response = client.post(
        f"/api/stories/{story['id']}/breakdown/characters/optimize",
        json=_payload(),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DEEPSEEK_KEY_MISSING"


def test_requires_existing_breakdown(client, story):
    """角色优化属于拆解结果的一部分；没有拆解时不能调用。"""
    response = client.post(
        f"/api/stories/{story['id']}/breakdown/characters/optimize",
        json=_payload(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "BREAKDOWN_NOT_FOUND"


def test_story_not_found(client):
    response = client.post(
        "/api/stories/9999/breakdown/characters/optimize",
        json=_payload(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"


def test_stream_success(client, configure_key, mock_deepseek_stream):
    story, _ = _prepare(client)
    mock_deepseek_stream["lines"] = [
        _chunk("```"),
        _chunk("锁骨短发、鹅蛋脸、细框眼镜、米白针织开衫。"),
        _chunk("```"),
        "data: [DONE]",
    ]

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/characters/optimize",
        json=_payload(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert [event["type"] for event in events] == ["delta", "delta", "delta", "done"]

    api_key, payload = mock_deepseek_stream["calls"][0]
    assert api_key == "sk-test-abcd"
    assert payload["stream"] is True
    assert payload["max_tokens"] == 2000
    system_prompt = payload["messages"][0]["content"]
    # 使用角色优化专用系统提示词，并携带姓名、身份与当前外形
    assert "角色「小八老师」（女主）" in system_prompt
    assert "鹅蛋脸、细框眼镜、深棕低马尾、米白针织开衫。" in system_prompt
    assert "Markdown 代码块" in system_prompt
    assert payload["messages"][-1] == {
        "role": "user",
        "content": "把低马尾改成锁骨短发",
    }


def test_upstream_timeout_becomes_sse_event(
    client, configure_key, mock_deepseek_stream
):
    story, _ = _prepare(client)
    mock_deepseek_stream["error"] = httpx.TimeoutException("timeout")

    response = client.post(
        f"/api/stories/{story['id']}/breakdown/characters/optimize",
        json=_payload(),
    )

    assert response.status_code == 200
    events = _events(response.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "DEEPSEEK_TIMEOUT"


def test_validation(client, configure_key):
    story, _ = _prepare(client)
    url = f"/api/stories/{story['id']}/breakdown/characters/optimize"

    # 最后一条必须是用户消息
    response = client.post(
        url,
        json=_payload(messages=[{"role": "assistant", "content": "嗯"}]),
    )
    assert response.status_code == 422

    # 空外形描述被拒绝
    response = client.post(url, json=_payload(current_appearance="   "))
    assert response.status_code == 422
