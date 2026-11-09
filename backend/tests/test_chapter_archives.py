"""章节封面 / 引导卡成品图归档与恢复测试。"""

from __future__ import annotations

from tests.test_prompt_snapshots import _prepare_story
from tests.test_uploads import PNG_BYTES


def test_chapter_cover_archive_and_restore(client):
    story = _prepare_story(client)
    url = (
        f"/api/stories/{story['id']}/breakdown/chapters/1/cover/image"
    )
    first = client.post(
        url, files={"file": ("cover.png", PNG_BYTES, "image/png")}
    )
    assert first.status_code == 200, first.text

    second = client.post(
        url, files={"file": ("cover2.png", PNG_BYTES, "image/png")}
    )
    assert second.status_code == 200, second.text

    archives = client.get(
        f"/api/stories/{story['id']}/breakdown/chapters/1/assets/cover/archives"
    )
    assert archives.status_code == 200, archives.text
    items = archives.json()
    assert len(items) == 1
    assert items[0]["filename"].startswith("chapter-1-cover-")

    restored = client.post(
        f"/api/stories/{story['id']}/breakdown/chapters/1/assets/cover/archives/{items[0]['filename']}/restore"
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["url"].startswith("/uploads/chapters/")

    after = client.get(
        f"/api/stories/{story['id']}/breakdown/chapters/1/assets/cover/archives"
    ).json()
    assert len(after) == 2
