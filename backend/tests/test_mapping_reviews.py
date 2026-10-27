"""分镜对照审阅：草稿、决策、应用与安全闸门测试。"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import StoryChapterPostConfig
from tests.test_breakdowns import (
    _chapter_payload,
    _patch_breakdown,
    _put_page,
)

STYLE = {"id": "style-a", "name": "测试画风", "content": "测试描述"}
OPTIMIZED = "甲乙丙丁。戊己庚辛。"
BASE_MAPPING = [
    {
        "page_number": 1,
        "source_text": "甲乙丙丁。",
        "summary": "第一段",
        "paragraph": "1",
        "part": "",
        "excluded": False,
    },
    {
        "page_number": 2,
        "source_text": "戊己庚辛。",
        "summary": "第二段",
        "paragraph": "2",
        "part": "",
        "excluded": False,
    },
]


def _setup(client, mapping=None, optimized=OPTIMIZED):
    assert (
        client.put(
            "/api/settings/art-styles",
            json={"styles": [STYLE], "active_id": "style-a"},
        ).status_code
        == 200
    )
    story = client.post(
        "/api/stories",
        json={
            "name": "审阅测试",
            "content": "原文内容。",
            "art_style_id": "style-a",
        },
    ).json()
    response = _patch_breakdown(
        client,
        story["id"],
        optimized_content=optimized,
        mapping=mapping or BASE_MAPPING,
    )
    assert response.status_code == 200, response.text
    return story


def _split_change(change_id="c1", risk="low", page=1, left="甲乙", right="丙丁。"):
    return {
        "id": change_id,
        "kind": "split",
        "risk": risk,
        "old_page_numbers": [page],
        "proposed_segments": [
            {"source_text": left, "summary": "前半"},
            {"source_text": right, "summary": "后半"},
        ],
        "reason": "一页里有两个动作，拆开" if risk != "low" else "拆成两页",
    }


def _put_review(client, story_id, changes):
    return client.put(
        f"/api/stories/{story_id}/breakdown/mapping-review",
        json={"changes": changes},
    )


def _apply(client, story_id, clear_chapters=False):
    return client.post(
        f"/api/stories/{story_id}/breakdown/mapping-review/apply",
        json={"clear_chapters": clear_chapters},
    )


def test_low_risk_auto_approved_and_apply(client):
    story = _setup(client)
    response = _put_review(client, story["id"], [_split_change()])
    assert response.status_code == 200, response.text
    review = response.json()
    assert review["status"] == "draft"
    assert review["decisions"] == {"c1": "approved"}
    assert review["summary"]["current_page_count"] == 2
    assert review["summary"]["proposed_page_count"] == 3
    assert review["summary"]["pending_count"] == 0
    assert review["summary"]["auto_approved_count"] == 1

    applied = _apply(client, story["id"])
    assert applied.status_code == 200, applied.text
    data = applied.json()
    assert data["strict_coverage"] is True
    assert data["chapters_cleared"] is False
    assert [item["source_text"] for item in data["breakdown"]["mapping"]] == [
        "甲乙",
        "丙丁。",
        "戊己庚辛。",
    ]
    assert [item["page_number"] for item in data["breakdown"]["mapping"]] == [
        1,
        2,
        3,
    ]


def test_high_risk_stays_undecided_and_is_not_applied(client):
    story = _setup(client)
    response = _put_review(
        client,
        story["id"],
        [
            _split_change("c1", "low"),
            _split_change("c2", "high", page=2, left="戊己", right="庚辛。"),
        ],
    )
    assert response.status_code == 200, response.text
    review = response.json()
    assert review["decisions"] == {"c1": "approved", "c2": "undecided"}
    assert review["summary"]["pending_count"] == 1

    applied = _apply(client, story["id"])
    assert applied.status_code == 200, applied.text
    mapping = applied.json()["breakdown"]["mapping"]
    assert [item["source_text"] for item in mapping] == [
        "甲乙",
        "丙丁。",
        "戊己庚辛。",
    ]


def test_apply_requires_approved_changes(client):
    story = _setup(client)
    response = _put_review(
        client,
        story["id"],
        [_split_change("c1", "high", page=1, left="甲乙", right="丙丁。")],
    )
    assert response.status_code == 200, response.text
    applied = _apply(client, story["id"])
    assert applied.status_code == 422
    assert applied.json()["code"] == "MAPPING_REVIEW_NO_APPROVED_CHANGES"


def test_invalid_change_boundaries_rejected(client):
    story = _setup(client)
    change = _split_change()
    change["proposed_segments"][0]["source_text"] = "甲"
    response = _put_review(client, story["id"], [change])
    assert response.status_code == 422
    assert response.json()["code"] == "MAPPING_REVIEW_COVERAGE_INVALID"


def test_unknown_decision_rejected(client):
    story = _setup(client)
    assert _put_review(client, story["id"], [_split_change()]).status_code == 200
    response = client.patch(
        f"/api/stories/{story['id']}/breakdown/mapping-review",
        json={"decisions": {"missing": "approved"}},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "MAPPING_REVIEW_INVALID_CHANGE"


def test_stale_mapping_rejected(client):
    story = _setup(client)
    assert _put_review(client, story["id"], [_split_change()]).status_code == 200
    changed = [
        {**BASE_MAPPING[0], "summary": "改过的简述"},
        BASE_MAPPING[1],
    ]
    assert (
        _patch_breakdown(client, story["id"], mapping=changed).status_code
        == 200
    )
    response = _apply(client, story["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "MAPPING_REVIEW_STALE"


def test_pages_existing_blocks_apply(client):
    story = _setup(client)
    assert _put_review(client, story["id"], [_split_change()]).status_code == 200
    assert _put_page(client, story["id"], 1).status_code == 200
    response = _apply(client, story["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "MAPPING_REVIEW_PAGES_EXIST"


def test_excluded_page_cannot_be_changed(client):
    excluded = [
        {**BASE_MAPPING[0], "excluded": True},
        BASE_MAPPING[1],
    ]
    story = _setup(client, mapping=excluded)
    change = _split_change()
    change["old_page_numbers"] = [1]
    response = _put_review(client, story["id"], [change])
    assert response.status_code == 422
    assert response.json()["code"] == "MAPPING_REVIEW_INVALID_CHANGE"


def test_chapters_require_confirmation_and_clear_configs_and_assets(
    client, app, app_settings
):
    story = _setup(client)
    story_id = story["id"]
    chapters = [_chapter_payload(1, [1, 2])]
    assert (
        _patch_breakdown(client, story_id, chapters=chapters).status_code
        == 200
    )
    saved = client.put(
        f"/api/stories/{story_id}/post-config?chapter=1",
        json={"title": "第一章文案", "content": "正文"},
    )
    assert saved.status_code == 200, saved.text

    asset_dir = app_settings.upload_dir / "chapters" / str(story_id)
    asset_dir.mkdir(parents=True)
    (asset_dir / "chapter-1-cover.png").write_bytes(b"fake")

    assert _put_review(client, story_id, [_split_change()]).status_code == 200

    blocked = _apply(client, story_id, clear_chapters=False)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "MAPPING_REVIEW_CHAPTERS_LOCKED"

    applied = _apply(client, story_id, clear_chapters=True)
    assert applied.status_code == 200, applied.text
    data = applied.json()
    assert data["chapters_cleared"] is True
    assert data["breakdown"]["chapters"] == []
    assert not asset_dir.exists()
    archive_root = app_settings.upload_dir / "chapters-archive"
    assert any(archive_root.iterdir())

    with app.state.session_factory() as session:
        count = session.scalar(
            select(func.count()).select_from(StoryChapterPostConfig)
        )
    assert count == 0


def test_discard_review(client):
    story = _setup(client)
    assert _put_review(client, story["id"], [_split_change()]).status_code == 200
    assert (
        client.delete(
            f"/api/stories/{story['id']}/breakdown/mapping-review"
        ).status_code
        == 204
    )
    assert (
        client.get(
            f"/api/stories/{story['id']}/breakdown/mapping-review"
        ).status_code
        == 404
    )
