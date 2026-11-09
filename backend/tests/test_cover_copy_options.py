"""章节封面文案方案接口测试（DeepSeek 全部 mock）。"""

from __future__ import annotations

from tests.conftest import make_response
from tests.test_breakdowns import (
    _chapter_payload,
    _mapping_items,
    _patch_breakdown,
    _prepare,
)


def _cover_options():
    return [
        {
            "style": "禁忌反转",
            "feature": "用辞职原因直接点出办公室恋情，信息前置，冲突最强。",
            "hook_source": "开头闪前",
            "visual_hint": "辞职信放在办公桌上，女主推过去，男主按住信纸抬眼看她。",
            "visual_content": "3:4竖版封面。{{我}} 坐在办公桌前，把辞职信推到 {{小八老师}} 面前；{{小八老师}} 按住信纸抬眼看她；桌上有一封辞职信和一支笔；办公室夜景，窗外城市灯光，背景不纯黑；机位为从桌沿上方略俯的近景。",
            "narration_main": "辞职因为办公室恋情",
            "narration_highlight": "办公室恋情",
            "narration_sub": "他追问我辞职原因，我说：因为你禁止办公室恋情。",
            "recommended": True,
            "recommend_reason": "和本章发文标题同一个钩子，点击欲最强。",
        },
        {
            "style": "信息差",
            "feature": "先写他记得我，再把偏爱翻成好用，制造反差。",
            "hook_source": "中段反转",
            "visual_hint": "深夜办公室，女主被身后的上司惊到，咖啡杯在前景。",
            "visual_content": "3:4竖版封面。{{我}} 在深夜办公室被身后的 {{小八老师}} 惊到，肩膀一僵；前景是一只被吸管戳穿的冰咖啡杯；电脑屏幕冷光、百叶窗和零散工位灯保留，背景不纯黑；机位为略低角度过肩近景。",
            "narration_main": "他记得我，因为我好用",
            "narration_highlight": "好用",
            "narration_sub": "他当众记住我的名字，我却知道这不是偏爱。",
            "recommended": False,
            "recommend_reason": "",
        },
        {
            "style": "代价前置",
            "feature": "把辞职代价放在最前面，适合情绪向读者。",
            "hook_source": "结尾反转",
            "visual_hint": "女主抱着纸箱站在公司门口，回头看向办公室灯光。",
            "visual_content": "3:4竖版封面。{{我}} 抱着纸箱站在公司门口，回头看向亮着灯的办公室；夜色里公司玻璃门和路灯保留，背景不纯黑；机位为正面中景，人物偏画面右侧，左侧留白给文字。",
            "narration_main": "我为他辞了职",
            "narration_highlight": "辞了职",
            "narration_sub": "暗恋前上司，我辞了职；重逢后他追问我原因。",
            "recommended": False,
            "recommend_reason": "",
        },
    ]


def test_cover_copy_options_use_post_title_and_chapter_text(
    client, configure_key, mock_deepseek
):
    story, _ = _prepare(client)
    story_id = story["id"]
    assert (
        _patch_breakdown(
            client, story_id, mapping=_mapping_items([1, 2])
        ).status_code
        == 200
    )
    assert (
        _patch_breakdown(
            client,
            story_id,
            chapters=[_chapter_payload(1, [1, 2], title="冷面上司，偏偏记得我")],
        ).status_code
        == 200
    )
    post_config = client.put(
        f"/api/stories/{story_id}/post-config?chapter=1",
        json={
            "title": "我辞职原因：公司禁止办公室恋情",
            "content": "辞职原因能有多离谱？我：因为你禁止办公室恋情。",
        },
    )
    assert post_config.status_code == 200, post_config.text

    mock_deepseek["response"] = make_response(options=_cover_options())
    response = client.post(
        f"/api/stories/{story_id}/breakdown/chapters/1/cover/copy-options",
        json={
            "chapter_title": "冷面上司，偏偏记得我",
            "cover_label": "第1章 · 冷面上司，偏偏记得我",
            "cover_main": "他偏偏记得我",
            "cover_highlight": "偏偏",
            "cover_sub": "我却当众被他记住。",
            "direction": "更强调辞职和办公室恋情",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["post_title"] == "我辞职原因：公司禁止办公室恋情"
    assert len(data["options"]) == 3
    assert data["options"][0]["narration_main"] == "辞职因为办公室恋情"
    assert data["options"][0]["recommended"] is True
    assert sum(option["recommended"] for option in data["options"]) == 1
    assert data["options"][0]["image_prompt"]
    assert "辞职因为办公室恋情" in data["options"][0]["image_prompt"]

    _, messages = mock_deepseek["calls"][0]
    system_prompt = messages[0]["content"]
    assert "我辞职原因：公司禁止办公室恋情" in system_prompt
    assert "第1段原文" in system_prompt
    assert "第 1 章必须围绕故事的核心关系/禁忌/代价" in system_prompt
    assert messages[1]["content"] == "更强调辞职和办公室恋情"


def test_cover_copy_options_reject_invalid_lengths(
    client, configure_key, mock_deepseek
):
    story, _ = _prepare(client)
    story_id = story["id"]
    assert (
        _patch_breakdown(
            client, story_id, mapping=_mapping_items([1])
        ).status_code
        == 200
    )
    assert (
        _patch_breakdown(
            client, story_id, chapters=[_chapter_payload(1, [1])]
        ).status_code
        == 200
    )
    bad = _cover_options()
    bad[0]["narration_main"] = "这个主标题实在太长了超过十二个字"
    mock_deepseek["response"] = [make_response(options=bad), make_response(options=bad)]
    response = client.post(
        f"/api/stories/{story_id}/breakdown/chapters/1/cover/copy-options",
        json={},
    )
    assert response.status_code == 502
    assert response.json()["code"] == "COVER_COPY_INVALID"
