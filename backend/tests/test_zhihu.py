"""知乎推广信息：别名校验、生成与文案同步测试。"""

from __future__ import annotations

import json

from tests.conftest import make_response
from tests.test_post_configs import _prepare_chapters

TITLE = "重生后我嫁给了渣男"
ARTICLE_ID = "2096656473648525790"


def _patch_zhihu(client, story_id, **payload):
    return client.patch(f"/api/stories/{story_id}/zhihu", json=payload)


def test_patch_zhihu_round_trip(client, story):
    response = _patch_zhihu(
        client,
        story["id"],
        zhihu_article_id=ARTICLE_ID,
        zhihu_alias="橘子汽水很甜",
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["zhihu_title"] == story["name"] == "测试故事"
    assert data["zhihu_article_id"] == ARTICLE_ID
    assert data["zhihu_alias"] == "橘子汽水很甜"

    got = client.get(f"/api/stories/{story['id']}").json()
    assert got["zhihu_alias"] == "橘子汽水很甜"
    listed = client.get("/api/stories").json()
    assert next(item for item in listed if item["id"] == story["id"])[
        "zhihu_title"
    ] == "测试故事"


def test_zhihu_alias_validation(client):
    # 故事名为空时不能填写别名（原名标题即故事名）
    unnamed = client.post(
        "/api/stories",
        json={"name": "", "content": "还没有故事名的故事。"},
    ).json()
    response = _patch_zhihu(
        client, unnamed["id"], zhihu_alias="橘子汽水很甜"
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ZHIHU_TITLE_REQUIRED"

    story = client.post(
        "/api/stories",
        json={"name": TITLE, "content": "故事内容。"},
    ).json()
    story_id = story["id"]

    # 不能复用故事名中的连续两个字
    response = _patch_zhihu(
        client,
        story_id,
        zhihu_alias="重生之后归家",
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ALIAS_REUSES_TITLE_TEXT"

    # 只允许 6–8 个汉字
    response = _patch_zhihu(
        client,
        story_id,
        zhihu_alias="abc",
    )
    assert response.status_code == 422

    response = _patch_zhihu(
        client,
        story_id,
        zhihu_alias="一二三四五六七八九",
    )
    assert response.status_code == 422

    # 原文 ID 只接受数字
    response = _patch_zhihu(
        client,
        story_id,
        zhihu_article_id="p123",
        zhihu_alias="橘子汽水很甜",
    )
    assert response.status_code == 422


def test_multiple_aliases_and_active_selection(client):
    story = client.post(
        "/api/stories",
        json={"name": TITLE, "content": "故事内容。"},
    ).json()
    story_id = story["id"]
    response = _patch_zhihu(
        client,
        story_id,
        zhihu_article_id=ARTICLE_ID,
        zhihu_aliases=["橘子汽水很甜", "晚风邮局等你"],
        zhihu_alias="",
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["zhihu_aliases"] == ["橘子汽水很甜", "晚风邮局等你"]
    assert data["zhihu_alias"] == ""

    # 最终使用别名可以稍后再标注
    response = _patch_zhihu(
        client,
        story_id,
        zhihu_article_id=ARTICLE_ID,
        zhihu_alias="晚风邮局等你",
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["zhihu_alias"] == "晚风邮局等你"
    assert data["zhihu_aliases"] == ["橘子汽水很甜", "晚风邮局等你"]

    # 最终别名如果不在候选列表里，会自动补进列表
    response = _patch_zhihu(
        client,
        story_id,
        zhihu_article_id=ARTICLE_ID,
        zhihu_aliases=["橘子汽水很甜"],
        zhihu_alias="晚风邮局等你",
    )
    assert response.status_code == 200
    assert response.json()["zhihu_aliases"] == ["橘子汽水很甜", "晚风邮局等你"]

    # 任一候选别名都不能复用标题文案
    response = _patch_zhihu(
        client,
        story_id,
        zhihu_aliases=["橘子汽水很甜", "重生之后归家"],
        zhihu_alias="",
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ALIAS_REUSES_TITLE_TEXT"


def test_story_rename_respects_aliases(client):
    """故事名即知乎原名标题，改名后别名仍不能复用新标题的连续两字。"""
    story = client.post(
        "/api/stories",
        json={"name": TITLE, "content": "故事内容。"},
    ).json()
    assert (
        _patch_zhihu(
            client,
            story["id"],
            zhihu_alias="橘子汽水很甜",
        ).status_code
        == 200
    )

    payload = {
        "name": "橘子花开的时候",
        "content": "故事内容。",
        "cover_filename": None,
        "art_style_id": None,
    }
    response = client.put(f"/api/stories/{story['id']}", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "ALIAS_REUSES_TITLE_TEXT"

    # 已有别名时不能把故事名清空
    payload["name"] = ""
    response = client.put(f"/api/stories/{story['id']}", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "ZHIHU_TITLE_REQUIRED"

    # 不冲突的名字可以正常保存，响应中的知乎标题随之更新
    payload["name"] = "换一个名字"
    response = client.put(f"/api/stories/{story['id']}", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["zhihu_title"] == "换一个名字"


def test_zhihu_alias_must_be_unique_locally(client, story):
    other = client.post(
        "/api/stories",
        json={"name": "另一篇", "content": "另一个故事。"},
    ).json()

    assert (
        _patch_zhihu(
            client,
            story["id"],
            zhihu_alias="橘子汽水很甜",
        ).status_code
        == 200
    )
    response = _patch_zhihu(
        client,
        other["id"],
        zhihu_alias="橘子汽水很甜",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ALIAS_ALREADY_USED"


def test_alias_update_syncs_saved_post_configs(client):
    story = _prepare_chapters(client)
    story_id = story["id"]

    assert (
        _patch_zhihu(
            client,
            story_id,
            zhihu_article_id=ARTICLE_ID,
            zhihu_alias="橘子汽水很甜",
        ).status_code
        == 200
    )
    saved = client.put(
        f"/api/stories/{story_id}/post-config?chapter=2",
        json={"title": "第二章", "content": "正文开头 #话题"},
    ).json()
    assert saved["content"] == "【橘子汽水很甜】\n正文开头 #话题"

    # 改别名时同步替换已保存文案的开头
    assert (
        _patch_zhihu(
            client,
            story_id,
            zhihu_article_id=ARTICLE_ID,
            zhihu_alias="晚风邮局等你",
        ).status_code
        == 200
    )
    got = client.get(
        f"/api/stories/{story_id}/post-config?chapter=2"
    ).json()
    assert got["content"] == "【晚风邮局等你】\n正文开头 #话题"

    # 清空别名时移除开头别名
    assert (
        _patch_zhihu(
            client,
            story_id,
            zhihu_article_id=ARTICLE_ID,
            zhihu_alias="",
        ).status_code
        == 200
    )
    got = client.get(
        f"/api/stories/{story_id}/post-config?chapter=2"
    ).json()
    assert got["content"] == "正文开头 #话题"


def test_alias_suggestions_filter_invalid_and_duplicates(
    client, configure_key, mock_deepseek
):
    story = client.post(
        "/api/stories",
        json={"name": TITLE, "content": "故事内容。"},
    ).json()
    mock_deepseek["response"] = make_response(
        raw_content=json.dumps(
            {
                "aliases": [
                    "橘子汽水很甜",
                    "重生之后归家",
                    "abc",
                    "晚风邮局等你",
                    "橘子汽水很甜",
                    "南巷旧梦未醒",
                    "一二三四五六七八九",
                ]
            },
            ensure_ascii=False,
        )
    )

    response = client.post(
        f"/api/stories/{story['id']}/zhihu/alias-suggestions"
    )
    assert response.status_code == 200, response.text
    assert response.json()["aliases"] == [
        "橘子汽水很甜",
        "晚风邮局等你",
        "南巷旧梦未醒",
    ]
    _, messages = mock_deepseek["calls"][0]
    assert TITLE in messages[1]["content"]


def test_alias_suggestions_require_story_name_and_key(
    client, configure_key, mock_deepseek
):
    # 没有故事名（即知乎原名标题）时不调用模型
    story = client.post(
        "/api/stories",
        json={"name": "", "content": "故事内容。"},
    ).json()
    response = client.post(
        f"/api/stories/{story['id']}/zhihu/alias-suggestions"
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ZHIHU_TITLE_REQUIRED"
    assert mock_deepseek["calls"] == []


def test_generate_copy_includes_zhihu_alias(
    client, configure_key, mock_deepseek
):
    story = client.post(
        "/api/stories",
        json={"name": "别名文案", "content": "故事内容。"},
    ).json()
    assert (
        _patch_zhihu(
            client,
            story["id"],
            zhihu_article_id=ARTICLE_ID,
            zhihu_alias="橘子汽水很甜",
        ).status_code
        == 200
    )
    mock_deepseek["response"] = make_response()

    response = client.post(
        "/api/posts/generate", json={"story_id": story["id"]}
    )
    assert response.status_code == 200
    _, messages = mock_deepseek["calls"][0]
    assert "【橘子汽水很甜】" in messages[0]["content"]
    assert "【橘子汽水很甜】" in messages[1]["content"]
