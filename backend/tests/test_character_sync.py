"""角色卡同步接口测试：更新角色卡并联动重写分镜人物回顾（DeepSeek 全部 mock）。"""

from __future__ import annotations

import json

from tests.conftest import make_response
from tests.test_breakdowns import _prepare, _put_page


def _sync(client, story_id: int, characters: list[dict]):
    return client.post(
        f"/api/stories/{story_id}/breakdown/characters/sync",
        json={"characters": characters},
    )


def _review_response(reviews: dict[int, str], **kwargs):
    payload = {
        "reviews": [
            {"page_number": page, "character_review": review}
            for page, review in reviews.items()
        ]
    }
    return make_response(
        raw_content=json.dumps(payload, ensure_ascii=False), **kwargs
    )


def _prepare_with_pages(client):
    """拆解头部 + 三页分镜：第 1、2 页登场同步角色，第 3 页不受影响。"""
    story, _ = _prepare(client)
    assert _put_page(client, story["id"], 1).status_code == 200
    assert (
        _put_page(
            client,
            story["id"],
            2,
            characters=["朋友"],
            character_review="朋友：利落短发、西装外套。",
        ).status_code
        == 200
    )
    assert (
        _put_page(
            client,
            story["id"],
            3,
            characters=["路人甲"],
            character_review="路人甲：背影。",
        ).status_code
        == 200
    )
    return story


SYNC_PAYLOAD = [
    {"name": "我", "appearance": "黑色短发，深灰连帽卫衣，黑色双肩包，偏瘦含胸。"},
    {"name": "朋友", "appearance": "利落短发，深蓝休闲西装外套，金属表。"},
]


def test_sync_story_not_found(client):
    response = _sync(client, 9999, SYNC_PAYLOAD)
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"


def test_sync_requires_existing_breakdown(client, story):
    response = _sync(client, story["id"], SYNC_PAYLOAD)
    assert response.status_code == 404
    assert response.json()["code"] == "BREAKDOWN_NOT_FOUND"


def test_sync_updates_cards_and_reviews(client, configure_key, mock_deepseek):
    story = _prepare_with_pages(client)
    mock_deepseek["response"] = _review_response(
        {
            1: "{{我}}：黑色短发、深灰连帽卫衣、黑色双肩包，偏瘦含胸。",
            2: "{{朋友}}：利落短发、深蓝休闲西装外套、金属表。",
        }
    )

    response = _sync(client, story["id"], SYNC_PAYLOAD)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["updated_names"] == ["我"]
    assert data["created_names"] == ["朋友"]
    assert data["review_updated_pages"] == [1, 2]
    assert data["review_warning"] is None

    breakdown = client.get(f"/api/stories/{story['id']}/breakdown").json()
    cards = {card["name"]: card for card in breakdown["characters"]}
    # 已有角色整体覆盖外形并保留身份；新角色追加
    assert cards["我"]["appearance"] == "黑色短发，深灰连帽卫衣，黑色双肩包，偏瘦含胸。"
    assert cards["我"]["role"] == "男主"
    assert cards["朋友"]["appearance"] == "利落短发，深蓝休闲西装外套，金属表。"
    # 未同步的角色保持原样
    assert cards["小八老师"]["appearance"] == "鹅蛋脸，衬衫。"

    pages = {page["page_number"]: page for page in breakdown["pages"]}
    assert pages[1]["character_review"].startswith("{{我}}：黑色短发")
    assert pages[2]["character_review"].startswith("{{朋友}}：利落短发")
    # 不登场同步角色的页面不受影响
    assert pages[3]["character_review"] == "路人甲：背影。"

    # 校验上游请求：新外形与受影响页面的旧回顾都要发给模型
    api_key, messages = mock_deepseek["calls"][0]
    assert api_key == "sk-test-abcd"
    assert "人物回顾" in messages[0]["content"]
    user_prompt = messages[1]["content"]
    assert "{{我}}：黑色短发，深灰连帽卫衣" in user_prompt
    assert "第 3 页" not in user_prompt


def test_sync_without_key_updates_cards_only(client, mock_deepseek):
    """未配置 Key：角色卡照常更新，人物回顾保持原样并给出提示。"""
    story = _prepare_with_pages(client)

    response = _sync(client, story["id"], SYNC_PAYLOAD)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["updated_names"] == ["我"]
    assert data["review_updated_pages"] == []
    assert "DeepSeek API Key" in data["review_warning"]
    assert mock_deepseek["calls"] == []

    breakdown = client.get(f"/api/stories/{story['id']}/breakdown").json()
    cards = {card["name"]: card for card in breakdown["characters"]}
    assert cards["我"]["appearance"] == "黑色短发，深灰连帽卫衣，黑色双肩包，偏瘦含胸。"
    pages = {page["page_number"]: page for page in breakdown["pages"]}
    assert pages[1]["character_review"] == "我：短发、休闲装；小八老师：鹅蛋脸、衬衫。"


def test_sync_ai_failure_leaves_nothing_changed(
    client, configure_key, mock_deepseek
):
    """AI 调用失败时整体不落库，避免角色卡与人物回顾不一致。"""
    story = _prepare_with_pages(client)
    mock_deepseek["response"] = [
        make_response(raw_content="这不是 JSON"),
        make_response(raw_content="仍然不是 JSON"),
    ]

    response = _sync(client, story["id"], SYNC_PAYLOAD)

    assert response.status_code == 502
    assert response.json()["code"] == "DEEPSEEK_BAD_OUTPUT"
    assert len(mock_deepseek["calls"]) == 2

    breakdown = client.get(f"/api/stories/{story['id']}/breakdown").json()
    cards = {card["name"]: card for card in breakdown["characters"]}
    assert cards["我"]["appearance"] == "短发，休闲装。"
    assert "朋友" not in cards


def test_sync_rejects_wrong_page_numbers(client, configure_key, mock_deepseek):
    """模型漏页或编造页码时拒绝写入，防止脏数据进入分镜。"""
    story = _prepare_with_pages(client)
    mock_deepseek["response"] = [
        _review_response({1: "{{我}}：黑色短发。"}),
        _review_response({1: "{{我}}：黑色短发。"}),
    ]

    response = _sync(client, story["id"], SYNC_PAYLOAD)

    assert response.status_code == 502
    assert response.json()["code"] == "DEEPSEEK_BAD_OUTPUT"
    breakdown = client.get(f"/api/stories/{story['id']}/breakdown").json()
    cards = {card["name"]: card for card in breakdown["characters"]}
    assert cards["我"]["appearance"] == "短发，休闲装。"


def test_sync_no_affected_pages_skips_ai(client, configure_key, mock_deepseek):
    """同步的角色没有登上任何分镜页时，不重写人物回顾。"""
    story, _ = _prepare(client)

    response = _sync(
        client, story["id"], [{"name": "我", "appearance": "新外形。"}]
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["review_updated_pages"] == []
    assert "没有分镜页" in data["review_warning"]
    assert mock_deepseek["calls"] == []


def test_sync_validation(client):
    story, _ = _prepare(client)
    url = f"/api/stories/{story['id']}/breakdown/characters/sync"

    # 空列表被拒绝
    assert client.post(url, json={"characters": []}).status_code == 422
    # 空外形被拒绝
    response = client.post(
        url, json={"characters": [{"name": "我", "appearance": "  "}]}
    )
    assert response.status_code == 422
