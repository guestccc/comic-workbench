"""创作中心抓取结果解析：标题匹配与抓取器输出读取。

纯函数，不启动浏览器、不访问数据库，可直接单测；标题匹配只在这里实现一次。
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from ...config import PUBLISH_PLATFORM_DOUYIN, PUBLISH_PLATFORM_XIAOHONGSHU

# 去掉首尾标点后再比较，避免标题末尾「。！？」差异导致匹配失败。
_TRAILING_PUNCTUATION = "。．.!！?？…⋯、,，;；:：~～-—_ 　\n\r\t"

# 只接受平台正式域名，防止把异常数据写成奇怪链接。
_ALLOWED_HOSTS = {
    PUBLISH_PLATFORM_DOUYIN: {"www.douyin.com", "douyin.com"},
    PUBLISH_PLATFORM_XIAOHONGSHU: {"www.xiaohongshu.com", "xiaohongshu.com"},
}


def normalize_title(text: Any) -> str:
    """去空白、去首尾标点并统一大小写，用于标题比较。"""
    compact = "".join(str(text or "").split())
    return compact.strip(_TRAILING_PUNCTUATION).lower()


def _first_line(text: Any) -> str:
    for line in str(text or "").splitlines():
        if line.strip():
            return line
    return ""


def _item_title(platform: str, title: Any) -> str:
    # 抖音 desc = 标题 + 正文，标题只在第一行；小红书 display_title 就是标题。
    if platform == PUBLISH_PLATFORM_DOUYIN:
        return _first_line(title)
    return str(title or "")


def _title_matches(
    platform: str, item_title: str, raw_target: str, normalized_target: str
) -> bool:
    """抖音标题后可能紧跟别名，用前缀匹配；小红书标题独立，用精确匹配。"""
    if platform == PUBLISH_PLATFORM_DOUYIN:
        return (
            str(item_title or "").strip().casefold().startswith(
                raw_target.casefold()
            )
        )
    return normalize_title(item_title) == normalized_target


def _is_allowed_url(platform: str, url: str) -> bool:
    parsed = urlparse(url)
    hosts = _ALLOWED_HOSTS.get(platform, set())
    return parsed.scheme == "https" and parsed.hostname in hosts


def merge_capture_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """跨页合并：按链接去重，保持平台返回顺序。"""
    merged: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        key: Any = url or (
            str(item.get("title") or ""),
            item.get("created_at"),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def match_capture_item(
    platform: str, title: str, items: list[dict[str, Any]]
) -> str | None:
    """按标题从抓取条目中选一条已发布作品链接；多条命中取发布时间最新。"""
    target = normalize_title(title)
    raw_target = str(title or "").strip()
    if not target or not raw_target:
        return None
    matches: list[tuple[int, str]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or not _is_allowed_url(platform, url):
            continue
        item_title = _item_title(platform, item.get("title"))
        if not _title_matches(platform, item_title, raw_target, target):
            continue
        try:
            created_at = int(item.get("created_at") or 0)
        except (TypeError, ValueError):
            created_at = 0
        matches.append((created_at, url))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]


def parse_worker_output(text: str) -> dict[str, Any]:
    """取抓取器标准输出的最后一行 JSON；解析失败抛出 ValueError。"""
    for line in reversed(str(text or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("抓取器没有输出可解析的 JSON")
