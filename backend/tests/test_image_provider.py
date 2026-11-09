"""生图上游连接重试：只重试握手失败，不重试已发出的请求。"""

from __future__ import annotations

import httpx
import pytest

from app.services import image_provider


def test_connect_error_is_retried(monkeypatch):
    calls = 0

    def request() -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(200)

    monkeypatch.setattr(image_provider.time, "sleep", lambda _: None)
    response = image_provider._request_with_connect_retry(request)
    assert response.status_code == 200
    assert calls == 3


def test_connect_error_gives_up_after_limit(monkeypatch):
    calls = 0

    def request() -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection reset")

    monkeypatch.setattr(image_provider.time, "sleep", lambda _: None)
    with pytest.raises(httpx.ConnectError):
        image_provider._request_with_connect_retry(request)
    assert calls == image_provider._CONNECT_ATTEMPTS


def test_read_timeout_is_not_retried(monkeypatch):
    calls = 0

    def request() -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("read timed out")

    monkeypatch.setattr(image_provider.time, "sleep", lambda _: None)
    with pytest.raises(httpx.ReadTimeout):
        image_provider._request_with_connect_retry(request)
    assert calls == 1
