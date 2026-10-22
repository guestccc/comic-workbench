"""AI 优化画风描述的流式接口测试。"""

from __future__ import annotations

import httpx
import pytest

from app.errors import AppError
from tests.test_prompt_optimize import _chunk, _events


def _payload(**overrides) -> dict:
    data = {
        "current_style": "日系赛璐璐风格，线条干净，平涂上色。",
        "messages": [{"role": "user", "content": "补充光影和氛围"}],
    }
    data.update(overrides)
    return data


def test_missing_key_returns_409(client):
    response = client.post("/api/settings/art-styles/optimize", json=_payload())
    assert response.status_code == 409
    assert response.json()["code"] == "DEEPSEEK_KEY_MISSING"


def test_stream_success(client, configure_key, mock_deepseek_stream):
    mock_deepseek_stream["lines"] = [
        _chunk("日系赛璐璐风格，"),
        _chunk("线条干净，柔和光影。"),
        "data: [DONE]",
    ]

    response = client.post("/api/settings/art-styles/optimize", json=_payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert [event["type"] for event in events] == ["delta", "delta", "done"]
    assert "线条干净，柔和光影。" in events[1]["content"]

    api_key, payload = mock_deepseek_stream["calls"][0]
    assert api_key == "sk-test-abcd"
    assert payload["stream"] is True
    assert payload["max_tokens"] == 2000
    system_prompt = payload["messages"][0]["content"]
    # 使用画风专用的系统提示词，并携带当前描述
    assert "画风描述" in system_prompt
    assert "日系赛璐璐风格，线条干净，平涂上色。" in system_prompt
    assert payload["messages"][-1] == {
        "role": "user",
        "content": "补充光影和氛围",
    }


def test_upstream_error_becomes_sse_event(
    client, configure_key, mock_deepseek_stream
):
    mock_deepseek_stream["error"] = httpx.TimeoutException("timeout")

    response = client.post("/api/settings/art-styles/optimize", json=_payload())

    assert response.status_code == 200
    events = _events(response.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "DEEPSEEK_TIMEOUT"


def test_auth_error_code_is_preserved(
    client, configure_key, mock_deepseek_stream
):
    mock_deepseek_stream["error"] = AppError(
        502, "Key 无效", "DEEPSEEK_AUTH_FAILED"
    )

    events = _events(
        client.post("/api/settings/art-styles/optimize", json=_payload()).text
    )
    assert events[-1]["code"] == "DEEPSEEK_AUTH_FAILED"


@pytest.mark.parametrize(
    "payload",
    [
        # 没有任何对话
        _payload(messages=[]),
        # 最后一条不是用户消息
        _payload(messages=[{"role": "assistant", "content": "好的"}]),
        # 画风描述为空
        _payload(current_style="   "),
        # 画风描述超长（上限 2000）
        _payload(current_style="画" * 2001),
    ],
)
def test_validation_errors(client, configure_key, payload):
    response = client.post("/api/settings/art-styles/optimize", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
