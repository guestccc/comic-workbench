"""发布载荷的唯一渲染与校验入口。

标题、正文、标签、图片顺序都从这里产出；预览与创建任务复用同一份结果，
前端不得自行拼接。检查项由 preflight 统一计算，errors / warnings 只做派生。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ...models import PublishAccount, Story, StoryBreakdown, StoryChapterPostConfig
from ...config import (
    PUBLISH_PLATFORM_XIAOHONGSHU,
    XHS_DECLARATION_REPOST,
)
from ..files import ChapterImage, collect_chapter_images
from .preflight import STATUS_ERROR, STATUS_WARNING, PreflightCheck, build_preflight


@dataclass(slots=True)
class RenderedPayload:
    """预览与任务共用的渲染结果；errors 非空时禁止发布。"""

    platform: str
    mode: str
    account_name: str
    title: str
    note: str
    tags: list[str]
    images: list[ChapterImage]
    schedule_at: datetime | None
    # 小红书发布设置；抖音恒为 None
    declaration: str | None = None
    # 只有「来源转载」声明下才有值
    repost_source: str | None = None
    collection: str | None = None
    checks: list[PreflightCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_hash: str = ""
    payload_hash: str = ""

    @property
    def is_blocked(self) -> bool:
        return bool(self.errors)

    def to_json_dict(self, image_paths: list[str] | None = None) -> dict:
        """冻结到 publish_jobs.payload_json 的结构。

        image_paths 传任务快照内的绝对路径；预览时不传，只用于哈希。
        立即发布的 schedule_at 为 null；mode 决定执行时是否带 --schedule。
        """
        schedule_value = None
        if self.schedule_at is not None:
            schedule_value = (
                self.schedule_at.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
        return {
            "platform": self.platform,
            "mode": self.mode,
            "account_name": self.account_name,
            "title": self.title,
            "note": self.note,
            "tags": list(self.tags),
            "images": list(
                image_paths
                if image_paths is not None
                else [str(image.path) for image in self.images]
            ),
            "schedule_at": schedule_value,
            "declaration": self.declaration,
            "repost_source": self.repost_source,
            "collection": self.collection,
        }


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_chapter(breakdown: StoryBreakdown, chapter_number: int) -> dict | None:
    for chapter in breakdown.chapters or []:
        if chapter.get("chapter_number") == chapter_number:
            return chapter
    return None


def _declaration_for(story: Story, platform: str) -> str | None:
    """小红书内容声明文案；抖音没有对应参数，恒为 None。"""
    if platform != PUBLISH_PLATFORM_XIAOHONGSHU:
        return None
    return (story.xhs_declaration or "").strip() or None


def _repost_source_for(story: Story, platform: str, declaration: str | None) -> str | None:
    """来源转载的媒体名；其他声明下即使填了也不进入载荷。"""
    if platform != PUBLISH_PLATFORM_XIAOHONGSHU:
        return None
    if declaration != XHS_DECLARATION_REPOST:
        return None
    return (story.xhs_repost_source or "").strip() or None


# 合集暂停接入：sau 工作区还没有 --collection，等 PR2 合入后从
# stories.xhs_collection 接回（见蓝图 2026-11-10-xiaohongshu-publish-settings）。
def _collection_for(story: Story, platform: str) -> str | None:
    return None


def render_payload(
    *,
    story: Story,
    breakdown: StoryBreakdown,
    chapter_number: int,
    config: StoryChapterPostConfig | None,
    account: PublishAccount,
    platform: str,
    mode: str = "scheduled",
    schedule_at: datetime | None,
    upload_dir: Path,
    now: datetime | None = None,
    sensitive_words: list[dict] | None = None,
    existing_job_statuses: list[str] | None = None,
) -> RenderedPayload:
    """渲染并校验发布载荷；不读数据库、不写文件。"""
    now = now or datetime.now(timezone.utc)
    chapter = _find_chapter(breakdown, chapter_number)
    title = (config.title if config else "").strip()
    note = config.content if config else ""
    tags = list(config.tags or []) if config else []

    images = (
        collect_chapter_images(
            upload_dir, story.id, chapter, breakdown.pages or []
        )
        if chapter is not None
        else []
    )

    raw_schedule_at = schedule_at
    if mode == "immediate":
        normalized_schedule = None
    elif schedule_at is not None and schedule_at.tzinfo is None:
        normalized_schedule = schedule_at.replace(tzinfo=timezone.utc)
    else:
        normalized_schedule = schedule_at

    declaration = _declaration_for(story, platform)
    payload = RenderedPayload(
        platform=platform,
        mode=mode,
        account_name=account.account_name,
        title=title,
        note=note,
        tags=tags,
        images=images,
        schedule_at=normalized_schedule,
        declaration=declaration,
        repost_source=_repost_source_for(story, platform, declaration),
        collection=_collection_for(story, platform),
    )
    image_hashes = {
        image.path: _sha256_file(image.path) for image in images
    }
    payload.checks = build_preflight(
        story=story,
        pages=list(breakdown.pages or []),
        chapter=chapter,
        chapter_number=chapter_number,
        config=config,
        title=title,
        note=note,
        tags=tags,
        images=images,
        image_hashes=image_hashes,
        account=account,
        platform=platform,
        mode=mode,
        raw_schedule_at=raw_schedule_at,
        schedule_at=normalized_schedule,
        now=now,
        upload_dir=upload_dir,
        sensitive_words=sensitive_words or [],
        existing_job_statuses=existing_job_statuses or [],
        declaration=payload.declaration,
        repost_source=payload.repost_source,
    )
    payload.errors = [
        check.message for check in payload.checks if check.status == STATUS_ERROR
    ]
    payload.warnings = [
        check.message for check in payload.checks if check.status == STATUS_WARNING
    ]

    payload.source_hash = _sha256_text(
        _canonical(
            {
                "title": title,
                "note": note,
                "tags": tags,
                "images": [image_hashes[image.path] for image in images],
            }
        )
    )
    hash_parts: dict[str, object] = {
        "source_hash": payload.source_hash,
        "platform": platform,
        "mode": mode,
        "account_name": account.account_name,
        "declaration": payload.declaration,
        "repost_source": payload.repost_source,
        "collection": payload.collection,
    }
    if payload.schedule_at is not None:
        hash_parts["schedule_at"] = (
            payload.schedule_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    payload.payload_hash = _sha256_text(_canonical(hash_parts))
    return payload
