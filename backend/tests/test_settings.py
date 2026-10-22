"""设置接口测试：启动提示词、DeepSeek Key。"""

from __future__ import annotations


def test_default_settings(client):
    data = client.get("/api/settings").json()
    assert data["prompt"]
    assert data["is_default"] is True
    assert data["prompt_updated_at"] is None
    assert data["deepseek"] == {
        "configured": False,
        "source": "none",
        "masked_key": None,
        "db_configured": False,
    }


def test_update_and_reset_prompt(client):
    response = client.put(
        "/api/settings/prompt", json={"content": "自定义提示词 {story_name}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["prompt"] == "自定义提示词 {story_name}"
    assert data["is_default"] is False
    assert data["prompt_updated_at"] is not None
    assert data["prompt_updated_at"].endswith("Z")

    # 重新读取仍能拿到保存值
    assert client.get("/api/settings").json()["prompt"] == "自定义提示词 {story_name}"

    reset = client.post("/api/settings/prompt/reset").json()
    assert reset["is_default"] is True
    assert reset["prompt_updated_at"] is None


def test_prompt_validation(client):
    assert (
        client.put("/api/settings/prompt", json={"content": "   "}).status_code == 422
    )
    assert (
        client.put("/api/settings/prompt", json={"content": "x" * 10001}).status_code
        == 422
    )


def test_deepseek_key_is_masked(client):
    response = client.put(
        "/api/settings/deepseek", json={"api_key": "sk-secret-1234"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["deepseek"]["configured"] is True
    assert data["deepseek"]["source"] == "db"
    assert data["deepseek"]["masked_key"] == "****1234"
    assert data["deepseek"]["db_configured"] is True
    # 响应中绝不能出现完整 Key
    assert "sk-secret-1234" not in response.text

    cleared = client.delete("/api/settings/deepseek").json()
    assert cleared["deepseek"]["configured"] is False


def test_blank_key_rejected(client):
    response = client.put("/api/settings/deepseek", json={"api_key": "   "})
    assert response.status_code == 422


def test_env_key_takes_priority(client, monkeypatch):
    client.put("/api/settings/deepseek", json={"api_key": "sk-db-0000"})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-9999")

    data = client.get("/api/settings").json()
    assert data["deepseek"]["source"] == "env"
    assert data["deepseek"]["masked_key"] == "****9999"
    assert data["deepseek"]["db_configured"] is True
