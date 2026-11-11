"""发布前检查：把载荷校验归并成可分组、可修复、可阻断的检查项。

`errors` / `warnings` 是 `checks` 的派生视图，创建任务以派生 `errors` 为准；
前端只展示，不自行判定任何结论。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ...config import (
    MAX_POST_CONFIG_TITLE_LENGTH,
    MAX_PUBLISH_IMAGES_BY_PLATFORM,
    MAX_PUBLISH_NOTE_LENGTH,
    MAX_PUBLISH_TAGS,
    PUBLISH_PLATFORM_LABELS,
    PUBLISH_PLATFORM_XIAOHONGSHU,
    PUBLISH_SCHEDULE_MAX_LEAD,
    PUBLISH_SCHEDULE_MIN_LEAD,
    PUBLISH_TIMEZONE,
    SUPPORTED_PUBLISH_IMAGE_EXTENSIONS,
    XHS_DECLARATION_REPOST,
)
from ...errors import AppError
from ...models import PublishAccount, Story, StoryChapterPostConfig
from ..alias_stamp import alias_backup_root, stamped_alias
from ..files import ChapterImage
from ..sensitive_words import scan_text
from ..zhihu import validate_alias

STATUS_PASS = "pass"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"

GROUP_CONTENT = "content"
GROUP_ALIAS = "alias"
GROUP_IMAGES = "images"
GROUP_ACCOUNT = "account"
GROUP_PLATFORM = "platform"

ACTION_STAMP_ALIAS = "stamp_alias"
ACTION_CHECK_LOGIN = "check_login"
ACTION_OPEN_ZHIHU = "open_zhihu"
ACTION_OPEN_CHAPTERS = "open_chapters"
ACTION_OPEN_POST_CONFIG = "open_post_config"

# 已有这些状态的任务时，同一章节 / 平台 / 账号不允许再次发布。
# failed 表示上次没有提交成功，允许重新预览后再发。
BLOCKING_JOB_STATUSES = ("queued", "running", "scheduled", "unknown", "published")
_JOB_STATUS_LABELS = {
    "queued": "排队中",
    "running": "执行中",
    "scheduled": "已定时",
    "unknown": "待核对",
    "published": "已发布",
}


@dataclass(slots=True, frozen=True)
class CheckItem:
    """逐图明细：只描述是哪张图、是否通过。"""

    label: str
    status: str = STATUS_PASS


@dataclass(slots=True)
class PreflightCheck:
    key: str
    group: str
    label: str
    status: str
    message: str
    action: str | None = None
    action_label: str | None = None
    items: list[CheckItem] = field(default_factory=list)


def _check(
    key: str,
    group: str,
    label: str,
    status: str,
    message: str,
    *,
    action: str | None = None,
    action_label: str | None = None,
    items: list[CheckItem] | None = None,
) -> PreflightCheck:
    return PreflightCheck(
        key=key,
        group=group,
        label=label,
        status=status,
        message=message,
        action=action,
        action_label=action_label,
        items=list(items or []),
    )


def _labels_text(labels: list[str], limit: int = 6) -> str:
    if len(labels) <= limit:
        return "、".join(labels)
    return "、".join(labels[:limit]) + f" 等 {len(labels)} 张"


def _content_checks(
    *,
    config: StoryChapterPostConfig | None,
    chapter_number: int,
    title: str,
    note: str,
    tags: list[str],
    platform_label: str,
    sensitive_words: list[dict],
) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    edit = ACTION_OPEN_POST_CONFIG
    edit_label = "去修改"

    if config is None:
        checks.append(
            _check(
                "content.config",
                GROUP_CONTENT,
                "本章文案",
                STATUS_ERROR,
                f"第 {chapter_number} 章还没有保存发文配置，请先填写标题、正文和标签",
                action=edit,
                action_label="去填写",
            )
        )
    else:
        checks.append(
            _check(
                "content.config",
                GROUP_CONTENT,
                "本章文案",
                STATUS_PASS,
                f"第 {chapter_number} 章发文配置已保存",
            )
        )

    if not title:
        checks.append(
            _check(
                "content.title",
                GROUP_CONTENT,
                "标题",
                STATUS_ERROR,
                "标题不能为空",
                action=edit,
                action_label="去填写",
            )
        )
    elif len(title) > MAX_POST_CONFIG_TITLE_LENGTH:
        checks.append(
            _check(
                "content.title",
                GROUP_CONTENT,
                "标题",
                STATUS_ERROR,
                f"标题不能超过 {MAX_POST_CONFIG_TITLE_LENGTH} 字，当前 {len(title)} 字",
                action=edit,
                action_label=edit_label,
            )
        )
    else:
        checks.append(
            _check(
                "content.title",
                GROUP_CONTENT,
                "标题",
                STATUS_PASS,
                f"标题 {len(title)} 字，未超过 {MAX_POST_CONFIG_TITLE_LENGTH} 字",
            )
        )

    if not note.strip():
        checks.append(
            _check(
                "content.note",
                GROUP_CONTENT,
                "正文",
                STATUS_WARNING,
                f"正文为空，{platform_label}将只发布标题与标签",
                action=edit,
                action_label="去填写",
            )
        )
    else:
        checks.append(
            _check(
                "content.note",
                GROUP_CONTENT,
                "正文",
                STATUS_PASS,
                f"正文 {len(note)} 字",
            )
        )

    tags_text = " ".join(f"#{tag}" for tag in tags)
    total_length = len(note) + len(tags_text) + (2 if note and tags_text else 0)
    if len(note) > MAX_PUBLISH_NOTE_LENGTH:
        checks.append(
            _check(
                "content.length",
                GROUP_CONTENT,
                "正文与标签总长",
                STATUS_ERROR,
                f"正文不能超过 {MAX_PUBLISH_NOTE_LENGTH} 字，当前 {len(note)} 字",
                action=edit,
                action_label=edit_label,
            )
        )
    elif total_length > MAX_PUBLISH_NOTE_LENGTH:
        checks.append(
            _check(
                "content.length",
                GROUP_CONTENT,
                "正文与标签总长",
                STATUS_WARNING,
                "正文加话题后的总长度接近或超过 1000 字，平台可能截断或拒绝发布",
                action=edit,
                action_label=edit_label,
            )
        )
    else:
        checks.append(
            _check(
                "content.length",
                GROUP_CONTENT,
                "正文与标签总长",
                STATUS_PASS,
                f"正文与标签共 {total_length} 字，未超过 {MAX_PUBLISH_NOTE_LENGTH} 字",
            )
        )

    if not tags:
        checks.append(
            _check(
                "content.tags",
                GROUP_CONTENT,
                "发布标签",
                STATUS_ERROR,
                "还没有发布标签，至少选择或输入 1 个；发布时按 #话题 追加",
                action=edit,
                action_label=edit_label,
            )
        )
    elif len(tags) > MAX_PUBLISH_TAGS:
        checks.append(
            _check(
                "content.tags",
                GROUP_CONTENT,
                "发布标签",
                STATUS_ERROR,
                f"标签最多 {MAX_PUBLISH_TAGS} 个，当前 {len(tags)} 个",
                action=edit,
                action_label=edit_label,
            )
        )
    else:
        checks.append(
            _check(
                "content.tags",
                GROUP_CONTENT,
                "发布标签",
                STATUS_PASS,
                f"标签 {len(tags)} 个，未超过 {MAX_PUBLISH_TAGS} 个",
            )
        )

    scan = scan_text(f"{title}\n{note}", sensitive_words)
    if scan["total"] > 0:
        words = list(scan["counts"].items())[:5]
        detail = "、".join(f"{word}×{count}" for word, count in words)
        if len(scan["counts"]) > len(words):
            detail += " 等"
        checks.append(
            _check(
                "content.sensitive",
                GROUP_CONTENT,
                "敏感词",
                STATUS_WARNING,
                f"标题或正文命中敏感词 {scan['total']} 处：{detail}；发布前建议处理",
                action=edit,
                action_label=edit_label,
            )
        )
    else:
        checks.append(
            _check(
                "content.sensitive",
                GROUP_CONTENT,
                "敏感词",
                STATUS_PASS,
                "标题与正文未命中已启用的敏感词",
            )
        )
    return checks


def _alias_checks(
    *,
    story: Story,
    alias: str,
    note: str,
    images: list[ChapterImage],
    image_hashes: dict[Path, str],
    upload_dir: Path,
) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    if not alias:
        checks.append(
            _check(
                "alias.configured",
                GROUP_ALIAS,
                "最终别名",
                STATUS_ERROR,
                "还没有设置最终别名，请先在「知乎推广」中填写并保存",
                action=ACTION_OPEN_ZHIHU,
                action_label="去设置",
            )
        )
        return checks

    checks.append(
        _check(
            "alias.configured",
            GROUP_ALIAS,
            "最终别名",
            STATUS_PASS,
            f"最终别名：【{alias}】",
        )
    )

    try:
        validate_alias(story.name or "", alias)
    except AppError as exc:
        checks.append(
            _check(
                "alias.valid",
                GROUP_ALIAS,
                "别名格式",
                STATUS_ERROR,
                exc.message,
                action=ACTION_OPEN_ZHIHU,
                action_label="去修改",
            )
        )
    else:
        checks.append(
            _check(
                "alias.valid",
                GROUP_ALIAS,
                "别名格式",
                STATUS_PASS,
                "别名格式正确，且没有复用故事名中的连续两字",
            )
        )

    if note.strip():
        if note.startswith(f"【{alias}】"):
            checks.append(
                _check(
                    "alias.note_prefix",
                    GROUP_ALIAS,
                    "正文别名前缀",
                    STATUS_PASS,
                    f"正文以【{alias}】开头",
                )
            )
        else:
            checks.append(
                _check(
                    "alias.note_prefix",
                    GROUP_ALIAS,
                    "正文别名前缀",
                    STATUS_WARNING,
                    f"正文未以【{alias}】开头；请回到发文配置保存一次以补齐别名前缀",
                    action=ACTION_OPEN_POST_CONFIG,
                    action_label="去修改",
                )
            )

    if not images:
        checks.append(
            _check(
                "alias.images",
                GROUP_ALIAS,
                "图片别名水印",
                STATUS_PASS,
                "本章没有可检查的图片",
            )
        )
        return checks

    backup_root = alias_backup_root(upload_dir, story.id)
    items: list[CheckItem] = []
    missing: list[str] = []
    mismatched: list[str] = []
    for image in images:
        stamped = stamped_alias(
            image.path,
            upload_dir=upload_dir,
            backup_root=backup_root,
            current_hash=image_hashes.get(image.path),
        )
        if stamped == alias:
            items.append(CheckItem(label=image.label))
            continue
        items.append(CheckItem(label=image.label, status=STATUS_WARNING))
        if stamped is None:
            missing.append(image.label)
        else:
            mismatched.append(image.label)

    if not missing and not mismatched:
        checks.append(
            _check(
                "alias.images",
                GROUP_ALIAS,
                "图片别名水印",
                STATUS_PASS,
                f"封面、正文页、引导卡均已加【{alias}】",
                items=items,
            )
        )
        return checks

    parts: list[str] = []
    if missing:
        parts.append(f"未检测到【{alias}】：{_labels_text(missing)}")
    if mismatched:
        parts.append(f"别名不是【{alias}】：{_labels_text(mismatched)}")
    checks.append(
        _check(
            "alias.images",
            GROUP_ALIAS,
            "图片别名水印",
            STATUS_WARNING,
            "；".join(parts) + "。点击「一键加别名」后会自动重新预览",
            action=ACTION_STAMP_ALIAS,
            action_label="一键加别名",
            items=items,
        )
    )
    return checks


def _image_checks(
    *,
    chapter: dict | None,
    chapter_number: int,
    pages: list[dict],
    images: list[ChapterImage],
    platform_label: str,
    platform: str,
) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    labels = {image.label for image in images}
    upload = ACTION_OPEN_CHAPTERS
    upload_label = "去上传"

    if chapter is None:
        checks.append(
            _check(
                "images.chapter",
                GROUP_IMAGES,
                "章节",
                STATUS_ERROR,
                f"第 {chapter_number} 章不存在，请重新规划章节",
                action=upload,
                action_label=upload_label,
            )
        )
        checks.append(
            _check(
                "images.pages",
                GROUP_IMAGES,
                "正文页图片",
                STATUS_ERROR,
                "章节不存在，无法检查正文页图片",
                action=upload,
                action_label=upload_label,
            )
        )
    else:
        checks.append(
            _check(
                "images.chapter",
                GROUP_IMAGES,
                "章节",
                STATUS_PASS,
                f"第 {chapter_number} 章已规划",
            )
        )

        if "封面" in labels:
            checks.append(
                _check(
                    "images.cover",
                    GROUP_IMAGES,
                    "章节封面",
                    STATUS_PASS,
                    "章节封面已上传",
                )
            )
        else:
            checks.append(
                _check(
                    "images.cover",
                    GROUP_IMAGES,
                    "章节封面",
                    STATUS_ERROR,
                    "章节封面未上传或文件缺失，请先上传章节封面",
                    action=upload,
                    action_label=upload_label,
                )
            )

        if "引导卡" in labels:
            checks.append(
                _check(
                    "images.guide",
                    GROUP_IMAGES,
                    "引导卡",
                    STATUS_PASS,
                    "引导卡已上传",
                )
            )
        else:
            checks.append(
                _check(
                    "images.guide",
                    GROUP_IMAGES,
                    "引导卡",
                    STATUS_WARNING,
                    "章节引导卡未上传或文件缺失，本次发布不会包含引导卡",
                    action=upload,
                    action_label=upload_label,
                )
            )

        pages_by_mapping = {
            page.get("mapping_page_number"): page
            for page in pages
            if page.get("mapping_page_number") is not None
        }
        expected: list[str] = []
        for mapping_number in chapter.get("mapping_page_numbers") or []:
            page = pages_by_mapping.get(mapping_number)
            if page is None or page.get("page_number") is None:
                expected.append(f"对照段 {mapping_number}")
                continue
            expected.append(f"第{page.get('chapter_page_number')}页")
        missing_pages = [label for label in expected if label not in labels]
        if not expected:
            checks.append(
                _check(
                    "images.pages",
                    GROUP_IMAGES,
                    "正文页图片",
                    STATUS_ERROR,
                    "本章还没有正文页，请先规划章节正文",
                    action=upload,
                    action_label=upload_label,
                )
            )
        elif missing_pages:
            checks.append(
                _check(
                    "images.pages",
                    GROUP_IMAGES,
                    "正文页图片",
                    STATUS_ERROR,
                    f"正文图缺失 {len(missing_pages)} 张：{_labels_text(missing_pages)}",
                    action=upload,
                    action_label=upload_label,
                )
            )
        else:
            checks.append(
                _check(
                    "images.pages",
                    GROUP_IMAGES,
                    "正文页图片",
                    STATUS_PASS,
                    f"正文页图片齐全（{len(expected)} 页）",
                )
            )

    max_images = MAX_PUBLISH_IMAGES_BY_PLATFORM.get(platform)
    if not images:
        checks.append(
            _check(
                "images.count",
                GROUP_IMAGES,
                "图片数量",
                STATUS_ERROR,
                "本章没有可发布的图片",
                action=upload,
                action_label=upload_label,
            )
        )
    elif max_images is not None and len(images) > max_images:
        checks.append(
            _check(
                "images.count",
                GROUP_IMAGES,
                "图片数量",
                STATUS_ERROR,
                f"{platform_label}图文最多 {max_images} 张图片，当前 {len(images)} 张",
                action=upload,
                action_label=upload_label,
            )
        )
    else:
        limit = f"，{platform_label}上限 {max_images} 张" if max_images else ""
        checks.append(
            _check(
                "images.count",
                GROUP_IMAGES,
                "图片数量",
                STATUS_PASS,
                f"共 {len(images)} 张图片{limit}",
            )
        )

    unsupported = [
        image.path.name
        for image in images
        if image.path.suffix.lower() not in SUPPORTED_PUBLISH_IMAGE_EXTENSIONS
    ]
    if unsupported:
        checks.append(
            _check(
                "images.format",
                GROUP_IMAGES,
                "图片格式",
                STATUS_ERROR,
                f"以下图片格式{platform_label}不支持：" + "、".join(unsupported[:5]),
                action=upload,
                action_label=upload_label,
            )
        )
    else:
        checks.append(
            _check(
                "images.format",
                GROUP_IMAGES,
                "图片格式",
                STATUS_PASS,
                "图片格式均为平台支持的 JPG、PNG、WebP 或 BMP",
            )
        )

    if images:
        order = [image.label for image in images]
        checks.append(
            _check(
                "images.order",
                GROUP_IMAGES,
                "发布顺序",
                STATUS_PASS,
                f"发布顺序：{' → '.join(order[:6])}"
                + (" → …" if len(order) > 6 else ""),
            )
        )
    return checks


def _account_checks(
    *,
    account: PublishAccount,
    platform: str,
    platform_label: str,
    chapter_number: int,
    mode: str,
    raw_schedule_at: datetime | None,
    schedule_at: datetime | None,
    now: datetime,
    existing_job_statuses: list[str],
) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []

    if account.status == "invalid":
        checks.append(
            _check(
                "account.login",
                GROUP_ACCOUNT,
                "账号登录",
                STATUS_ERROR,
                "账号登录已失效，请重新登录并检测后再发布",
                action=ACTION_CHECK_LOGIN,
                action_label="检测登录",
            )
        )
    elif account.status == "unknown":
        checks.append(
            _check(
                "account.login",
                GROUP_ACCOUNT,
                "账号登录",
                STATUS_WARNING,
                "账号尚未检测登录状态，建议先点「检测登录」",
                action=ACTION_CHECK_LOGIN,
                action_label="检测登录",
            )
        )
    else:
        checks.append(
            _check(
                "account.login",
                GROUP_ACCOUNT,
                "账号登录",
                STATUS_PASS,
                "账号登录状态正常",
            )
        )

    if MAX_PUBLISH_IMAGES_BY_PLATFORM.get(platform) is None:
        checks.append(
            _check(
                "platform.target",
                GROUP_PLATFORM,
                "发布平台",
                STATUS_ERROR,
                f"不支持的发布平台：{platform}",
            )
        )

    if mode not in ("scheduled", "immediate"):
        checks.append(
            _check(
                "platform.schedule",
                GROUP_PLATFORM,
                "发布方式",
                STATUS_ERROR,
                f"不支持的发布方式：{mode}",
            )
        )
    elif mode == "immediate":
        if raw_schedule_at is not None:
            checks.append(
                _check(
                    "platform.schedule",
                    GROUP_PLATFORM,
                    "发布方式",
                    STATUS_ERROR,
                    "立即发布不需要定时时间，请清空定时后再预览",
                )
            )
        else:
            checks.append(
                _check(
                    "platform.schedule",
                    GROUP_PLATFORM,
                    "发布方式",
                    STATUS_PASS,
                    "立即发布：创建后马上上传，成功即对读者可见，不可撤回",
                )
            )
    elif schedule_at is None:
        checks.append(
            _check(
                "platform.schedule",
                GROUP_PLATFORM,
                "发布方式",
                STATUS_ERROR,
                "请选择定时发布时间",
            )
        )
    else:
        local = schedule_at.astimezone(PUBLISH_TIMEZONE)
        if schedule_at <= now + PUBLISH_SCHEDULE_MIN_LEAD:
            earliest = (now + PUBLISH_SCHEDULE_MIN_LEAD).astimezone(
                PUBLISH_TIMEZONE
            )
            checks.append(
                _check(
                    "platform.schedule",
                    GROUP_PLATFORM,
                    "发布方式",
                    STATUS_ERROR,
                    "定时发布时间必须晚于当前时间 2 小时（最早 "
                    f"{earliest.strftime('%Y-%m-%d %H:%M')}）",
                )
            )
        elif schedule_at > now + PUBLISH_SCHEDULE_MAX_LEAD:
            latest = (now + PUBLISH_SCHEDULE_MAX_LEAD).astimezone(
                PUBLISH_TIMEZONE
            )
            checks.append(
                _check(
                    "platform.schedule",
                    GROUP_PLATFORM,
                    "发布方式",
                    STATUS_ERROR,
                    f"定时发布时间不能超过当前时间 {PUBLISH_SCHEDULE_MAX_LEAD.days} 天"
                    f"（最晚 {latest.strftime('%Y-%m-%d %H:%M')}）",
                )
            )
        else:
            checks.append(
                _check(
                    "platform.schedule",
                    GROUP_PLATFORM,
                    "发布方式",
                    STATUS_PASS,
                    f"定时发布：{local.strftime('%Y-%m-%d %H:%M')}（北京时间）",
                )
            )

    blocking = [
        status for status in existing_job_statuses if status in BLOCKING_JOB_STATUSES
    ]
    if blocking:
        states = "、".join(
            _JOB_STATUS_LABELS.get(status, status) for status in blocking
        )
        checks.append(
            _check(
                "platform.duplicate",
                GROUP_PLATFORM,
                "重复发布",
                STATUS_ERROR,
                f"第 {chapter_number} 章在{platform_label}账号"
                f"「{account.display_name}」已有{states}任务；"
                "同一章节同一平台账号只能发布一次，"
                "请先到发布任务页确认原任务",
            )
        )
    else:
        checks.append(
            _check(
                "platform.duplicate",
                GROUP_PLATFORM,
                "重复发布",
                STATUS_PASS,
                f"该{platform_label}账号尚未发布本章",
            )
        )
    return checks


def _xhs_settings_checks(
    *,
    platform: str,
    declaration: str | None,
    repost_source: str | None,
) -> list[PreflightCheck]:
    """小红书故事级发布设置：内容声明。

    声明是用户显式选择的状态，恒 pass；合集暂停接入，不产出检查项。
    """
    if platform != PUBLISH_PLATFORM_XIAOHONGSHU:
        return []
    checks: list[PreflightCheck] = []
    if declaration == XHS_DECLARATION_REPOST:
        message = (
            f"发布会声明「来源转载」，来源媒体「{repost_source}」"
            if repost_source
            else "发布会声明「来源转载」，但没有来源媒体名"
        )
    elif declaration:
        message = f"发布会声明「{declaration}」"
    else:
        message = "未设置内容声明，发布时不会添加任何内容类型声明"
    checks.append(
        _check(
            "platform.declaration",
            GROUP_PLATFORM,
            "内容声明",
            STATUS_PASS,
            message,
        )
    )
    return checks


def build_preflight(
    *,
    story: Story,
    pages: list[dict],
    chapter: dict | None,
    chapter_number: int,
    config: StoryChapterPostConfig | None,
    title: str,
    note: str,
    tags: list[str],
    images: list[ChapterImage],
    image_hashes: dict[Path, str],
    account: PublishAccount,
    platform: str,
    mode: str,
    raw_schedule_at: datetime | None,
    schedule_at: datetime | None,
    now: datetime,
    upload_dir: Path,
    sensitive_words: list[dict],
    existing_job_statuses: list[str],
    declaration: str | None = None,
    repost_source: str | None = None,
) -> list[PreflightCheck]:
    """按文案 → 别名 → 图片 → 账号 / 平台的固定顺序产出检查项。"""
    platform_label = PUBLISH_PLATFORM_LABELS.get(platform, platform)
    alias = (story.zhihu_alias or "").strip()
    return [
        *_content_checks(
            config=config,
            chapter_number=chapter_number,
            title=title,
            note=note,
            tags=tags,
            platform_label=platform_label,
            sensitive_words=sensitive_words,
        ),
        *_alias_checks(
            story=story,
            alias=alias,
            note=note,
            images=images,
            image_hashes=image_hashes,
            upload_dir=upload_dir,
        ),
        *_image_checks(
            chapter=chapter,
            chapter_number=chapter_number,
            pages=pages,
            images=images,
            platform_label=platform_label,
            platform=platform,
        ),
        *_account_checks(
            account=account,
            platform=platform,
            platform_label=platform_label,
            chapter_number=chapter_number,
            mode=mode,
            raw_schedule_at=raw_schedule_at,
            schedule_at=schedule_at,
            now=now,
            existing_job_statuses=existing_job_statuses,
        ),
        *_xhs_settings_checks(
            platform=platform,
            declaration=declaration,
            repost_source=repost_source,
        ),
    ]
