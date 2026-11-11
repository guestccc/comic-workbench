"""发布前检查：检查项契约、别名水印检测与重复发布门禁。"""

from __future__ import annotations

import io

from PIL import Image

from tests.test_publishing import (
    _account,
    _prepare_publishable,
    _preview,
)


def _check(data: dict, key: str) -> dict:
    return next(item for item in data["checks"] if item["key"] == key)


def _real_png() -> bytes:
    """发布前检查要读图片像素信息，测试图必须是可解码的 PNG。"""
    buffer = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _refresh_images(client, story_id: int) -> None:
    """把 fixture 里的占位字节换成真实 PNG，供加别名与哈希检测使用。"""
    for page_number in (1, 2):
        uploaded = client.post(
            f"/api/stories/{story_id}/breakdown/pages/{page_number}/image",
            files={"file": ("page.png", _real_png(), "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text
    for kind in ("cover", "guide"):
        uploaded = client.post(
            f"/api/stories/{story_id}/breakdown/chapters/1/{kind}/image",
            files={"file": (f"{kind}.png", _real_png(), "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text


def _job_payload(story_id: int, preview: dict) -> dict:
    return {
        "story_id": story_id,
        "chapter_number": 1,
        "platform": "douyin",
        "account_id": preview["account"]["id"],
        "schedule_at": preview["schedule_at"],
        "preview_hash": preview["payload_hash"],
        "confirm": True,
    }


def test_preview_returns_grouped_checks_with_derived_errors(client):
    story = _prepare_publishable(client)
    data = _preview(client, story["id"]).json()

    assert [item["key"] for item in data["checks"]] == [
        "content.config",
        "content.title",
        "content.note",
        "content.length",
        "content.tags",
        "content.sensitive",
        "alias.configured",
        "alias.valid",
        "alias.note_prefix",
        "alias.images",
        "images.chapter",
        "images.cover",
        "images.guide",
        "images.pages",
        "images.count",
        "images.format",
        "images.order",
        "account.login",
        "platform.schedule",
        "platform.duplicate",
    ]
    assert {item["group"] for item in data["checks"]} == {
        "content",
        "alias",
        "images",
        "account",
        "platform",
    }
    # errors / warnings 必须完全由 checks 派生，不能再单独追加
    assert data["errors"] == [
        item["message"]
        for item in data["checks"]
        if item["status"] == "error"
    ]
    assert data["warnings"] == [
        item["message"]
        for item in data["checks"]
        if item["status"] == "warning"
    ]

    assert _check(data, "alias.configured")["status"] == "pass"
    assert _check(data, "alias.note_prefix")["status"] == "pass"
    alias_images = _check(data, "alias.images")
    assert alias_images["status"] == "warning"
    assert alias_images["action"] == "stamp_alias"
    assert [item["label"] for item in alias_images["items"]] == [
        "封面",
        "第1页",
        "第2页",
        "引导卡",
    ]
    assert _check(data, "images.order")["status"] == "pass"
    assert _check(data, "platform.duplicate")["status"] == "pass"


def test_empty_tags_block_publish(client):
    story = _prepare_publishable(client)
    saved = client.put(
        f"/api/stories/{story['id']}/post-config?chapter=1",
        json={"title": "第一章：她重生了", "content": "正文", "tags": []},
    )
    assert saved.status_code == 200, saved.text

    preview = _preview(client, story["id"]).json()
    tags = _check(preview, "content.tags")
    assert tags["status"] == "error"
    assert tags["action"] == "open_post_config"
    assert "至少" in tags["message"]

    duplicate = client.post(
        "/api/publishing/jobs", json=_job_payload(story["id"], preview)
    )
    assert duplicate.status_code == 422
    assert "至少" in duplicate.json()["detail"]


def test_missing_alias_is_blocking_and_points_to_zhihu(client):
    story = _prepare_publishable(client)
    cleared = client.patch(
        f"/api/stories/{story['id']}/zhihu", json={"zhihu_alias": ""}
    )
    assert cleared.status_code == 200, cleared.text

    data = _preview(client, story["id"]).json()
    configured = _check(data, "alias.configured")
    assert configured["status"] == "error"
    assert configured["action"] == "open_zhihu"
    assert any("最终别名" in item for item in data["errors"])


def test_alias_stamp_check_follows_current_images(client):
    story = _prepare_publishable(client)
    _refresh_images(client, story["id"])
    before = _preview(client, story["id"]).json()
    assert _check(before, "alias.images")["status"] == "warning"

    stamped = client.post(
        f"/api/stories/{story['id']}/alias-stamp",
        json={"chapter_number": 1},
    )
    assert stamped.status_code == 200, stamped.text
    result = stamped.json()
    assert result["alias"] == "晚风替我告白"
    assert result["stamped"] == 4
    assert result["failed"] == 0

    after = _preview(client, story["id"]).json()
    check = _check(after, "alias.images")
    assert check["status"] == "pass"
    assert all(item["status"] == "pass" for item in check["items"])
    assert check["action"] is None


def test_alias_stamp_check_reports_wrong_alias(client):
    """换别名后旧水印不算已加，必须提示重新处理。"""
    story = _prepare_publishable(client)
    _refresh_images(client, story["id"])
    stamped = client.post(
        f"/api/stories/{story['id']}/alias-stamp",
        json={"chapter_number": 1},
    )
    assert stamped.status_code == 200, stamped.text

    changed = client.patch(
        f"/api/stories/{story['id']}/zhihu", json={"zhihu_alias": "旧梦替我告白"}
    )
    assert changed.status_code == 200, changed.text

    data = _preview(client, story["id"]).json()
    check = _check(data, "alias.images")
    assert check["status"] == "warning"
    assert "旧梦替我告白" in check["message"]
    assert check["action"] == "stamp_alias"


def test_duplicate_publish_blocks_until_previous_job_fails(
    client, monkeypatch, app
):
    monkeypatch.setattr(
        "app.routers.publishing.start_job_thread", lambda *args, **kwargs: None
    )
    story = _prepare_publishable(client)
    preview = _preview(client, story["id"]).json()
    created = client.post(
        "/api/publishing/jobs", json=_job_payload(story["id"], preview)
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    again = _preview(client, story["id"]).json()
    duplicate = _check(again, "platform.duplicate")
    assert duplicate["status"] == "error"
    assert duplicate["action"] is None
    assert any("只能发布一次" in item for item in again["errors"])

    # 失败任务不算已发布，允许重新预览并发起
    with app.state.session_factory() as session:
        from app.models import PublishJob

        job = session.get(PublishJob, job_id)
        job.status = "failed"
        session.commit()

    retry = _preview(client, story["id"]).json()
    assert _check(retry, "platform.duplicate")["status"] == "pass"


def test_sensitive_words_are_reported_as_warning(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.publishing.load_sensitive_words",
        lambda db: [
            {
                "word": "重生",
                "replacement": "",
                "category": "测试",
                "enabled": True,
            }
        ],
    )
    story = _prepare_publishable(client)
    data = _preview(client, story["id"]).json()

    check = _check(data, "content.sensitive")
    assert check["status"] == "warning"
    assert "重生" in check["message"]
    assert check["action"] == "open_post_config"
    assert data["errors"] == []


def test_create_rejects_platform_mismatch_before_checks(client):
    story = _prepare_publishable(client)
    response = client.post(
        "/api/publishing/preview",
        json={
            "story_id": story["id"],
            "chapter_number": 1,
            "platform": "xiaohongshu",
            "account_id": _account(client, "douyin")["id"],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PLATFORM_MISMATCH"
