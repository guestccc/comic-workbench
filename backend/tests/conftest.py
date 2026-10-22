"""pytest 公共夹具：临时数据库、临时上传目录、DeepSeek mock。"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_deepseek_env(monkeypatch):
    """默认清空环境变量，避免本机真实 Key 影响测试。"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


@pytest.fixture()
def app_settings(tmp_path):
    return AppSettings(
        db_path=tmp_path / "test.db",
        upload_dir=tmp_path / "uploads",
        frontend_dist=tmp_path / "dist",
    )


@pytest.fixture()
def app(app_settings):
    return create_app(app_settings)


@pytest.fixture()
def client(app):
    # 使用上下文管理器触发 lifespan（建表、创建目录）
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def story(client):
    response = client.post(
        "/api/stories",
        json={"name": "测试故事", "content": "从前有座山，山里有座庙。"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def configure_key(client):
    response = client.put("/api/settings/deepseek", json={"api_key": "sk-test-abcd"})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture()
def mock_deepseek(monkeypatch):
    """拦截 DeepSeek 网络请求。

    用法：mock_deepseek["response"] = httpx.Response(...)，或传入响应列表
    以模拟多次调用；mock_deepseek["calls"] 记录 (api_key, messages)。
    """
    from app.services import deepseek

    state: dict = {"calls": [], "response": None}

    def fake_post(url, headers, payload, timeout):
        # 记录 (api_key, messages)，便于测试断言实际使用的 Key 与提示词
        api_key = headers.get("Authorization", "").removeprefix("Bearer ")
        state["calls"].append((api_key, payload["messages"]))
        response = state["response"]
        if isinstance(response, list):
            return response.pop(0)
        return response

    # 只拦截网络层，状态码映射、超时转换、JSON 解析仍执行真实代码
    monkeypatch.setattr(deepseek, "_post", fake_post)
    return state


@pytest.fixture()
def mock_deepseek_stream(monkeypatch):
    """拦截 DeepSeek 流式请求。

    用法：mock_deepseek_stream["lines"] = [...SSE 文本...]；
    或 mock_deepseek_stream["error"] = 异常实例以模拟上游失败。
    mock_deepseek_stream["calls"] 记录 (api_key, payload)。
    """
    from app.services import deepseek

    state: dict = {"calls": [], "lines": [], "error": None}

    def fake_stream(url, headers, payload, timeout):
        api_key = headers.get("Authorization", "").removeprefix("Bearer ")
        state["calls"].append((api_key, payload))
        if state["error"] is not None:
            raise state["error"]
        yield from state["lines"]

    monkeypatch.setattr(deepseek, "_stream_post", fake_stream)
    return state


def make_response(
    *,
    title: str = "测试标题",
    content: str = "这是测试正文。#条漫",
    status_code: int = 200,
    raw_content: str | None = None,
    finish_reason: str = "stop",
) -> httpx.Response:
    """构造 DeepSeek 兼容响应；raw_content 用于模拟非法输出。"""
    if raw_content is None:
        raw_content = json.dumps(
            {"title": title, "content": content}, ensure_ascii=False
        )
    payload = {
        "choices": [
            {"message": {"content": raw_content}, "finish_reason": finish_reason}
        ]
    }
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
    )
