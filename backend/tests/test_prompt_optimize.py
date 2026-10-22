"""AI 优化启动提示词的流式接口测试。"""

from __future__ import annotations

import json

import httpx
import pytest

from app.errors import AppError


def _payload(**overrides) -> dict:
    data = {
        "current_prompt": "你是分镜师，请根据故事生成条漫分镜。",
        "messages": [{"role": "user", "content": "让提示词更结构化"}],
    }
    data.update(overrides)
    return data


def _chunk(content: str | None, finish_reason: str | None = None) -> str:
    """构造一行 DeepSeek 流式响应。"""
    return "data: " + json.dumps(
        {
            "choices": [
                {
                    "delta": {"content": content} if content is not None else {},
                    "finish_reason": finish_reason,
                }
            ]
        },
        ensure_ascii=False,
    )


def _events(text: str) -> list[dict]:
    """把 SSE 响应体解析成事件列表。"""
    events: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block.startswith("data:"):
            continue
        events.append(json.loads(block[len("data:") :].strip()))
    return events


def test_missing_key_returns_409(client):
    response = client.post("/api/settings/prompt/optimize", json=_payload())
    assert response.status_code == 409
    assert response.json()["code"] == "DEEPSEEK_KEY_MISSING"


def test_stream_success(client, configure_key, mock_deepseek_stream):
    mock_deepseek_stream["lines"] = [
        _chunk("新版"),
        "",
        _chunk("提示词。"),
        "data: [DONE]",
    ]

    response = client.post("/api/settings/prompt/optimize", json=_payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert [event["type"] for event in events] == ["delta", "delta", "done"]
    assert events[0]["content"] == "新版"
    assert events[1]["content"] == "提示词。"

    api_key, payload = mock_deepseek_stream["calls"][0]
    assert api_key == "sk-test-abcd"
    assert payload["stream"] is True
    assert payload["max_tokens"] == 8000
    assert payload["messages"][0]["role"] == "system"
    assert "你是分镜师，请根据故事生成条漫分镜。" in payload["messages"][0]["content"]
    assert payload["messages"][-1] == {
        "role": "user",
        "content": "让提示词更结构化",
    }


def test_history_is_forwarded(client, configure_key, mock_deepseek_stream):
    mock_deepseek_stream["lines"] = [_chunk("好的"), "data: [DONE]"]
    messages = [
        {"role": "user", "content": "第一轮诉求"},
        {"role": "assistant", "content": "第一版提示词"},
        {"role": "user", "content": "第二轮诉求"},
    ]

    response = client.post(
        "/api/settings/prompt/optimize",
        json=_payload(messages=messages),
    )

    assert response.status_code == 200
    forwarded = mock_deepseek_stream["calls"][0][1]["messages"]
    assert forwarded[1:] == messages


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            AppError(502, "Key 无效", "DEEPSEEK_AUTH_FAILED"),
            "DEEPSEEK_AUTH_FAILED",
        ),
        (httpx.TimeoutException("timeout"), "DEEPSEEK_TIMEOUT"),
        (httpx.ConnectError("network"), "DEEPSEEK_NETWORK_ERROR"),
    ],
)
def test_upstream_errors_become_sse_events(
    client, configure_key, mock_deepseek_stream, error, expected_code
):
    # 流开始后才发生错误，HTTP 状态仍为 200，错误通过 SSE 事件传递
    mock_deepseek_stream["error"] = error

    response = client.post("/api/settings/prompt/optimize", json=_payload())

    assert response.status_code == 200
    events = _events(response.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == expected_code


def test_empty_upstream_output(client, configure_key, mock_deepseek_stream):
    mock_deepseek_stream["lines"] = ["data: [DONE]"]

    response = client.post("/api/settings/prompt/optimize", json=_payload())

    events = _events(response.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "DEEPSEEK_BAD_OUTPUT"


def test_truncated_output(client, configure_key, mock_deepseek_stream):
    mock_deepseek_stream["lines"] = [
        _chunk("写到一半", finish_reason="length"),
        "data: [DONE]",
    ]

    response = client.post("/api/settings/prompt/optimize", json=_payload())

    events = _events(response.text)
    assert events[0] == {"type": "delta", "content": "写到一半"}
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "DEEPSEEK_OUTPUT_TRUNCATED"


@pytest.mark.parametrize(
    "payload",
    [
        # 没有任何对话
        _payload(messages=[]),
        # 最后一条不是用户消息
        _payload(messages=[{"role": "assistant", "content": "好的"}]),
        # 提示词为空
        _payload(current_prompt="   "),
        # 超过 12 条
        _payload(
            messages=[
                {"role": "user", "content": f"第 {index} 轮"}
                for index in range(13)
            ]
        ),
        # 总字符数超过 30000
        _payload(
            current_prompt="x" * 10000,
            messages=[
                {"role": "user", "content": "y" * 10000},
                {"role": "assistant", "content": "z" * 10000},
                {"role": "user", "content": "继续"},
            ],
        ),
    ],
)
def test_validation_errors(client, configure_key, payload):
    response = client.post("/api/settings/prompt/optimize", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
