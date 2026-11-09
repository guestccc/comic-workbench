"""敏感词词库、扫描与替换。"""

from __future__ import annotations


def _set_words(client, words):
    response = client.put("/api/settings/sensitive-words", json={"words": words})
    assert response.status_code == 200, response.text
    return response.json()["words"]


def test_default_sensitive_words_available(client):
    defaults = client.get("/api/settings/sensitive-words/defaults").json()["words"]
    assert len(defaults) >= 100
    words = [item["word"] for item in defaults]
    assert len(words) == len(set(words))
    assert "全网最低" in words
    assert "加微信" in words
    assert "第一" in words
    assert next(item for item in defaults if item["word"] == "第一")["enabled"] is False


def test_sensitive_word_dictionary_roundtrip(client):
    initial = client.get("/api/settings/sensitive-words").json()["words"]
    assert len(initial) >= 100

    saved = _set_words(
        client,
        [
            {
                "word": "敏感",
                "replacement": "稳妥",
                "category": "测试",
                "enabled": True,
            },
            {
                "word": "敏感词",
                "replacement": "安全词",
                "category": "测试",
                "enabled": True,
            },
        ],
    )
    assert [item["word"] for item in saved] == ["敏感", "敏感词"]
    assert client.get("/api/settings/sensitive-words").json()["words"] == saved

    duplicate = client.put(
        "/api/settings/sensitive-words",
        json={"words": [{"word": "敏感"}, {"word": "敏感"}]},
    )
    assert duplicate.status_code == 422
    assert duplicate.json()["code"] == "SENSITIVE_WORD_DUPLICATE"


def test_explicit_empty_dictionary_stays_empty(client):
    """用户明确保存空词库后，不再自动回填默认包。"""
    _set_words(client, [])
    assert client.get("/api/settings/sensitive-words").json()["words"] == []


def test_scan_uses_longest_match_and_reports_offsets(client):
    _set_words(
        client,
        [
            {"word": "敏感", "replacement": "稳妥"},
            {"word": "敏感词", "replacement": "安全词"},
        ],
    )
    text = "这是敏感词和敏感内容"
    response = client.post("/api/sensitive-words/scan", json={"text": text})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2
    assert data["counts"] == {"敏感词": 1, "敏感": 1}
    assert [match["word"] for match in data["matches"]] == ["敏感词", "敏感"]
    assert data["matches"][0]["start"] == 2
    assert data["matches"][0]["end"] == 5
    assert data["dictionary_version"]


def test_apply_replaces_selected_words_from_end(client):
    _set_words(
        client,
        [
            {"word": "敏感", "replacement": "稳妥"},
            {"word": "敏感词", "replacement": "安全词"},
        ],
    )
    response = client.post(
        "/api/sensitive-words/apply",
        json={
            "text": "这是敏感词和敏感内容",
            "items": [
                {"word": "敏感", "replacement": "X"},
                {"word": "敏感词", "replacement": "Y"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["content"] == "这是Y和X内容"
    assert data["items"] == [
        {"word": "敏感", "replacement": "X", "count": 1},
        {"word": "敏感词", "replacement": "Y", "count": 1},
    ]
    edit = data["sensitive_edit"]
    assert edit["original_content"] == "这是敏感词和敏感内容"
    assert edit["result_content"] == data["content"]
    assert edit["dictionary_version"] == data["dictionary_version"]


def test_story_apply_updates_content_and_audit(client):
    _set_words(client, [{"word": "敏感", "replacement": "稳妥"}])
    created = client.post(
        "/api/stories",
        json={"name": "测试", "content": "这是敏感内容"},
    )
    assert created.status_code == 201, created.text
    story = created.json()
    assert story["sensitive_edit"] is None

    applied = client.post(
        f"/api/stories/{story['id']}/sensitive-words/apply",
        json={"items": [{"word": "敏感", "replacement": "稳妥"}]},
    )
    assert applied.status_code == 200, applied.text
    data = applied.json()
    assert data["content"] == "这是稳妥内容"
    assert data["sensitive_edit"]["original_content"] == "这是敏感内容"
    assert data["sensitive_edit"]["result_content"] == "这是稳妥内容"
    assert data["sensitive_edit"]["items"] == [
        {"word": "敏感", "replacement": "稳妥", "count": 1}
    ]

    # 普通更新不带 sensitive_edit 时保留审计
    updated = client.put(
        f"/api/stories/{story['id']}",
        json={
            "name": "测试",
            "content": "这是稳妥内容",
            "cover_filename": None,
            "art_style_id": None,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["sensitive_edit"] is not None

    # 明确传 null 才清除
    cleared = client.put(
        f"/api/stories/{story['id']}",
        json={
            "name": "测试",
            "content": "这是稳妥内容",
            "cover_filename": None,
            "art_style_id": None,
            "sensitive_edit": None,
        },
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["sensitive_edit"] is None
