"""多平台发布：预设标签、预览校验、任务快照与状态判定。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.config import (
    PUBLISH_SUCCESS_MARKER,
    PUBLISH_TIMEZONE,
    AppSettings,
)
from app.errors import AppError
from app.services.files import ChapterImage
from app.services.publishing.link_capture import fetch_published_link
from app.services.publishing.link_parsing import (
    match_capture_item,
    merge_capture_items,
    normalize_title,
    parse_worker_output,
)
from app.services.publishing.runner import (
    PublishRunResult,
    build_upload_command,
    classify_result,
    strip_ansi,
)
from tests.test_breakdowns import (
    _chapter_payload,
    _mapping_items,
    _patch_breakdown,
    _prepare,
    _put_page,
)
from tests.test_uploads import PNG_BYTES

def _future(minutes: int = 180) -> str:
    """按平台本地时间给出未来时刻；界面上的定时时间就是北京时间。"""
    return (
        datetime.now(PUBLISH_TIMEZONE) + timedelta(minutes=minutes)
    ).isoformat()


def _prepare_publishable(client):
    """准备故事、1 章 2 页、封面 / 引导卡 / 正文图和发文配置。"""
    story, _ = _prepare(client)
    story_id = story["id"]
    # 发布前检查要求最终别名已配置；别名不能复用故事名「拆解故事」的连续两字。
    aliased = client.patch(
        f"/api/stories/{story_id}/zhihu",
        json={"zhihu_alias": "晚风替我告白"},
    )
    assert aliased.status_code == 200, aliased.text
    assert (
        _patch_breakdown(
            client, story_id, mapping=_mapping_items([1, 2])
        ).status_code
        == 200
    )
    assert (
        _patch_breakdown(
            client, story_id, chapters=[_chapter_payload(1, [1, 2])]
        ).status_code
        == 200
    )
    for page_number, chapter_page_number in ((1, 1), (2, 2)):
        assert (
            _put_page(
                client,
                story_id,
                page_number,
                mapping_page_number=page_number,
                chapter_number=1,
                chapter_page_number=chapter_page_number,
            ).status_code
            == 200
        )
        uploaded = client.post(
            f"/api/stories/{story_id}/breakdown/pages/{page_number}/image",
            files={"file": ("page.png", PNG_BYTES, "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text

    for kind in ("cover", "guide"):
        uploaded = client.post(
            f"/api/stories/{story_id}/breakdown/chapters/1/{kind}/image",
            files={"file": (f"{kind}.png", PNG_BYTES, "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text

    saved = client.put(
        f"/api/stories/{story_id}/post-config?chapter=1",
        json={
            "title": "第一章：她重生了",
            "content": "重来一世，她只想回家。",
            "tags": ["重生", "#爽文", "重生", " "],
        },
    )
    assert saved.status_code == 200, saved.text
    return story


def _account(client, platform: str = "douyin"):
    accounts = client.get(
        f"/api/publishing/accounts?platform={platform}"
    ).json()
    assert accounts
    return accounts[0]


def _preview(
    client,
    story_id,
    *,
    schedule_at=None,
    account_id=None,
    platform: str = "douyin",
):
    return client.post(
        "/api/publishing/preview",
        json={
            "story_id": story_id,
            "chapter_number": 1,
            "platform": platform,
            "account_id": account_id or _account(client, platform)["id"],
            "schedule_at": schedule_at or _future(),
        },
    )


def test_chapter_post_config_saves_cleaned_tags(client):
    story = _prepare_publishable(client)
    response = client.get(
        f"/api/stories/{story['id']}/post-config?chapter=1"
    )
    assert response.status_code == 200, response.text
    assert response.json()["tags"] == ["重生", "爽文"]


def test_tag_presets_default_to_story_topics(client):
    response = client.get("/api/publishing/tag-presets")
    assert response.status_code == 200
    assert response.json()["tags"] == ["画一个故事", "小说推文", "漫画故事"]


def test_tag_presets_round_trip(client):
    saved = client.put(
        "/api/publishing/tag-presets",
        json={"tags": ["重生", "#爽文", "逆袭", "重生"]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["tags"] == ["重生", "爽文", "逆袭"]

    read = client.get("/api/publishing/tag-presets")
    assert read.json()["tags"] == ["重生", "爽文", "逆袭"]


def test_tag_presets_explicit_empty_is_kept(client):
    saved = client.put("/api/publishing/tag-presets", json={"tags": []})
    assert saved.status_code == 200, saved.text

    read = client.get("/api/publishing/tag-presets")
    assert read.json()["tags"] == []


def test_accounts_are_seeded_per_platform(client):
    """抖音 / 小红书各自补种默认账号，互不串台；非法平台直接 422。"""
    douyin = client.get("/api/publishing/accounts").json()
    assert [item["platform"] for item in douyin] == ["douyin"]
    assert douyin[0]["display_name"] == "抖音主账号"

    xhs = client.get(
        "/api/publishing/accounts?platform=xiaohongshu"
    ).json()
    assert [item["platform"] for item in xhs] == ["xiaohongshu"]
    assert xhs[0]["display_name"] == "小红书主账号"

    again = client.get(
        "/api/publishing/accounts?platform=xiaohongshu"
    ).json()
    assert len(again) == 1

    invalid = client.get("/api/publishing/accounts?platform=weibo")
    assert invalid.status_code == 422


def test_preview_rejects_account_from_other_platform(client):
    story = _prepare_publishable(client)
    response = _preview(
        client,
        story["id"],
        platform="xiaohongshu",
        account_id=_account(client, "douyin")["id"],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PLATFORM_MISMATCH"


def test_preview_enforces_platform_image_limits(
    client, monkeypatch, app_settings
):
    """抖音 35 张、小红书 18 张；同一份图片清单按平台分别校验。"""
    story = _prepare_publishable(client)
    fake_path = app_settings.upload_dir / "fake.png"
    fake_path.write_bytes(PNG_BYTES)
    images = [
        ChapterImage(
            label=label,
            url=f"/uploads/fake.png?{index}",
            path=fake_path,
        )
        for index, label in enumerate(
            ["封面", *[f"第{number}页" for number in range(1, 20)], "引导卡"],
            start=1,
        )
    ]
    monkeypatch.setattr(
        "app.services.publishing.payload.collect_chapter_images",
        lambda *args, **kwargs: images,
    )

    douyin = _preview(client, story["id"]).json()
    assert douyin["errors"] == []

    xhs = _preview(client, story["id"], platform="xiaohongshu").json()
    assert any("小红书图文最多 18 张" in item for item in xhs["errors"])


def test_preview_orders_images_cover_pages_guide(client):
    story = _prepare_publishable(client)
    response = _preview(client, story["id"])
    assert response.status_code == 200, response.text
    data = response.json()

    assert [image["label"] for image in data["images"]] == [
        "封面",
        "第1页",
        "第2页",
        "引导卡",
    ]
    assert data["image_count"] == 4
    assert all(image["url"].startswith("/uploads/") for image in data["images"])
    assert data["title"] == "第一章：她重生了"
    assert data["tags"] == ["重生", "爽文"]
    assert data["errors"] == []
    assert len(data["payload_hash"]) == 64
    assert data["schedule_min_at"]


def test_preview_rejects_schedule_inside_two_hours(client):
    story = _prepare_publishable(client)
    response = _preview(client, story["id"], schedule_at=_future(60))
    assert response.status_code == 200, response.text
    data = response.json()
    assert any("2 小时" in item for item in data["errors"])


def test_preview_rejects_note_over_douyin_limit(client):
    story = _prepare_publishable(client)
    too_long = "字" * 1001
    saved = client.put(
        f"/api/stories/{story['id']}/post-config?chapter=1",
        json={"title": "标题", "content": too_long, "tags": []},
    )
    assert saved.status_code == 200, saved.text

    data = _preview(client, story["id"]).json()
    assert any("1000" in item for item in data["errors"])


def test_create_job_snapshots_images_and_blocks_duplicate(
    client, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.publishing.start_job_thread", lambda *args, **kwargs: None
    )
    story = _prepare_publishable(client)
    preview = _preview(client, story["id"]).json()

    payload = {
        "story_id": story["id"],
        "chapter_number": 1,
        "platform": "douyin",
        "account_id": _account(client)["id"],
        "schedule_at": preview["schedule_at"],
        "preview_hash": preview["payload_hash"],
        "confirm": True,
    }

    stale = dict(payload, preview_hash="0" * 64)
    response = client.post("/api/publishing/jobs", json=stale)
    assert response.status_code == 409
    assert response.json()["code"] == "PUBLISH_PREVIEW_STALE"

    unconfirmed = dict(payload, confirm=False)
    response = client.post("/api/publishing/jobs", json=unconfirmed)
    assert response.status_code == 422
    assert response.json()["code"] == "PUBLISH_NOT_CONFIRMED"

    created = client.post("/api/publishing/jobs", json=payload)
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["status"] == "queued"
    assert job["payload"]["title"] == "第一章：她重生了"
    assert [url.rsplit("/", 1)[-1][:2] for url in job["payload"]["images"]] == [
        "01",
        "02",
        "03",
        "04",
    ]
    assert all(
        url.startswith("/uploads/publish-jobs/")
        for url in job["payload"]["images"]
    )

    duplicate = client.post("/api/publishing/jobs", json=payload)
    assert duplicate.status_code == 422
    assert duplicate.json()["code"] == "PUBLISH_PAYLOAD_INVALID"
    assert any("已有排队中任务" in item for item in duplicate.json()["detail"].split("；"))


def test_job_log_and_manual_status_transition(
    client, monkeypatch, app_settings, app
):
    monkeypatch.setattr(
        "app.routers.publishing.start_job_thread", lambda *args, **kwargs: None
    )
    story = _prepare_publishable(client)
    preview = _preview(client, story["id"]).json()
    created = client.post(
        "/api/publishing/jobs",
        json={
            "story_id": story["id"],
            "chapter_number": 1,
            "platform": "douyin",
            "account_id": _account(client)["id"],
            "schedule_at": preview["schedule_at"],
            "preview_hash": preview["payload_hash"],
            "confirm": True,
        },
    ).json()
    job_id = created["id"]

    log_dir = app_settings.resolved_publish_log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{job_id}.log").write_text("上传中\n图文发布成功", encoding="utf-8")
    log = client.get(f"/api/publishing/jobs/{job_id}/log")
    assert log.status_code == 200
    assert "图文发布成功" in log.json()["text"]

    invalid = client.patch(
        f"/api/publishing/jobs/{job_id}", json={"status": "scheduled"}
    )
    assert invalid.status_code == 409

    with app.state.session_factory() as session:
        from app.models import PublishJob

        job = session.get(PublishJob, job_id)
        job.status = "unknown"
        session.commit()

    fixed = client.patch(
        f"/api/publishing/jobs/{job_id}",
        json={"status": "scheduled", "external_url": "https://example.com/p/1"},
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["status"] == "scheduled"
    assert fixed.json()["external_url"] == "https://example.com/p/1"


def test_story_with_publish_job_cannot_be_deleted(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.publishing.start_job_thread", lambda *args, **kwargs: None
    )
    story = _prepare_publishable(client)
    preview = _preview(client, story["id"]).json()
    created = client.post(
        "/api/publishing/jobs",
        json={
            "story_id": story["id"],
            "chapter_number": 1,
            "platform": "douyin",
            "account_id": _account(client)["id"],
            "schedule_at": preview["schedule_at"],
            "preview_hash": preview["payload_hash"],
            "confirm": True,
        },
    )
    assert created.status_code == 201

    deleted = client.delete(f"/api/stories/{story['id']}")
    assert deleted.status_code == 409
    assert deleted.json()["code"] == "STORY_HAS_PUBLISH_JOBS"


def test_build_upload_command_uses_local_time_and_comma_tags(tmp_path):
    settings = AppSettings(
        db_path=tmp_path / "test.db",
        upload_dir=tmp_path / "uploads",
        frontend_dist=tmp_path / "dist",
        sau_project_dir=tmp_path / "sau",
        sau_executable=tmp_path / "sau" / "sau.exe",
    )
    command = build_upload_command(
        settings,
        {
            "account_name": "default",
            "images": ["a.png", "b.png"],
            "title": "标题",
            "note": "正文",
            "tags": ["重生", "爽文"],
            "schedule_at": "2026-11-10T12:30:00Z",
        },
    )
    assert command[1:3] == ["douyin", "upload-note"]
    assert command[command.index("--tags") + 1] == "重生,爽文"
    assert command[command.index("--schedule") + 1] == "2026-11-10 20:30"
    assert "--images" in command

    xhs = build_upload_command(
        settings,
        {
            "platform": "xiaohongshu",
            "account_name": "default",
            "images": ["a.png"],
            "title": "标题",
            "note": "正文",
            "tags": [],
            "schedule_at": "2026-11-10T12:30:00Z",
        },
    )
    assert xhs[1:3] == ["xiaohongshu", "upload-note"]
    assert xhs[xhs.index("--schedule") + 1] == "2026-11-10 20:30"

    immediate = build_upload_command(
        settings,
        {
            "platform": "xiaohongshu",
            "mode": "immediate",
            "account_name": "default",
            "images": ["a.png"],
            "title": "标题",
            "note": "正文",
            "tags": [],
            "schedule_at": None,
        },
    )
    # 立即发布必须不带 --schedule，否则 sau 会走定时分支
    assert "--schedule" not in immediate

    with pytest.raises(ValueError):
        build_upload_command(
            settings,
            {
                "mode": "scheduled",
                "account_name": "default",
                "images": ["a.png"],
                "title": "标题",
                "note": "正文",
                "tags": [],
                "schedule_at": None,
            },
        )


def test_build_upload_command_passes_xhs_settings_only_for_xiaohongshu(
    tmp_path,
):
    settings = AppSettings(
        db_path=tmp_path / "test.db",
        upload_dir=tmp_path / "uploads",
        frontend_dist=tmp_path / "dist",
        sau_project_dir=tmp_path / "sau",
        sau_executable=tmp_path / "sau" / "sau.exe",
    )
    base = {
        "account_name": "default",
        "images": ["a.png"],
        "title": "标题",
        "note": "正文",
        "tags": [],
        "declaration": "笔记含AI合成内容",
        "collection": "西天路上的谜团",
    }
    xhs = build_upload_command(
        settings,
        {
            **base,
            "platform": "xiaohongshu",
            "mode": "immediate",
            "schedule_at": None,
        },
    )
    assert xhs[xhs.index("--declaration") + 1] == "笔记含AI合成内容"
    # 合集暂停接入：sau 工作区还没有 --collection，任何情况下都不能出现
    assert "--collection" not in xhs
    # 非来源转载时 repost_source 即使有值也不得出现
    assert "--repost-source" not in xhs

    repost = build_upload_command(
        settings,
        {
            **base,
            "platform": "xiaohongshu",
            "mode": "immediate",
            "schedule_at": None,
            "declaration": "来源转载",
            "repost_source": " 某媒体 ",
        },
    )
    assert repost[repost.index("--repost-source") + 1] == "某媒体"
    # --repost-source 与 --declaration 互斥，不能同时出现
    assert "--declaration" not in repost

    with pytest.raises(ValueError, match="来源媒体名"):
        build_upload_command(
            settings,
            {
                **base,
                "platform": "xiaohongshu",
                "mode": "immediate",
                "schedule_at": None,
                "declaration": "来源转载",
                "repost_source": None,
            },
        )

    douyin = build_upload_command(
        settings,
        {**base, "mode": "immediate", "schedule_at": None},
    )
    # 抖音图文没有这些参数，传了会被 argparse 拒绝
    assert "--declaration" not in douyin
    assert "--repost-source" not in douyin
    assert "--collection" not in douyin

    empty = build_upload_command(
        settings,
        {
            **base,
            "platform": "xiaohongshu",
            "mode": "immediate",
            "schedule_at": None,
            "declaration": None,
            "collection": None,
        },
    )
    assert "--declaration" not in empty
    assert "--collection" not in empty


def test_story_xiaohongshu_settings_round_trip(client):
    story = _prepare_publishable(client)
    story_id = story["id"]
    # 新故事默认声明 AI 合成内容、没有来源媒体名、不加入合集
    initial = client.get(f"/api/stories/{story_id}").json()
    assert initial["xhs_declaration"] == "笔记含AI合成内容"
    assert initial["xhs_repost_source"] == ""
    assert initial["xhs_collection"] == ""

    updated = client.patch(
        f"/api/stories/{story_id}/xiaohongshu",
        json={"declaration": ""},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["xhs_declaration"] == ""

    # 合集暂停接入：PATCH 收到 collection 也不改写已有值
    ignored = client.patch(
        f"/api/stories/{story_id}/xiaohongshu",
        json={"collection": "西天路上的谜团", "declaration": ""},
    )
    assert ignored.status_code == 200, ignored.text
    assert ignored.json()["xhs_collection"] == ""


def test_xhs_declaration_options_expose_platform_choices(client):
    body = client.get("/api/publishing/xhs-declaration-options").json()
    values = [item["value"] for item in body["options"]]
    assert values == [
        "",
        "虚构演绎，仅供娱乐",
        "笔记含AI合成内容",
        "内容包含营销广告",
        "来源转载",
    ]
    assert body["default"] == "笔记含AI合成内容"
    assert body["repost_value"] == "来源转载"
    # 「自主拍摄」需要拍摄地点与日期，sau 未实现，不能作为可选项
    assert "自主拍摄" not in values


def test_story_xiaohongshu_rejects_invalid_declaration(client):
    story = _prepare_publishable(client)
    story_id = story["id"]

    # 平台没有这个选项：拒绝写入，而不是静默存下来等发布时炸
    invalid = client.patch(
        f"/api/stories/{story_id}/xiaohongshu",
        json={"declaration": "笔记含AI"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "XHS_DECLARATION_INVALID"

    # 「来源转载」必须带媒体名，否则会发出空来源声明
    missing_source = client.patch(
        f"/api/stories/{story_id}/xiaohongshu",
        json={"declaration": "来源转载"},
    )
    assert missing_source.status_code == 422
    assert missing_source.json()["code"] == "XHS_REPOST_SOURCE_REQUIRED"

    ok = client.patch(
        f"/api/stories/{story_id}/xiaohongshu",
        json={"declaration": "来源转载", "repost_source": " 某媒体 "},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["xhs_declaration"] == "来源转载"
    assert ok.json()["xhs_repost_source"] == "某媒体"


def _check_by_key(preview_json: dict, key: str) -> dict:
    for check in preview_json["checks"]:
        if check["key"] == key:
            return check
    raise AssertionError(f"缺少检查项 {key}")


def test_xhs_preview_carries_declaration_and_collection(client):
    story = _prepare_publishable(client)
    story_id = story["id"]

    default = _preview(client, story_id, platform="xiaohongshu")
    assert default.status_code == 200, default.text
    body = default.json()
    assert body["declaration"] == "笔记含AI合成内容"
    assert body["repost_source"] is None
    # 合集暂停接入：载荷恒为空，也不产出合集检查项
    assert body["collection"] is None
    keys = {check["key"] for check in body["checks"]}
    assert "platform.collection" not in keys
    assert _check_by_key(body, "platform.declaration")["status"] == "pass"
    assert body["errors"] == []
    assert "没有设置小红书合集" not in " ".join(body["warnings"])

    assert (
        client.patch(
            f"/api/stories/{story_id}/xiaohongshu",
            json={"declaration": ""},
        ).status_code
        == 200
    )
    updated = _preview(client, story_id, platform="xiaohongshu").json()
    assert updated["declaration"] is None
    assert updated["repost_source"] is None
    assert updated["collection"] is None
    assert "未设置内容声明" in _check_by_key(
        updated, "platform.declaration"
    )["message"]

    assert (
        client.patch(
            f"/api/stories/{story_id}/xiaohongshu",
            json={
                "declaration": "来源转载",
                "repost_source": "某媒体",
            },
        ).status_code
        == 200
    )
    repost = _preview(client, story_id, platform="xiaohongshu").json()
    assert repost["declaration"] == "来源转载"
    assert repost["repost_source"] == "某媒体"
    # 来源转载也是内容声明，预检文案要带上媒体名
    assert "某媒体" in _check_by_key(repost, "platform.declaration")["message"]

    douyin = _preview(client, story_id).json()
    # 抖音不读取故事级小红书设置，也不产生这两项检查
    assert douyin["declaration"] is None
    assert douyin["repost_source"] is None
    assert douyin["collection"] is None
    keys = {check["key"] for check in douyin["checks"]}
    assert "platform.declaration" not in keys
    assert "platform.collection" not in keys


def test_xhs_job_payload_freezes_declaration_and_collection(
    client, monkeypatch, app
):
    story = _prepare_publishable(client)
    story_id = story["id"]
    assert (
        client.patch(
            f"/api/stories/{story_id}/xiaohongshu",
            json={
                "declaration": "来源转载",
                "repost_source": "某媒体",
            },
        ).status_code
        == 200
    )
    calls = []

    def _fake_start(session_factory, settings, job_id):
        calls.append(job_id)

    monkeypatch.setattr("app.routers.publishing.start_job_thread", _fake_start)
    preview = _preview(client, story_id, platform="xiaohongshu").json()
    created = client.post(
        "/api/publishing/jobs",
        json={
            "story_id": story_id,
            "chapter_number": 1,
            "platform": "xiaohongshu",
            "account_id": _account(client, "xiaohongshu")["id"],
            "publish_mode": "scheduled",
            "schedule_at": preview["schedule_at"],
            "preview_hash": preview["payload_hash"],
            "confirm": True,
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()["payload"]
    assert payload["declaration"] == "来源转载"
    assert payload["repost_source"] == "某媒体"
    # 合集暂停接入，载荷里恒为空
    assert payload["collection"] is None
    assert calls


def test_classify_result_never_treats_unmarked_zero_as_success():
    success = PublishRunResult(
        exit_code=0, timed_out=False, output=PUBLISH_SUCCESS_MARKER
    )
    assert classify_result(success)[0] == "scheduled"
    assert classify_result(success, "immediate")[0] == "published"
    assert classify_result(
        PublishRunResult(exit_code=1, timed_out=False, output="boom")
    )[0] == "failed"
    assert classify_result(
        PublishRunResult(exit_code=0, timed_out=False, output="finished")
    )[0] == "unknown"
    assert classify_result(
        PublishRunResult(exit_code=None, timed_out=True, output="")
    )[0] == "unknown"


def test_classify_result_strips_terminal_color_codes():
    """sau 日志带 ANSI 颜色码，任务结果里必须去掉，否则界面显示乱码。"""
    result = PublishRunResult(
        exit_code=1,
        timed_out=False,
        output="\x1b[38;2;112;172;222m2026-11-09\x1b[0m | \x1b[97m失败\x1b[0m",
    )
    status, message = classify_result(result)
    assert status == "failed"
    assert "\x1b" not in message
    assert message == "发布器退出码 1：2026-11-09 | 失败"
    assert strip_ansi("\x1b[31m红\x1b[0m") == "红"


def test_list_jobs_filters_by_status(client, monkeypatch):
    """总览页按状态筛选；非法状态直接 422，不能静默忽略。"""
    monkeypatch.setattr(
        "app.routers.publishing.start_job_thread", lambda *args, **kwargs: None
    )
    story = _prepare_publishable(client)
    preview = _preview(client, story["id"]).json()
    created = client.post(
        "/api/publishing/jobs",
        json={
            "story_id": story["id"],
            "chapter_number": 1,
            "platform": "douyin",
            "account_id": _account(client)["id"],
            "schedule_at": preview["schedule_at"],
            "preview_hash": preview["payload_hash"],
            "confirm": True,
        },
    )
    assert created.status_code == 201, created.text

    queued = client.get("/api/publishing/jobs?status=queued")
    assert queued.status_code == 200
    assert [job["id"] for job in queued.json()] == [created.json()["id"]]

    scheduled = client.get("/api/publishing/jobs?status=scheduled")
    assert scheduled.status_code == 200
    assert scheduled.json() == []

    invalid = client.get("/api/publishing/jobs?status=bogus")
    assert invalid.status_code == 422


def test_xiaohongshu_job_and_platform_filter(client, monkeypatch):
    """小红书走同一套预览 / 建任务契约，并按平台隔离任务列表。"""
    monkeypatch.setattr(
        "app.routers.publishing.start_job_thread", lambda *args, **kwargs: None
    )
    story = _prepare_publishable(client)
    account = _account(client, "xiaohongshu")
    preview = _preview(
        client, story["id"], platform="xiaohongshu", account_id=account["id"]
    ).json()
    assert preview["platform"] == "xiaohongshu"
    assert preview["account"]["platform"] == "xiaohongshu"
    assert preview["errors"] == []

    created = client.post(
        "/api/publishing/jobs",
        json={
            "story_id": story["id"],
            "chapter_number": 1,
            "platform": "xiaohongshu",
            "account_id": account["id"],
            "schedule_at": preview["schedule_at"],
            "preview_hash": preview["payload_hash"],
            "confirm": True,
        },
    )
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["platform"] == "xiaohongshu"

    xhs = client.get("/api/publishing/jobs?platform=xiaohongshu").json()
    assert [item["id"] for item in xhs] == [job["id"]]
    assert client.get("/api/publishing/jobs?platform=douyin").json() == []
    assert (
        client.get("/api/publishing/jobs?platform=weibo").status_code == 422
    )


def test_preview_enforces_fourteen_day_schedule_window(client):
    story = _prepare_publishable(client)
    too_far = _preview(
        client, story["id"], schedule_at=_future(minutes=14 * 24 * 60 + 60)
    )
    assert too_far.status_code == 200
    assert any(
        "不能超过当前时间 14 天" in item for item in too_far.json()["errors"]
    )

    within = _preview(
        client, story["id"], schedule_at=_future(minutes=13 * 24 * 60)
    )
    assert within.status_code == 200
    assert within.json()["errors"] == []
    assert within.json()["schedule_max_at"]


def test_immediate_preview_needs_no_schedule_and_rejects_one(client):
    story = _prepare_publishable(client)
    body = {
        "story_id": story["id"],
        "chapter_number": 1,
        "platform": "douyin",
        "account_id": _account(client)["id"],
        "publish_mode": "immediate",
    }

    response = client.post("/api/publishing/preview", json=body)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["publish_mode"] == "immediate"
    assert preview["schedule_at"] is None
    assert preview["errors"] == []
    assert len(preview["payload_hash"]) == 64

    with_schedule = client.post(
        "/api/publishing/preview",
        json={**body, "schedule_at": _future()},
    )
    assert with_schedule.status_code == 200, with_schedule.text
    assert any(
        "立即发布不需要定时时间" in item
        for item in with_schedule.json()["errors"]
    )


def test_immediate_job_creation_keeps_mode_in_payload(client, monkeypatch, app):
    monkeypatch.setattr(
        "app.routers.publishing.start_job_thread", lambda *args, **kwargs: None
    )
    story = _prepare_publishable(client)
    account = _account(client)
    preview = client.post(
        "/api/publishing/preview",
        json={
            "story_id": story["id"],
            "chapter_number": 1,
            "platform": "douyin",
            "account_id": account["id"],
            "publish_mode": "immediate",
        },
    ).json()
    assert preview["errors"] == []

    created = client.post(
        "/api/publishing/jobs",
        json={
            "story_id": story["id"],
            "chapter_number": 1,
            "platform": "douyin",
            "account_id": account["id"],
            "publish_mode": "immediate",
            "schedule_at": None,
            "preview_hash": preview["payload_hash"],
            "confirm": True,
        },
    )
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["status"] == "queued"
    assert job["payload"]["mode"] == "immediate"
    assert job["payload"]["schedule_at"] is None
    # scheduled_at 列不可为空：立即任务存创建时刻作为执行锚点
    assert job["scheduled_at"]

    with app.state.session_factory() as session:
        from app.models import PublishJob

        stored = session.get(PublishJob, job["id"])
        assert stored.payload_json["mode"] == "immediate"
        assert stored.payload_json["schedule_at"] is None


# ---------------------------------------------------------------------------
# 作品链接抓取
# ---------------------------------------------------------------------------


def _capture_settings(tmp_path):
    """构造一个「sau 环境与 Cookie 都齐全」的配置，避免真实启动浏览器。"""
    sau_dir = tmp_path / "sau"
    cookie_dir = sau_dir / "cookies"
    cookie_dir.mkdir(parents=True)
    (cookie_dir / "douyin_main.json").write_text("{}", encoding="utf-8")
    (cookie_dir / "xiaohongshu_main.json").write_text("{}", encoding="utf-8")
    (sau_dir / ".venv" / "Scripts").mkdir(parents=True)
    executable = sau_dir / ".venv" / "Scripts" / "sau.exe"
    executable.write_text("", encoding="utf-8")
    (executable.parent / "python.exe").write_text("", encoding="utf-8")
    return AppSettings(sau_project_dir=sau_dir, sau_executable=executable)


def test_match_capture_item_prefers_latest_and_uses_first_line():
    douyin_url = "https://www.douyin.com/note/7704983002492816678"
    older = {
        "title": "第一章：她重生了。\n重来一世，她只想回家。",
        "url": "https://www.douyin.com/note/1",
        "created_at": 100,
    }
    # 抖音首行实测为「标题。【最终别名】」，标题与别名连写
    newer = {
        "title": "第一章：她重生了。【别名】\n旧版本正文",
        "url": douyin_url,
        "created_at": 200,
    }
    assert (
        match_capture_item("douyin", "第一章：她重生了", [older, newer])
        == douyin_url
    )
    # 标题只比对首行前缀：正文里出现相同文字不算命中
    assert (
        match_capture_item(
            "douyin",
            "重来一世",
            [
                {
                    "title": "别的标题\n重来一世，她只想回家。",
                    "url": douyin_url,
                    "created_at": 1,
                }
            ],
        )
        is None
    )


def test_match_capture_item_rejects_foreign_and_scheduled_links():
    items = [
        {"title": "标题。", "url": "https://evil.example/note/1", "created_at": 9},
    ]
    assert match_capture_item("douyin", "标题", items) is None

    xhs = [
        {
            "title": "师父临死前说：回来的不是唐僧😱",
            "url": "https://www.xiaohongshu.com/explore/id?xsec_token=t",
            "created_at": 300,
        }
    ]
    assert (
        match_capture_item("xiaohongshu", "师父临死前说：回来的不是唐僧😱", xhs)
        == xhs[0]["url"]
    )
    assert match_capture_item("xiaohongshu", "不存在的标题", xhs) is None


def test_normalize_title_ignores_whitespace_and_trailing_punctuation():
    assert normalize_title("  第一章：她重生了。 ") == normalize_title("第一章：她重生了")


def test_merge_capture_items_dedupes_across_pages():
    first = {
        "title": "第一章：她重生了。",
        "url": "https://www.douyin.com/note/1",
        "created_at": 100,
    }
    second = dict(first)
    other = {
        "title": "别的标题",
        "url": "https://www.douyin.com/note/2",
        "created_at": 50,
    }
    assert merge_capture_items([first, second, other]) == [first, other]


def test_parse_worker_output_uses_last_json_line():
    text = '浏览器警告\n{"platform": "douyin", "items": [], "reason": "ok"}\n'
    parsed = parse_worker_output(text)
    assert parsed["platform"] == "douyin"
    with pytest.raises(ValueError):
        parse_worker_output("只有诊断信息")


def test_fetch_published_link_maps_missing_cookie_and_no_match(
    tmp_path, monkeypatch
):
    settings = _capture_settings(tmp_path)
    url = "https://www.douyin.com/note/7704983002492816678"
    monkeypatch.setattr(
        "app.services.publishing.link_capture._run_worker",
        lambda *args, **kwargs: {
            "platform": "douyin",
            "count": 1,
            "items": [
                {
                    "title": "第一章：她重生了。\n重来一世，她只想回家。",
                    "url": url,
                    "created_at": 1,
                }
            ],
            "reason": "",
        },
    )
    assert (
        fetch_published_link(settings, "douyin", "main", "第一章：她重生了") == url
    )

    monkeypatch.setattr(
        "app.services.publishing.link_capture._run_worker",
        lambda *args, **kwargs: {
            "platform": "douyin",
            "count": 1,
            "items": [
                {
                    "title": "别的标题\n正文",
                    "url": "https://www.douyin.com/note/2",
                    "created_at": 1,
                }
            ],
            "reason": "",
        },
    )
    with pytest.raises(AppError) as not_found:
        fetch_published_link(settings, "douyin", "main", "第一章：她重生了")
    assert not_found.value.code == "PUBLISH_LINK_NOT_FOUND"

    monkeypatch.setattr(
        "app.services.publishing.link_capture._run_worker",
        lambda *args, **kwargs: {
            "platform": "douyin",
            "count": 0,
            "items": [],
            "reason": "登录态已失效",
        },
    )
    with pytest.raises(AppError) as failed:
        fetch_published_link(settings, "douyin", "main", "第一章：她重生了")
    assert failed.value.code == "PUBLISH_LINK_CAPTURE_FAILED"

    bare = AppSettings(
        sau_project_dir=tmp_path / "empty-sau",
        sau_executable=tmp_path / "empty-sau" / ".venv" / "Scripts" / "sau.exe",
    )
    bare.sau_executable.parent.mkdir(parents=True)
    bare.sau_executable.write_text("", encoding="utf-8")
    (bare.sau_executable.parent / "python.exe").write_text("", encoding="utf-8")
    with pytest.raises(AppError) as unavailable:
        fetch_published_link(bare, "douyin", "main", "第一章：她重生了")
    assert unavailable.value.code == "PUBLISH_LINK_CAPTURE_UNAVAILABLE"


def test_fetch_job_link_fills_url_without_touching_status(
    client, monkeypatch, app
):
    monkeypatch.setattr(
        "app.routers.publishing.start_job_thread", lambda *args, **kwargs: None
    )
    story = _prepare_publishable(client)
    preview = _preview(client, story["id"]).json()
    created = client.post(
        "/api/publishing/jobs",
        json={
            "story_id": story["id"],
            "chapter_number": 1,
            "platform": "douyin",
            "account_id": _account(client)["id"],
            "schedule_at": preview["schedule_at"],
            "preview_hash": preview["payload_hash"],
            "confirm": True,
        },
    ).json()

    queued = client.post(
        f"/api/publishing/jobs/{created['id']}/fetch-link"
    )
    assert queued.status_code == 409
    assert queued.json()["code"] == "PUBLISH_LINK_STATUS_INVALID"

    with app.state.session_factory() as session:
        from app.models import PublishJob

        stored = session.get(PublishJob, created["id"])
        stored.status = "scheduled"
        session.commit()

    calls: dict[str, str] = {}

    def fake_capture(settings, *, platform, account_name, title):
        calls.update(
            platform=platform, account_name=account_name, title=title
        )
        return "https://www.douyin.com/note/7704983002492816678"

    monkeypatch.setattr(
        "app.routers.publishing.fetch_published_link", fake_capture
    )
    response = client.post(f"/api/publishing/jobs/{created['id']}/fetch-link")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["external_url"] == "https://www.douyin.com/note/7704983002492816678"
    assert body["status"] == "scheduled"
    assert calls == {
        "platform": "douyin",
        "account_name": _account(client)["account_name"],
        "title": "第一章：她重生了",
    }
