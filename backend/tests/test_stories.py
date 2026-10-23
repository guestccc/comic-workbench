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


def test_story_name_optional(client):
    """故事名可留空，拆解后再手动补填。"""
    created = client.post("/api/stories", json={"content": "内容"})
    assert created.status_code == 201, created.text
    story = created.json()
    assert story["name"] == ""

    # 仅空白字符同样视为留空
    blank = client.post("/api/stories", json={"name": "   ", "content": "内容"})
    assert blank.status_code == 201, blank.text
    assert blank.json()["name"] == ""

    # 拆解得到名称后可补填
    updated = client.put(
        f"/api/stories/{story['id']}",
        json={"name": "拆解得到的名字", "content": "内容", "cover_filename": None},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "拆解得到的名字"


def test_story_validation(client):
    # 故事原文必填
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


def _save_art_styles(client, styles, active_id=None):
    response = client.put(
        "/api/settings/art-styles",
        json={"styles": styles, "active_id": active_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


STYLE_A = {"id": "style-a", "name": "唯美彩铅", "content": "韩式唯美彩铅手绘"}
STYLE_B = {"id": "style-b", "name": "日系赛璐璐", "content": "日系赛璐璐平涂"}


def test_story_art_style_resolved(client):
    """故事选择画风后，响应中解析出画风名称与描述。"""
    _save_art_styles(client, [STYLE_A, STYLE_B], active_id="style-a")

    created = client.post(
        "/api/stories",
        json={"name": "画风故事", "content": "内容", "art_style_id": "style-a"},
    )
    assert created.status_code == 201, created.text
    story = created.json()
    assert story["art_style_id"] == "style-a"
    assert story["art_style_name"] == "唯美彩铅"
    assert story["art_style_content"] == "韩式唯美彩铅手绘"

    # 列表与详情都会解析画风
    listed = client.get("/api/stories").json()[0]
    assert listed["art_style_name"] == "唯美彩铅"
    detail = client.get(f"/api/stories/{story['id']}").json()
    assert detail["art_style_content"] == "韩式唯美彩铅手绘"

    # 更换画风
    updated = client.put(
        f"/api/stories/{story['id']}",
        json={
            "name": "画风故事",
            "content": "内容",
            "cover_filename": None,
            "art_style_id": "style-b",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["art_style_name"] == "日系赛璐璐"

    # 清空画风
    cleared = client.put(
        f"/api/stories/{story['id']}",
        json={
            "name": "画风故事",
            "content": "内容",
            "cover_filename": None,
            "art_style_id": None,
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["art_style_id"] is None
    assert cleared.json()["art_style_name"] is None


def test_story_art_style_blank_normalized(client):
    """空白画风 id 视为未选择。"""
    created = client.post(
        "/api/stories",
        json={"name": "x", "content": "y", "art_style_id": "   "},
    )
    assert created.status_code == 201, created.text
    assert created.json()["art_style_id"] is None


def test_story_invalid_art_style_rejected(client):
    """不能引用画风列表中不存在的画风。"""
    _save_art_styles(client, [STYLE_A])

    created = client.post(
        "/api/stories",
        json={"name": "x", "content": "y", "art_style_id": "missing"},
    )
    assert created.status_code == 422
    assert created.json()["code"] == "ART_STYLE_NOT_FOUND"

    story = client.post(
        "/api/stories", json={"name": "x", "content": "y"}
    ).json()
    updated = client.put(
        f"/api/stories/{story['id']}",
        json={
            "name": "x",
            "content": "y",
            "cover_filename": None,
            "art_style_id": "missing",
        },
    )
    assert updated.status_code == 422
    assert updated.json()["code"] == "ART_STYLE_NOT_FOUND"


def test_story_art_style_deleted_becomes_dangling(client):
    """画风被删除后保留引用 id，但不再返回名称/描述。"""
    _save_art_styles(client, [STYLE_A], active_id="style-a")
    story = client.post(
        "/api/stories",
        json={"name": "x", "content": "y", "art_style_id": "style-a"},
    ).json()

    _save_art_styles(client, [], active_id=None)

    got = client.get(f"/api/stories/{story['id']}").json()
    assert got["art_style_id"] == "style-a"
    assert got["art_style_name"] is None
    assert got["art_style_content"] is None
