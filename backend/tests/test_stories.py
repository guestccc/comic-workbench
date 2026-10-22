"""故事接口测试。"""

from __future__ import annotations

from tests.test_uploads import PNG_BYTES


def _upload_cover(client):
    response = client.post(
        "/api/uploads", files={"file": ("cover.png", PNG_BYTES, "image/png")}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_story_crud(client):
    created = client.post(
        "/api/stories", json={"name": "故事A", "content": "内容A"}
    )
    assert created.status_code == 201
    story = created.json()
    assert story["cover_url"] is None
    assert story["created_at"].endswith("Z")
    assert story["updated_at"].endswith("Z")

    listing = client.get("/api/stories").json()
    assert [item["id"] for item in listing] == [story["id"]]

    got = client.get(f"/api/stories/{story['id']}").json()
    assert got["name"] == "故事A"

    updated = client.put(
        f"/api/stories/{story['id']}",
        json={"name": "故事B", "content": "内容B", "cover_filename": None},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "故事B"

    deleted = client.delete(f"/api/stories/{story['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/stories/{story['id']}").status_code == 404


def test_story_validation(client):
    assert (
        client.post("/api/stories", json={"name": "", "content": "x"}).status_code
        == 422
    )
    assert (
        client.post("/api/stories", json={"name": "x", "content": "   "}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/stories", json={"name": "x" * 201, "content": "x"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/stories", json={"name": "x", "content": "x" * 30001}
        ).status_code
        == 422
    )


def test_story_missing_returns_404(client):
    response = client.get("/api/stories/9999")
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"


def test_story_with_cover_and_cleanup(client):
    upload = _upload_cover(client)
    created = client.post(
        "/api/stories",
        json={
            "name": "封面故事",
            "content": "内容",
            "cover_filename": upload["filename"],
        },
    )
    assert created.status_code == 201
    story = created.json()
    assert story["cover_url"] == upload["url"]
    assert client.get(upload["url"]).status_code == 200

    # 删除故事后封面文件也被删除
    assert client.delete(f"/api/stories/{story['id']}").status_code == 204
    assert client.get(upload["url"]).status_code == 404


def test_replace_cover_deletes_old_file(client):
    first = _upload_cover(client)
    second = _upload_cover(client)
    story = client.post(
        "/api/stories",
        json={
            "name": "换封面",
            "content": "内容",
            "cover_filename": first["filename"],
        },
    ).json()

    updated = client.put(
        f"/api/stories/{story['id']}",
        json={
            "name": "换封面",
            "content": "内容",
            "cover_filename": second["filename"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["cover_url"] == second["url"]
    assert client.get(first["url"]).status_code == 404
    assert client.get(second["url"]).status_code == 200


def test_invalid_cover_filename_rejected(client):
    response = client.post(
        "/api/stories",
        json={"name": "x", "content": "y", "cover_filename": "../evil.png"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_COVER_FILENAME"

    missing = client.post(
        "/api/stories",
        json={"name": "x", "content": "y", "cover_filename": "a" * 32 + ".png"},
    )
    assert missing.status_code == 422
    assert missing.json()["code"] == "COVER_FILE_NOT_FOUND"


def test_delete_story_with_posts_blocked(client, story):
    post = client.post(
        "/api/posts",
        json={"story_id": story["id"], "title": "标题", "content": "正文"},
    )
    assert post.status_code == 201

    response = client.delete(f"/api/stories/{story['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "STORY_HAS_POSTS"
    # 故事与发文都保留
    assert client.get(f"/api/stories/{story['id']}").status_code == 200
    assert len(client.get("/api/posts").json()) == 1
