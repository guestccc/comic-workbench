"""每个故事一份的小红书发文配置接口测试。"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import StoryChapterPostConfig, StoryPostConfig
from tests.test_breakdowns import (
    _chapter_payload,
    _mapping_items,
    _patch_breakdown,
    _prepare,
)


def _prepare_chapters(client):
    """准备一个带 2 章规划的拆解结果。"""
    story, _ = _prepare(client)
    story_id = story["id"]
    assert (
        _patch_breakdown(
            client, story_id, mapping=_mapping_items([1, 2, 3, 4])
        ).status_code
        == 200
    )
    assert (
        _patch_breakdown(
            client,
            story_id,
            chapters=[
                _chapter_payload(1, [1, 2]),
                _chapter_payload(2, [3, 4]),
            ],
        ).status_code
        == 200
    )
    return story


def _count(app, model) -> int:
    with app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_get_post_config_missing_returns_null(client, story):
    response = client.get(f"/api/stories/{story['id']}/post-config")
    assert response.status_code == 200
    assert response.json() is None


def test_post_config_story_not_found(client):
    response = client.get("/api/stories/9999/post-config")
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"

    response = client.put(
        "/api/stories/9999/post-config",
        json={"title": "标题", "content": "正文"},
    )
    assert response.status_code == 404


def test_put_creates_and_updates(client, app, story):
    story_id = story["id"]
    created = client.put(
        f"/api/stories/{story_id}/post-config",
        json={"title": "相亲遇到A8女", "content": "正文内容 #条漫"},
    )
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["story_id"] == story_id
    assert data["title"] == "相亲遇到A8女"
    assert data["content"] == "正文内容 #条漫"
    assert data["created_at"].endswith("Z")

    got = client.get(f"/api/stories/{story_id}/post-config").json()
    assert got["title"] == "相亲遇到A8女"

    updated = client.put(
        f"/api/stories/{story_id}/post-config",
        json={"title": "新标题", "content": "新正文"},
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == data["id"]
    assert updated.json()["title"] == "新标题"

    # 一个故事只保留一份配置
    assert _count(app, StoryPostConfig) == 1


def test_empty_title_and_content_allowed(client, story):
    response = client.put(
        f"/api/stories/{story['id']}/post-config",
        json={"title": "  ", "content": ""},
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == ""
    assert response.json()["content"] == ""


def test_post_config_title_limit_18(client, story):
    """标题最多 18 字：边界值可保存，超出被拒绝。"""
    story_id = story["id"]

    ok = client.put(
        f"/api/stories/{story_id}/post-config",
        json={"title": "x" * 18, "content": "正文"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["title"] == "x" * 18

    too_long = client.put(
        f"/api/stories/{story_id}/post-config",
        json={"title": "x" * 19, "content": "正文"},
    )
    assert too_long.status_code == 422


def test_post_config_validation(client, story):
    response = client.put(
        f"/api/stories/{story['id']}/post-config",
        json={"title": "标题", "content": "x" * 20001},
    )
    assert response.status_code == 422


def test_delete_story_cascades_config(client, app, story):
    story_id = story["id"]
    assert (
        client.put(
            f"/api/stories/{story_id}/post-config",
            json={"title": "标题", "content": "正文"},
        ).status_code
        == 200
    )
    assert _count(app, StoryPostConfig) == 1

    assert client.delete(f"/api/stories/{story_id}").status_code == 204
    assert _count(app, StoryPostConfig) == 0


def test_chapter_post_config_crud(client, app):
    story = _prepare_chapters(client)
    story_id = story["id"]

    missing = client.get(
        f"/api/stories/{story_id}/post-config?chapter=1"
    )
    assert missing.status_code == 200
    assert missing.json() is None

    created = client.put(
        f"/api/stories/{story_id}/post-config?chapter=2",
        json={"title": "第二章标题", "content": "第二章正文 #条漫"},
    )
    assert created.status_code == 200, created.text
    data = created.json()
    assert data["chapter_number"] == 2
    assert data["title"] == "第二章标题"

    chapter_two = client.get(
        f"/api/stories/{story_id}/post-config?chapter=2"
    ).json()
    assert chapter_two["content"] == "第二章正文 #条漫"
    # 其他章和旧版整篇配置互不影响
    assert (
        client.get(
            f"/api/stories/{story_id}/post-config?chapter=1"
        ).json()
        is None
    )
    assert client.get(f"/api/stories/{story_id}/post-config").json() is None

    chapter_one = client.put(
        f"/api/stories/{story_id}/post-config?chapter=1",
        json={"title": "第一章标题", "content": "第一章正文"},
    )
    assert chapter_one.status_code == 200
    assert chapter_one.json()["chapter_number"] == 1

    updated = client.put(
        f"/api/stories/{story_id}/post-config?chapter=2",
        json={"title": "第二章新标题", "content": "第二章新正文"},
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == data["id"]
    assert updated.json()["title"] == "第二章新标题"
    assert _count(app, StoryChapterPostConfig) == 2


def test_chapter_post_config_requires_valid_chapter(client, story):
    # 没有章节规划
    response = client.get(
        f"/api/stories/{story['id']}/post-config?chapter=1"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "CHAPTERS_NOT_FOUND"

    chaptered_story = _prepare_chapters(client)
    story_id = chaptered_story["id"]
    response = client.get(
        f"/api/stories/{story_id}/post-config?chapter=99"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "CHAPTER_NOT_FOUND"


def test_delete_story_cascades_chapter_configs(client, app):
    story = _prepare_chapters(client)
    story_id = story["id"]
    assert (
        client.put(
            f"/api/stories/{story_id}/post-config?chapter=1",
            json={"title": "标题", "content": "正文"},
        ).status_code
        == 200
    )
    assert _count(app, StoryChapterPostConfig) == 1

    assert client.delete(f"/api/stories/{story_id}").status_code == 204
    assert _count(app, StoryChapterPostConfig) == 0
