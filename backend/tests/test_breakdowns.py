"""故事拆解结果接口测试。"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import StoryBreakdown, StoryPostConfig

STYLE_A = {"id": "style-a", "name": "唯美彩铅", "content": "韩式唯美彩铅手绘"}
STYLE_B = {"id": "style-b", "name": "日系赛璐璐", "content": "日系赛璐璐平涂"}


def _save_art_styles(client, styles, active_id=None):
    response = client.put(
        "/api/settings/art-styles",
        json={"styles": styles, "active_id": active_id},
    )
    assert response.status_code == 200, response.text


def _create_styled_story(client, style_id="style-a", content="第一次相亲的故事"):
    response = client.post(
        "/api/stories",
        json={
            "name": "拆解故事",
            "content": content,
            "art_style_id": style_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _page_payload(**overrides):
    payload = {
        "is_flashback": False,
        "story_content": "第一页：女老师提问 A8",
        "characters": ["我", "小八老师"],
        "character_review": "我：短发、休闲装；小八老师：鹅蛋脸、衬衫。",
        "scene": "高档餐厅，靠窗座位",
        "action_state": "小八老师倾身发问，我一脸困惑",
        "change_note": "抛出让男主困惑的问题",
        "narration_main": "如果一个女生开口问你有没有A8",
        "narration_highlight": "A8",
        "narration_sub": "第一次相亲，小八老师问出了这句话。",
        "dialogues": ["小八老师：你应该有A8吧？"],
        "shot_type": "特写",
        "image_prompt": "韩式唯美彩铅手绘，米色素描纸，餐厅特写……",
    }
    payload.update(overrides)
    return payload


def _mapping_items(numbers, excluded=()):
    return [
        {
            "page_number": number,
            "source_text": f"第{number}段原文",
            "summary": f"第{number}段",
            "paragraph": f"第{number}段",
            "part": "1/1",
            "excluded": number in excluded,
        }
        for number in numbers
    ]


def _chapter_payload(number, mapping_pages, title=None):
    return {
        "chapter_number": number,
        "title": title or f"第{number}章",
        "mapping_page_numbers": mapping_pages,
        "cover": {
            "label": f"第{number}章 · 标题",
            "narration_main": "这一次，她只想回家",
            "narration_highlight": "回家",
            "narration_sub": "重来一世，她只想回家见奶奶。",
            "image_prompt": "",
        },
        "guide": {
            "text": "关注我，看更多重生爽文",
            "sub_text": "下一章：祝卿当场摔杯",
            "image_prompt": "",
        },
    }


def _patch_breakdown(client, story_id, **payload):
    return client.patch(f"/api/stories/{story_id}/breakdown", json=payload)


def _put_page(client, story_id, page_number, **overrides):
    return client.put(
        f"/api/stories/{story_id}/breakdown/pages/{page_number}",
        json=_page_payload(**overrides),
    )


def _prepare(client):
    """准备画风、带画风的故事以及拆解头部信息。"""
    _save_art_styles(client, [STYLE_A, STYLE_B], active_id="style-a")
    story = _create_styled_story(client)
    response = _patch_breakdown(
        client,
        story["id"],
        optimized_content="优化后的完整故事……",
        characters=[
            {"name": "我", "role": "男主", "appearance": "短发，休闲装。"},
            {"name": "小八老师", "role": "女主", "appearance": "鹅蛋脸，衬衫。"},
        ],
    )
    assert response.status_code == 200, response.text
    return story, response.json()


def _count(app, model) -> int:
    with app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_get_breakdown_missing_returns_null(client, story):
    response = client.get(f"/api/stories/{story['id']}/breakdown")
    assert response.status_code == 200
    assert response.json() is None


def test_breakdown_story_not_found(client):
    assert (
        client.get("/api/stories/9999/breakdown").json()["code"]
        == "STORY_NOT_FOUND"
    )
    response = _patch_breakdown(client, 9999, optimized_content="x")
    assert response.status_code == 404
    assert response.json()["code"] == "STORY_NOT_FOUND"


def test_patch_requires_art_style(client, story):
    """没有有效画风时不能创建拆解结果。"""
    response = _patch_breakdown(client, story["id"], optimized_content="优化文")
    assert response.status_code == 422
    assert response.json()["code"] == "ART_STYLE_REQUIRED"


def test_patch_creates_and_snapshots_style(client):
    story, breakdown = _prepare(client)

    assert breakdown["story_id"] == story["id"]
    assert breakdown["optimized_content"] == "优化后的完整故事……"
    assert [card["name"] for card in breakdown["characters"]] == [
        "我",
        "小八老师",
    ]
    assert breakdown["art_style_id"] == "style-a"
    assert breakdown["art_style_name"] == "唯美彩铅"
    assert breakdown["art_style_content"] == "韩式唯美彩铅手绘"
    assert breakdown["is_content_stale"] is False
    assert breakdown["is_art_style_stale"] is False
    assert breakdown["pages"] == []
    assert breakdown["created_at"].endswith("Z")


def test_patch_partial_update_keeps_fields(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    response = _patch_breakdown(
        client, story_id, group_photo_prompt="人物合影提示词……"
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["group_photo_prompt"] == "人物合影提示词……"
    # 未提供的字段保持不变
    assert data["optimized_content"] == "优化后的完整故事……"
    assert len(data["characters"]) == 2


def test_patch_mapping_round_trip(client):
    """分镜对照表可单独写入，且不影响优化文与角色卡。"""
    story, _ = _prepare(client)
    story_id = story["id"]
    mapping = [
        {
            "page_number": 1,
            "source_text": "第一段原文",
            "summary": "第一段",
            "paragraph": "第1段",
            "part": "1/1",
        },
        {
            "page_number": 2,
            "source_text": "第二段原文",
            "summary": "第二段",
            "paragraph": "第2段",
            "part": "1/1",
        },
    ]

    response = _patch_breakdown(client, story_id, mapping=mapping)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mapping"] == [
        {**item, "excluded": False} for item in mapping
    ]
    assert data["optimized_content"] == "优化后的完整故事……"
    assert len(data["characters"]) == 2
    assert data["pages"] == []


def test_patch_chapters_round_trip(client):
    """章节可按对照顺序写入，并返回封面 / 引导卡占位信息。"""
    story, _ = _prepare(client)
    story_id = story["id"]
    mapping = _mapping_items([1, 2, 3, 4])
    assert _patch_breakdown(client, story_id, mapping=mapping).status_code == 200

    chapters = [
        _chapter_payload(1, [1, 2], "第一章 重来"),
        _chapter_payload(2, [3, 4], "第二章 真相"),
    ]
    response = _patch_breakdown(client, story_id, chapters=chapters)
    assert response.status_code == 200, response.text
    data = response.json()
    assert [item["chapter_number"] for item in data["chapters"]] == [1, 2]
    assert data["chapters"][0]["title"] == "第一章 重来"
    assert data["chapters"][0]["cover"]["narration_main"] == (
        "这一次，她只想回家"
    )
    assert data["chapters"][0]["cover"]["image_url"] is None
    assert data["chapters"][0]["guide"]["image_url"] is None
    # 章节不影响已有对照表与角色卡
    assert len(data["mapping"]) == 4
    assert len(data["characters"]) == 2


def test_chapters_must_cover_active_mapping_in_order(client):
    story, _ = _prepare(client)
    story_id = story["id"]
    assert (
        _patch_breakdown(
            client, story_id, mapping=_mapping_items([1, 2, 3, 4])
        ).status_code
        == 200
    )

    # 漏段
    response = _patch_breakdown(
        client,
        story_id,
        chapters=[_chapter_payload(1, [1, 2]), _chapter_payload(2, [3])],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "CHAPTER_COVERAGE_INVALID"

    # 跳段 / 倒序
    response = _patch_breakdown(
        client,
        story_id,
        chapters=[_chapter_payload(1, [1, 2]), _chapter_payload(2, [4, 3])],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "CHAPTER_COVERAGE_INVALID"

    # 章节号必须连续
    response = _patch_breakdown(
        client,
        story_id,
        chapters=[_chapter_payload(1, [1, 2]), _chapter_payload(3, [3, 4])],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "CHAPTER_NUMBER_INVALID"


def test_chapters_skip_excluded_mapping(client):
    story, _ = _prepare(client)
    story_id = story["id"]
    assert (
        _patch_breakdown(
            client,
            story_id,
            mapping=_mapping_items([1, 2, 3], excluded={2}),
        ).status_code
        == 200
    )

    # 弃用段不能分入章节
    response = _patch_breakdown(
        client,
        story_id,
        chapters=[_chapter_payload(1, [1]), _chapter_payload(2, [2, 3])],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "CHAPTER_USES_EXCLUDED_PAGE"

    # 跳过弃用段后必须完整覆盖剩余段
    response = _patch_breakdown(
        client,
        story_id,
        chapters=[_chapter_payload(1, [1]), _chapter_payload(2, [3])],
    )
    assert response.status_code == 200, response.text


def test_mapping_change_requires_chapter_update(client):
    """对照表变了但章节未同步时拒绝写入，避免章节漏段/错位。"""
    story, _ = _prepare(client)
    story_id = story["id"]
    assert (
        _patch_breakdown(
            client, story_id, mapping=_mapping_items([1, 2, 3])
        ).status_code
        == 200
    )
    assert (
        _patch_breakdown(
            client,
            story_id,
            chapters=[_chapter_payload(1, [1, 2]), _chapter_payload(2, [3])],
        ).status_code
        == 200
    )

    response = _patch_breakdown(
        client, story_id, mapping=_mapping_items([1, 2, 3, 4])
    )
    assert response.status_code == 422
    assert response.json()["code"] == "CHAPTER_COVERAGE_INVALID"


def test_page_chapter_fields_round_trip_and_validation(client):
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

    response = _put_page(
        client,
        story_id,
        1,
        mapping_page_number=1,
        chapter_number=1,
        chapter_page_number=1,
    )
    assert response.status_code == 200, response.text
    assert response.json()["chapter_number"] == 1
    assert response.json()["chapter_page_number"] == 1
    assert response.json()["display_page_number"] == 1

    # 章内页与来源对照段必须匹配（第 1 章第 2 页应对应对照第 2 段）
    response = _put_page(
        client,
        story_id,
        2,
        mapping_page_number=3,
        chapter_number=1,
        chapter_page_number=2,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "CHAPTER_PAGE_MAPPING_MISMATCH"

    # 全局页码必须由章节位置唯一确定（第 2 章第 2 页应为全局第 4 页）
    response = _put_page(
        client,
        story_id,
        5,
        mapping_page_number=4,
        chapter_number=2,
        chapter_page_number=2,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "CHAPTER_PAGE_NUMBER_MISMATCH"

    assert (
        _put_page(
            client,
            story_id,
            2,
            mapping_page_number=2,
            chapter_number=1,
            chapter_page_number=2,
        ).status_code
        == 200
    )
    response = _put_page(
        client,
        story_id,
        3,
        mapping_page_number=3,
        chapter_number=2,
        chapter_page_number=1,
    )
    assert response.status_code == 200
    assert response.json()["display_page_number"] == 1

    breakdown = client.get(f"/api/stories/{story_id}/breakdown").json()
    page3 = next(
        item for item in breakdown["pages"] if item["page_number"] == 3
    )
    assert page3["chapter_page_number"] == 1
    assert page3["display_page_number"] == 1
    assert (
        _put_page(
            client,
            story_id,
            4,
            mapping_page_number=4,
            chapter_number=2,
            chapter_page_number=2,
        ).status_code
        == 200
    )

    # 只改章节标题 / 封面文字时，已有页面不受影响，允许保存
    response = _patch_breakdown(
        client,
        story_id,
        chapters=[
            _chapter_payload(1, [1, 2], title="新的第一章"),
            _chapter_payload(2, [3, 4]),
        ],
    )
    assert response.status_code == 200, response.text

    # 章节结构变化会改变页面归属，已有正文页时拒绝
    response = _patch_breakdown(
        client,
        story_id,
        chapters=[
            _chapter_payload(1, [1, 2, 3]),
            _chapter_payload(2, [4]),
        ],
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CHAPTERS_LOCKED_BY_PAGES"

    # 对照表变化同样会改变来源，已有正文页时拒绝
    response = _patch_breakdown(
        client,
        story_id,
        mapping=_mapping_items([1, 2, 3, 4], excluded=(4,)),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "MAPPING_LOCKED_BY_PAGES"

    # 编辑时不带章节字段，保留原值
    response = _put_page(client, story_id, 1, narration_main="改写后的主旁白")
    assert response.status_code == 200
    assert response.json()["chapter_number"] == 1
    assert response.json()["chapter_page_number"] == 1

    # 章节字段必须成对出现（新页，没有旧值可继承）
    response = _put_page(client, story_id, 6, chapter_number=1)
    assert response.status_code == 422
    assert response.json()["code"] == "CHAPTER_PAGE_INCOMPLETE"


def test_page_prompt_number_must_match_display_page(client):
    """正文页提示词里的页码必须是章内页码，不能写全局页码或对照段号。"""
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

    wrong = _put_page(
        client,
        story_id,
        3,
        mapping_page_number=3,
        chapter_number=2,
        chapter_page_number=1,
        image_prompt=(
            "【画风】测试画风\n"
            "【页码】画面左下角放置「第17页」，不遮挡人物。\n"
            "【负面提示词】测试。"
        ),
    )
    assert wrong.status_code == 422
    assert wrong.json()["code"] == "PROMPT_PAGE_MISMATCH"

    ok = _put_page(
        client,
        story_id,
        3,
        mapping_page_number=3,
        chapter_number=2,
        chapter_page_number=1,
        image_prompt=(
            "【画风】测试画风\n"
            "【页码】画面左下角放置「第1页」，不遮挡人物。\n"
            "【负面提示词】测试。"
        ),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["display_page_number"] == 1

    # 旧数据没有【页码】分块时保持兼容，不阻断编辑
    legacy = _put_page(
        client,
        story_id,
        3,
        mapping_page_number=3,
        chapter_number=2,
        chapter_page_number=1,
        image_prompt="旧提示词，没有页码分块。",
    )
    assert legacy.status_code == 200, legacy.text


def test_patch_empty_payload_rejected(client):
    story, _ = _prepare(client)
    response = client.patch(
        f"/api/stories/{story['id']}/breakdown", json={}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_breakdown_stale_flags(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    # 修改原文后提示内容过期
    updated = client.put(
        f"/api/stories/{story_id}",
        json={
            "name": "拆解故事",
            "content": "新的原文内容",
            "cover_filename": None,
            "art_style_id": "style-a",
        },
    )
    assert updated.status_code == 200, updated.text
    got = client.get(f"/api/stories/{story_id}/breakdown").json()
    assert got["is_content_stale"] is True
    assert got["is_art_style_stale"] is False

    # 更换画风后提示画风过期
    updated = client.put(
        f"/api/stories/{story_id}",
        json={
            "name": "拆解故事",
            "content": "新的原文内容",
            "cover_filename": None,
            "art_style_id": "style-b",
        },
    )
    assert updated.status_code == 200, updated.text
    got = client.get(f"/api/stories/{story_id}/breakdown").json()
    assert got["is_art_style_stale"] is True


def test_patch_refreshes_style_snapshot_on_rerun(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    client.put(
        f"/api/stories/{story_id}",
        json={
            "name": "拆解故事",
            "content": "第一次相亲的故事",
            "cover_filename": None,
            "art_style_id": "style-b",
        },
    )
    response = _patch_breakdown(client, story_id, group_photo_prompt="新合影")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["art_style_id"] == "style-b"
    assert data["art_style_name"] == "日系赛璐璐"
    assert data["is_art_style_stale"] is False


def test_dangling_style_still_allows_editing(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    # 删除画风后，既有拆解仍可编辑，但会标记画风过期
    _save_art_styles(client, [], active_id=None)
    response = _patch_breakdown(client, story_id, group_photo_prompt="继续编辑")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["art_style_id"] == "style-a"
    assert data["is_art_style_stale"] is True


def test_page_upsert_sorted_and_replaced(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    assert _put_page(client, story_id, 2).status_code == 200
    assert _put_page(client, story_id, 1).status_code == 200

    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert [page["page_number"] for page in pages] == [1, 2]

    response = _put_page(
        client, story_id, 1, narration_main="改写后的首图提问"
    )
    assert response.status_code == 200
    assert response.json()["page_number"] == 1

    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert len(pages) == 2
    assert pages[0]["narration_main"] == "改写后的首图提问"


def test_page_mapping_page_number_round_trip(client):
    """脚本页记录来源对照段；编辑时未传则保留，且一段不能关联两页。"""
    story, _ = _prepare(client)
    story_id = story["id"]
    mapping = [
        {
            "page_number": 1,
            "source_text": "第一段原文",
            "summary": "第一段",
            "paragraph": "第1段",
            "part": "1/1",
        },
        {
            "page_number": 2,
            "source_text": "第二段原文",
            "summary": "第二段",
            "paragraph": "第2段",
            "part": "1/1",
        },
    ]
    assert _patch_breakdown(client, story_id, mapping=mapping).status_code == 200

    response = _put_page(client, story_id, 1, mapping_page_number=2)
    assert response.status_code == 200, response.text
    assert response.json()["mapping_page_number"] == 2

    # 编辑页面时不携带来源段，沿用原关联
    response = _put_page(client, story_id, 1, narration_main="改写后的主旁白")
    assert response.status_code == 200, response.text
    assert response.json()["mapping_page_number"] == 2

    # 同一对照段不能关联到两个脚本页
    response = _put_page(client, story_id, 2, mapping_page_number=2)
    assert response.status_code == 422
    assert response.json()["code"] == "MAPPING_PAGE_DUPLICATED"

    # 对照表里不存在的段不能作为来源
    response = _put_page(client, story_id, 2, mapping_page_number=99)
    assert response.status_code == 422
    assert response.json()["code"] == "MAPPING_PAGE_NOT_FOUND"


def test_page_role_saved_and_optional(client):
    """页面作用写回后原样返回；未传时默认为空字符串（兼容旧拆解）。"""
    story, _ = _prepare(client)
    story_id = story["id"]

    response = _put_page(client, story_id, 1, page_role="  钩子封面  ")
    assert response.status_code == 200
    assert response.json()["page_role"] == "钩子封面"

    # 旧数据或未标注的页面不传该字段，仍可正常写入并读回空字符串
    response = _put_page(client, story_id, 2)
    assert response.status_code == 200
    assert response.json()["page_role"] == ""

    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert [page["page_role"] for page in pages] == ["钩子封面", ""]

    # 超过长度限制会被拒绝，避免写入异常值
    assert _put_page(client, story_id, 3, page_role="x" * 21).status_code == 422


def test_camera_angle_saved_and_optional(client):
    """机位方位写回后原样返回；未传时默认为空字符串（兼容旧拆解数据）。"""
    story, _ = _prepare(client)
    story_id = story["id"]

    response = _put_page(client, story_id, 1, camera_angle="  过肩视角  ")
    assert response.status_code == 200
    assert response.json()["camera_angle"] == "过肩视角"

    # 旧数据未包含该字段，仍可正常写入并读回空字符串
    response = _put_page(client, story_id, 2)
    assert response.status_code == 200
    assert response.json()["camera_angle"] == ""

    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert [page["camera_angle"] for page in pages] == ["过肩视角", ""]

    # 超过长度限制会被拒绝
    assert _put_page(client, story_id, 3, camera_angle="x" * 51).status_code == 422


def test_page_requires_breakdown(client):
    _save_art_styles(client, [STYLE_A])
    story = _create_styled_story(client)

    response = _put_page(client, story["id"], 1)
    assert response.status_code == 404
    assert response.json()["code"] == "BREAKDOWN_NOT_FOUND"


def test_page_validation(client):
    story, _ = _prepare(client)
    story_id = story["id"]

    invalid_shot = _put_page(client, story_id, 1, shot_type="近景")
    assert invalid_shot.status_code == 422

    empty_prompt = _put_page(client, story_id, 1, image_prompt="   ")
    assert empty_prompt.status_code == 422

    too_many_dialogues = _put_page(
        client, story_id, 1, dialogues=["a", "b", "c"]
    )
    assert too_many_dialogues.status_code == 422

    assert (
        client.put(
            f"/api/stories/{story_id}/breakdown/pages/0",
            json=_page_payload(),
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/stories/{story_id}/breakdown/pages/201",
            json=_page_payload(),
        ).status_code
        == 422
    )


def test_delete_page_and_clear_pages(client):
    story, _ = _prepare(client)
    story_id = story["id"]
    for number in (1, 2, 3):
        assert _put_page(client, story_id, number).status_code == 200

    assert (
        client.delete(
            f"/api/stories/{story_id}/breakdown/pages/2"
        ).status_code
        == 204
    )
    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert [page["page_number"] for page in pages] == [1, 3]

    # 重复删除同一页码保持幂等
    assert (
        client.delete(
            f"/api/stories/{story_id}/breakdown/pages/2"
        ).status_code
        == 204
    )

    assert (
        client.delete(
            f"/api/stories/{story_id}/breakdown/pages"
        ).status_code
        == 204
    )
    pages = client.get(f"/api/stories/{story_id}/breakdown").json()["pages"]
    assert pages == []


def test_delete_breakdown_is_idempotent(client):
    story, _ = _prepare(client)
    story_id = story["id"]
    _put_page(client, story_id, 1)

    assert (
        client.delete(f"/api/stories/{story_id}/breakdown").status_code == 204
    )
    assert client.get(f"/api/stories/{story_id}/breakdown").json() is None
    assert (
        client.delete(f"/api/stories/{story_id}/breakdown").status_code == 204
    )


def test_delete_story_cascades_breakdown_and_post_config(client, app):
    story, _ = _prepare(client)
    story_id = story["id"]
    _put_page(client, story_id, 1)
    response = client.put(
        f"/api/stories/{story_id}/post-config",
        json={"title": "标题", "content": "正文"},
    )
    assert response.status_code == 200

    assert _count(app, StoryBreakdown) == 1
    assert _count(app, StoryPostConfig) == 1

    assert client.delete(f"/api/stories/{story_id}").status_code == 204
    assert _count(app, StoryBreakdown) == 0
    assert _count(app, StoryPostConfig) == 0


def test_delete_story_blocked_by_posts_keeps_breakdown(client, app):
    story, _ = _prepare(client)
    story_id = story["id"]
    post = client.post(
        "/api/posts",
        json={"story_id": story_id, "title": "标题", "content": "正文"},
    )
    assert post.status_code == 201

    response = client.delete(f"/api/stories/{story_id}")
    assert response.status_code == 409
    assert response.json()["code"] == "STORY_HAS_POSTS"
    assert _count(app, StoryBreakdown) == 1
