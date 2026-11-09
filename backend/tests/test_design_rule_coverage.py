"""设计规则落实检测任务：范围为空时也能创建并完成运行。"""

from __future__ import annotations

import time

from tests.test_design_feedbacks import _create_feedback, _create_styled_story
from tests.test_design_rules import _create_rule


def test_coverage_run_with_empty_scope(client):
    story = _create_styled_story(client)
    feedback = _create_feedback(client)
    rule = _create_rule(
        client,
        feedback["id"],
        target="cover",
        scope_type="story",
        story_id=story["id"],
        chapter_numbers=[],
        page_numbers=[],
    )

    started = client.post(f"/api/design-rules/{rule['id']}/coverage-runs")
    assert started.status_code == 202, started.text
    run = started.json()
    assert run["status"] in ("queued", "running", "succeeded")
    assert run["rule_id"] == rule["id"]

    deadline = time.time() + 3
    while time.time() < deadline:
        current = client.get(f"/api/design-rule-coverage-runs/{run['id']}").json()
        if current["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert current["status"] == "succeeded", current
    assert current["total"] == 0
    assert current["items"] == []

    latest = client.get(
        f"/api/design-rules/{rule['id']}/coverage-runs/latest"
    )
    assert latest.status_code == 200, latest.text
    assert latest.json()["id"] == run["id"]
