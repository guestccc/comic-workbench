"""按需抓取创作中心作品列表，输出最小字段 JSON。

必须用 `sau` 虚拟环境的解释器运行（patchright 装在那里），例如：

    .venv\\Scripts\\python.exe link_capture_worker.py --platform douyin --cookie ...

只读列表接口，不点击发布 / 编辑 / 删除；标准输出最后一行是结果 JSON，
其余诊断信息一律写 stderr，避免污染结果。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from patchright.async_api import async_playwright

TARGETS: dict[str, dict[str, str]] = {
    "douyin": {
        "page": "https://creator.douyin.com/creator-micro/content/manage",
        "api_marker": "/janus/douyin/creator/pc/work_list",
    },
    "xiaohongshu": {
        "page": "https://creator.xiaohongshu.com/new/note-manager",
        "api_marker": "/api/galaxy/v2/creator/note/user/posted",
    },
}

LIST_WAIT_SECONDS = 45
# 滚动加载更多的上限：约 10 页 / 120 条，避免作品很多时无限翻页。
MAX_SCROLL_ROUNDS = 10
MAX_CAPTURE_ITEMS = 120
SCROLL_PAUSE_MS = 1800

# 两个平台的列表都放在内层滚动容器里，滚动窗口本身不会触发加载。
_SCROLL_SCRIPT = """
() => {
    let moved = false;
    for (const element of document.querySelectorAll('*')) {
        if (element.scrollHeight > element.clientHeight + 100 && element.clientHeight > 100) {
            const before = element.scrollTop;
            element.scrollTop = element.scrollHeight;
            if (element.scrollTop !== before) moved = true;
        }
    }
    return moved;
}
"""


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _raw_items(platform: str, body: dict[str, Any]) -> list[Any]:
    if platform == "douyin":
        return body.get("aweme_list") or []
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    return (data or {}).get("notes") or []


def _douyin_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in _raw_items("douyin", body):
        if not isinstance(raw, dict):
            continue
        status = raw.get("status") if isinstance(raw.get("status"), dict) else {}
        if status.get("is_delete") or status.get("in_reviewing") or status.get("is_private"):
            continue
        aweme_id = str(raw.get("aweme_id") or "").strip()
        if not aweme_id:
            continue
        share_url = str(raw.get("share_url") or "")
        kind = "note" if "/note/" in share_url else "video"
        items.append(
            {
                "title": str(raw.get("desc") or ""),
                "url": f"https://www.douyin.com/{kind}/{aweme_id}",
                "created_at": int(raw.get("create_time") or 0),
            }
        )
    return items


def _xhs_created_at(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(datetime.strptime(text, "%Y-%m-%d %H:%M").timestamp())
    except ValueError:
        return 0


def _xhs_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    notes = _raw_items("xiaohongshu", body)
    items: list[dict[str, Any]] = []
    for raw in notes:
        if not isinstance(raw, dict):
            continue
        # tab_status 1 = 已发布，4 = 定时未生效；有 schedule_post_time 也视为未发布。
        if int(raw.get("tab_status") or 0) != 1:
            continue
        if int(raw.get("schedule_post_time") or 0) > 0:
            continue
        note_id = str(raw.get("id") or "").strip()
        if not note_id:
            continue
        url = f"https://www.xiaohongshu.com/explore/{note_id}"
        token = str(raw.get("xsec_token") or "").strip()
        if token:
            url += f"?xsec_token={quote(token, safe='')}&xsec_source=pc_user"
        items.append(
            {
                "title": str(raw.get("display_title") or ""),
                "url": url,
                "created_at": _xhs_created_at(raw.get("time")),
            }
        )
    return items


def _extract(platform: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    if platform == "douyin":
        return _douyin_items(body)
    return _xhs_items(body)


def _captured_count(platform: str, bodies: list[dict[str, Any]]) -> int:
    return sum(len(_raw_items(platform, body)) for body in bodies)


async def _scroll_through_pages(
    page, bodies: list[dict[str, Any]], platform: str
) -> None:
    """滚动内层列表容器触发加载更多，直到列表到底或达到上限。"""
    idle_rounds = 0
    for _ in range(MAX_SCROLL_ROUNDS):
        if _captured_count(platform, bodies) >= MAX_CAPTURE_ITEMS:
            return
        before = len(bodies)
        await page.evaluate(_SCROLL_SCRIPT)
        await page.wait_for_timeout(SCROLL_PAUSE_MS)
        if len(bodies) > before:
            idle_rounds = 0
            continue
        # 连续两轮没有新请求，认为已经到底或加载失败。
        idle_rounds += 1
        if idle_rounds >= 2:
            return


async def capture(platform: str, cookie: Path) -> dict[str, Any]:
    target = TARGETS[platform]
    bodies: list[dict[str, Any]] = []
    tasks: set[asyncio.Task] = set()
    final_url = ""

    async def on_response(response) -> None:
        if target["api_marker"] not in response.url:
            return
        if "json" not in (response.headers.get("content-type") or ""):
            return
        try:
            data = await response.json()
        except Exception:  # noqa: BLE001 - 非 JSON 响应直接跳过
            return
        if isinstance(data, dict):
            bodies.append(data)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, channel="chromium")
        context = await browser.new_context(storage_state=str(cookie))
        try:
            page = await context.new_page()

            def schedule(response) -> None:
                task = asyncio.create_task(on_response(response))
                tasks.add(task)
                task.add_done_callback(tasks.discard)

            page.on("response", schedule)
            try:
                await page.goto(
                    target["page"], wait_until="domcontentloaded", timeout=60000
                )
            except Exception as exc:  # noqa: BLE001
                _log(f"打开创作中心失败：{exc}")

            deadline = asyncio.get_running_loop().time() + LIST_WAIT_SECONDS
            while not bodies and asyncio.get_running_loop().time() < deadline:
                await page.wait_for_timeout(1000)
            # 列表接口可能被调用多次（不同 count），等待额外的分页响应落定。
            await page.wait_for_timeout(2000)
            await _scroll_through_pages(page, bodies, platform)
            final_url = page.url
        finally:
            await context.close()
            await browser.close()

    if not bodies:
        reason = "未捕获到作品列表接口"
        if any(key in final_url.lower() for key in ("login", "passport")):
            reason = "登录态已失效，请先在设置页重新扫码登录"
        return {"platform": platform, "count": 0, "items": [], "reason": reason}

    # 每页各自提取；跨页重复项保留，由工作台的合并器统一去重。
    items: list[dict[str, Any]] = []
    for body in bodies:
        items.extend(_extract(platform, body))
    return {"platform": platform, "count": len(items), "items": items, "reason": ""}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=sorted(TARGETS))
    parser.add_argument("--cookie", required=True)
    args = parser.parse_args()

    cookie = Path(args.cookie)
    if not cookie.is_file():
        result: dict[str, Any] = {
            "platform": args.platform,
            "count": 0,
            "items": [],
            "reason": f"找不到 Cookie 文件：{cookie}",
        }
    else:
        try:
            result = asyncio.run(capture(args.platform, cookie))
        except Exception as exc:  # noqa: BLE001 - 结果必须落成 JSON
            result = {
                "platform": args.platform,
                "count": 0,
                "items": [],
                "reason": f"抓取异常：{exc}",
            }

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
