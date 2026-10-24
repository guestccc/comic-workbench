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


def test_image_prefix_prompt_is_global_and_editable(client):
    # 默认带群像合照与垫图规则，画风变量留给复制时替换
    default = client.get("/api/settings").json()["image_prefix_prompt"]
    assert "群像合照规则" in default
    assert "垫图/角色参考图强制规则" in default
    assert "{art_style_name}" in default

    saved = client.put(
        "/api/settings/image-prefix-prompt", json={"content": "自定义前置规则"}
    )
    assert saved.status_code == 200
    assert saved.json()["image_prefix_prompt"] == "自定义前置规则"
    # 全局设置：重新读取仍然生效（与具体故事无关）
    assert (
        client.get("/api/settings").json()["image_prefix_prompt"] == "自定义前置规则"
    )

    # 允许清空：空值表示复制时不拼任何前置内容
    cleared = client.put("/api/settings/image-prefix-prompt", json={"content": "  "})
    assert cleared.status_code == 200
    assert cleared.json()["image_prefix_prompt"] == ""

    assert (
        client.put(
            "/api/settings/image-prefix-prompt", json={"content": "x" * 8001}
        ).status_code
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
