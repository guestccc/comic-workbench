"""画风列表接口测试：全量保存、校验与生成时替换画风变量。"""

from __future__ import annotations

import pytest

from tests.conftest import make_response

STYLES = [
    {"id": "style-1", "name": "日系赛璐璐", "content": "日系赛璐璐风格，线条干净，平涂上色"},
    {"id": "style-2", "name": "厚涂写实", "content": "厚涂写实风格，笔触明显，光影细腻"},
]


def _put_styles(client, styles, active_id=None):
    return client.put(
        "/api/settings/art-styles",
        json={"styles": styles, "active_id": active_id},
    )


def test_default_art_styles_empty(client):
    data = client.get("/api/settings").json()
    assert data["art_styles"] == []
    assert data["active_art_style"] is None


def test_save_and_read_art_styles(client):
    response = _put_styles(client, STYLES, "style-2")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["art_styles"] == STYLES
    assert data["active_art_style"] == "style-2"

    # 重新读取仍能拿到保存值
    persisted = client.get("/api/settings").json()
    assert persisted["art_styles"] == STYLES
    assert persisted["active_art_style"] == "style-2"


def test_full_replace_and_clear(client):
    assert _put_styles(client, STYLES, "style-1").status_code == 200

    # 全量覆盖：只保留一条，并切换选用
    replaced = _put_styles(client, [STYLES[1]], "style-2").json()
    assert replaced["art_styles"] == [STYLES[1]]
    assert replaced["active_art_style"] == "style-2"

    # 清空列表后选用项一并清空
    cleared = _put_styles(client, [], None).json()
    assert cleared["art_styles"] == []
    assert cleared["active_art_style"] is None


def test_cancel_selection_keeps_styles(client):
    _put_styles(client, STYLES, "style-1")
    data = _put_styles(client, STYLES, None).json()
    assert len(data["art_styles"]) == 2
    assert data["active_art_style"] is None


@pytest.mark.parametrize(
    "payload",
    [
        # 名称重复
        {"styles": [STYLES[0], {**STYLES[1], "name": STYLES[0]["name"]}]},
        # id 重复
        {"styles": [STYLES[0], {**STYLES[1], "id": STYLES[0]["id"]}]},
        # 选用的画风不在列表中
        {"styles": STYLES, "active_id": "style-missing"},
        # 空名称
        {"styles": [{**STYLES[0], "name": "   "}]},
        # 空内容
        {"styles": [{**STYLES[0], "content": "   "}]},
        # 超过数量上限
        {
            "styles": [
                {"id": f"style-{index}", "name": f"画风{index}", "content": "描述"}
                for index in range(21)
            ]
        },
        # 名称超长
        {"styles": [{**STYLES[0], "name": "画" * 51}]},
        # 内容超长
        {"styles": [{**STYLES[0], "content": "画" * 2001}]},
    ],
)
def test_validation(client, payload):
    response = client.put("/api/settings/art-styles", json=payload)
    assert response.status_code == 422


def test_generate_replaces_art_style(
    client, story, configure_key, mock_deepseek
):
    client.put(
        "/api/settings/prompt",
        json={"content": "围绕 {story_name} 写小红书。画风要求：{art_style}"},
    )
    _put_styles(client, STYLES, "style-1")
    mock_deepseek["response"] = make_response()

    response = client.post("/api/posts/generate", json={"story_id": story["id"]})
    assert response.status_code == 200, response.text

    _, messages = mock_deepseek["calls"][0]
    system_prompt = messages[0]["content"]
    assert STYLES[0]["content"] in system_prompt
    assert "{art_style}" not in system_prompt
    # 未选用的画风不应混入
    assert STYLES[1]["content"] not in system_prompt


def test_generate_replaces_art_style_name(
    client, story, configure_key, mock_deepseek
):
    """{art_style_name} 替换为画风名称，{art_style} 替换为描述，两者互不干扰。"""
    client.put(
        "/api/settings/prompt",
        json={"content": "画风名称：{art_style_name}；画风要求：{art_style}"},
    )
    _put_styles(client, STYLES, "style-2")
    mock_deepseek["response"] = make_response()

    response = client.post("/api/posts/generate", json={"story_id": story["id"]})
    assert response.status_code == 200, response.text

    _, messages = mock_deepseek["calls"][0]
    system_prompt = messages[0]["content"]
    assert STYLES[1]["name"] in system_prompt
    assert STYLES[1]["content"] in system_prompt
    assert "{art_style_name}" not in system_prompt
    assert "{art_style}" not in system_prompt


def test_generate_without_active_style_keeps_placeholder(
    client, story, configure_key, mock_deepseek
):
    client.put(
        "/api/settings/prompt",
        json={"content": "画风要求：{art_style}；名称：{art_style_name}"},
    )
    _put_styles(client, STYLES, None)
    mock_deepseek["response"] = make_response()

    assert (
        client.post("/api/posts/generate", json={"story_id": story["id"]}).status_code
        == 200
    )
    _, messages = mock_deepseek["calls"][0]
    system_prompt = messages[0]["content"]
    assert "{art_style}" in system_prompt
    assert "{art_style_name}" in system_prompt
    assert STYLES[0]["content"] not in system_prompt
    assert STYLES[0]["name"] not in system_prompt
