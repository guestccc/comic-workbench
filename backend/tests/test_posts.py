"""发文接口测试。"""

from __future__ import annotations


def test_post_crud_and_filters(client, story):
    created = client.post(
        "/api/posts",
        json={"story_id": story["id"], "title": "标题1", "content": "正文1"},
    )
    assert created.status_code == 201
    post = created.json()
    assert post["story_name"] == "测试故事"
    assert post["status"] == "draft"
    assert post["created_at"].endswith("Z")

    by_story = client.get("/api/posts", params={"story_id": story["id"]}).json()
    assert len(by_story) == 1
    assert client.get("/api/posts", params={"status": "published"}).json() == []

    patched = client.patch(
        f"/api/posts/{post['id']}", json={"status": "published", "title": "新标题"}
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "published"
    assert patched.json()["title"] == "新标题"
    assert len(client.get("/api/posts", params={"status": "published"}).json()) == 1

    assert client.delete(f"/api/posts/{post['id']}").status_code == 204
    assert client.get(f"/api/posts/{post['id']}").status_code == 404


def test_invalid_status_rejected(client, story):
    response = client.post(
        "/api/posts",
        json={
            "story_id": story["id"],
            "title": "t",
            "content": "c",
            "status": "unknown",
        },
    )
    assert response.status_code == 422
    assert (
        client.get("/api/posts", params={"status": "unknown"}).status_code == 422
    )


def test_post_validation(client, story):
    assert (
        client.post(
            "/api/posts",
            json={"story_id": story["id"], "title": "  ", "content": "c"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/posts",
            json={"story_id": story["id"], "title": "t", "content": "c" * 20001},
        ).status_code
        == 422
    )


def test_missing_story_rejected(client):
    response = client.post(
        "/api/posts", json={"story_id": 9999, "title": "t", "content": "c"}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"


def test_delete_post_keeps_story(client, story):
    post = client.post(
        "/api/posts",
        json={"story_id": story["id"], "title": "t", "content": "c"},
    ).json()
    assert client.delete(f"/api/posts/{post['id']}").status_code == 204
    assert client.get(f"/api/stories/{story['id']}").status_code == 200
