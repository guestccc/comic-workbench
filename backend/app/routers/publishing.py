"""多平台发布接口：预设标签、账号、预览、任务与日志。"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    DEFAULT_PUBLISH_TAG_PRESETS,
    PUBLISH_PLATFORM_DOUYIN,
    PUBLISH_PLATFORM_LABELS,
    PUBLISH_SCHEDULE_MAX_LEAD,
    PUBLISH_SCHEDULE_MIN_LEAD,
    PUBLISH_TAG_PRESETS_KEY,
    XHS_DECLARATION_CHOICES,
    XHS_DECLARATION_NONE,
    XHS_DECLARATION_REPOST,
    XHS_DEFAULT_DECLARATION,
)
from ..crud import get_setting, upsert_setting
from ..database import get_db
from ..errors import AppError
from ..models import (
    PublishAccount,
    PublishJob,
    Story,
    StoryBreakdown,
    StoryChapterPostConfig,
    utc_now,
)
from ..schemas import (
    PreflightCheckItemRead,
    PreflightCheckRead,
    PublishAccountRead,
    PublishImageRead,
    PublishJobCreate,
    PublishJobLogRead,
    PublishJobPatch,
    PublishJobRead,
    PublishJobStatus,
    PublishLoginRead,
    PublishPayloadRead,
    PublishPlatform,
    PublishPreviewRead,
    PublishPreviewRequest,
    PublishTagPresetsRead,
    PublishTagPresetsUpdate,
    XhsDeclarationOptionRead,
    XhsDeclarationOptionsRead,
)
from ..services.publishing import (
    ensure_default_accounts,
    fetch_published_link,
    render_payload,
    run_sau_check,
    start_job_thread,
    start_sau_login,
    strip_ansi,
)
from ..services.publishing.payload import RenderedPayload
from ..services.publishing.preflight import BLOCKING_JOB_STATUSES
from ..services.sensitive_words import load_sensitive_words

router = APIRouter(prefix="/api/publishing", tags=["多平台发布"])

_UNSAFE_LABEL_CHARS = re.compile(r'[\\/:*?"<>|]+')


def _get_story_or_404(db: Session, story_id: int) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise AppError(404, "故事不存在或已被删除", "STORY_NOT_FOUND")
    return story


def _get_breakdown_or_404(db: Session, story_id: int) -> StoryBreakdown:
    breakdown = db.scalar(
        select(StoryBreakdown).where(StoryBreakdown.story_id == story_id)
    )
    if breakdown is None or not breakdown.chapters:
        raise AppError(404, "该故事还没有章节规划", "CHAPTERS_NOT_FOUND")
    return breakdown


def _get_account_or_404(db: Session, account_id: int) -> PublishAccount:
    account = db.get(PublishAccount, account_id)
    if account is None:
        raise AppError(404, "发布账号不存在", "PUBLISH_ACCOUNT_NOT_FOUND")
    return account


def _get_chapter_config(
    db: Session, story_id: int, chapter_number: int
) -> StoryChapterPostConfig | None:
    return db.scalar(
        select(StoryChapterPostConfig).where(
            StoryChapterPostConfig.story_id == story_id,
            StoryChapterPostConfig.chapter_number == chapter_number,
        )
    )


def _account_read(account: PublishAccount) -> PublishAccountRead:
    return PublishAccountRead(
        id=account.id,
        platform=account.platform,
        account_name=account.account_name,
        display_name=account.display_name,
        status=account.status,
        last_checked_at=account.last_checked_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _snapshot_image_urls(
    upload_dir: Path, images: list[str]
) -> list[str]:
    """把任务快照里的绝对路径转成 /uploads 访问地址。"""
    urls: list[str] = []
    for raw in images:
        path = Path(raw)
        try:
            relative = path.resolve().relative_to(upload_dir.resolve())
        except (OSError, ValueError):
            urls.append(path.name)
            continue
        urls.append(f"/uploads/{relative.as_posix()}")
    return urls


def _payload_read(job: PublishJob, upload_dir: Path) -> PublishPayloadRead:
    raw = dict(job.payload_json or {})
    return PublishPayloadRead(
        platform=raw.get("platform", job.platform),
        mode=raw.get("mode", "scheduled"),
        account_name=raw.get("account_name", ""),
        title=raw.get("title", ""),
        note=raw.get("note", ""),
        tags=list(raw.get("tags") or []),
        images=_snapshot_image_urls(upload_dir, list(raw.get("images") or [])),
        schedule_at=raw.get("schedule_at", job.scheduled_at),
        # 历史载荷没有这几项，按不声明、不加入合集展示
        declaration=raw.get("declaration"),
        repost_source=raw.get("repost_source"),
        collection=raw.get("collection"),
    )


def _log_path(log_dir: Path, job_id: str) -> Path:
    return log_dir / f"{job_id}.log"


def _job_read(
    job: PublishJob, upload_dir: Path, log_dir: Path
) -> PublishJobRead:
    return PublishJobRead(
        id=job.id,
        story_id=job.story_id,
        chapter_number=job.chapter_number,
        platform=job.platform,
        account_id=job.account_id,
        status=job.status,
        scheduled_at=job.scheduled_at,
        payload=_payload_read(job, upload_dir),
        payload_hash=job.payload_hash,
        source_hash=job.source_hash,
        snapshot_dir=job.snapshot_dir,
        external_url=job.external_url,
        exit_code=job.exit_code,
        stdout_excerpt=job.stdout_excerpt,
        error_message=strip_ansi(job.error_message),
        started_at=job.started_at,
        finished_at=job.finished_at,
        log_available=_log_path(log_dir, job.id).is_file(),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _existing_job_statuses(
    db: Session,
    payload: PublishPreviewRequest,
    account: PublishAccount,
) -> list[str]:
    """同故事 + 同章节 + 同平台 + 同账号的非失败任务状态。"""
    return list(
        db.scalars(
            select(PublishJob.status).where(
                PublishJob.story_id == payload.story_id,
                PublishJob.chapter_number == payload.chapter_number,
                PublishJob.platform == payload.platform,
                PublishJob.account_id == account.id,
                PublishJob.status.in_(BLOCKING_JOB_STATUSES),
            )
        ).all()
    )


def _render(
    db: Session,
    settings,
    payload: PublishPreviewRequest,
) -> tuple[Story, RenderedPayload]:
    story = _get_story_or_404(db, payload.story_id)
    breakdown = _get_breakdown_or_404(db, payload.story_id)
    account = _get_account_or_404(db, payload.account_id)
    if account.platform != payload.platform:
        raise AppError(422, "账号平台与发布平台不一致", "PLATFORM_MISMATCH")
    config = _get_chapter_config(db, payload.story_id, payload.chapter_number)
    rendered = render_payload(
        story=story,
        breakdown=breakdown,
        chapter_number=payload.chapter_number,
        config=config,
        account=account,
        platform=payload.platform,
        mode=payload.publish_mode,
        schedule_at=payload.schedule_at,
        upload_dir=settings.upload_dir,
        sensitive_words=load_sensitive_words(db),
        existing_job_statuses=_existing_job_statuses(db, payload, account),
    )
    return story, rendered


def _preflight_read(rendered: RenderedPayload) -> list[PreflightCheckRead]:
    return [
        PreflightCheckRead(
            key=check.key,
            group=check.group,
            label=check.label,
            status=check.status,
            message=check.message,
            action=check.action,
            action_label=check.action_label,
            items=[
                PreflightCheckItemRead(label=item.label, status=item.status)
                for item in check.items
            ],
        )
        for check in rendered.checks
    ]


def _preview_read(
    rendered: RenderedPayload, account: PublishAccount, now: datetime
) -> PublishPreviewRead:
    return PublishPreviewRead(
        platform=rendered.platform,
        publish_mode=rendered.mode,
        account=_account_read(account),
        title=rendered.title,
        note=rendered.note,
        tags=rendered.tags,
        images=[
            PublishImageRead(
                label=image.label,
                url=image.url,
                filename=image.path.name,
            )
            for image in rendered.images
        ],
        image_count=len(rendered.images),
        title_length=len(rendered.title),
        note_length=len(rendered.note),
        schedule_at=rendered.schedule_at,
        schedule_min_at=now + PUBLISH_SCHEDULE_MIN_LEAD,
        schedule_max_at=now + PUBLISH_SCHEDULE_MAX_LEAD,
        payload_hash=rendered.payload_hash or None,
        source_hash=rendered.source_hash or None,
        declaration=rendered.declaration,
        repost_source=rendered.repost_source,
        collection=rendered.collection,
        checks=_preflight_read(rendered),
        errors=rendered.errors,
        warnings=rendered.warnings,
    )


# ---------------------------------------------------------------------------
# 预设标签
# ---------------------------------------------------------------------------


@router.get("/tag-presets", response_model=PublishTagPresetsRead)
def get_tag_presets(db: Session = Depends(get_db)) -> PublishTagPresetsRead:
    setting = get_setting(db, PUBLISH_TAG_PRESETS_KEY)
    if setting is None:
        return PublishTagPresetsRead(tags=list(DEFAULT_PUBLISH_TAG_PRESETS))
    try:
        parsed = json.loads(setting.value)
    except (TypeError, ValueError):
        return PublishTagPresetsRead(tags=list(DEFAULT_PUBLISH_TAG_PRESETS))
    if not isinstance(parsed, list):
        return PublishTagPresetsRead(tags=list(DEFAULT_PUBLISH_TAG_PRESETS))
    return PublishTagPresetsRead(
        tags=[str(item) for item in parsed if str(item).strip()]
    )


@router.put("/tag-presets", response_model=PublishTagPresetsRead)
def save_tag_presets(
    payload: PublishTagPresetsUpdate,
    db: Session = Depends(get_db),
) -> PublishTagPresetsRead:
    upsert_setting(
        db,
        PUBLISH_TAG_PRESETS_KEY,
        json.dumps(payload.tags, ensure_ascii=False),
    )
    db.commit()
    return PublishTagPresetsRead(tags=payload.tags)


# ---------------------------------------------------------------------------
# 小红书内容声明选项
# ---------------------------------------------------------------------------


@router.get("/xhs-declaration-options", response_model=XhsDeclarationOptionsRead)
def get_xhs_declaration_options() -> XhsDeclarationOptionsRead:
    """平台可选的内容声明文案；前端只渲染这份列表，不自行维护。"""
    options = [
        XhsDeclarationOptionRead(value=XHS_DECLARATION_NONE, label="不声明"),
        *(
            XhsDeclarationOptionRead(value=value, label=value)
            for value in XHS_DECLARATION_CHOICES
        ),
    ]
    return XhsDeclarationOptionsRead(
        options=options,
        default=XHS_DEFAULT_DECLARATION,
        repost_value=XHS_DECLARATION_REPOST,
    )


# ---------------------------------------------------------------------------
# 账号
# ---------------------------------------------------------------------------


@router.get("/accounts", response_model=list[PublishAccountRead])
def list_accounts(
    platform: PublishPlatform = Query(default=PUBLISH_PLATFORM_DOUYIN),
    db: Session = Depends(get_db),
) -> list[PublishAccountRead]:
    ensure_default_accounts(db)
    accounts = db.scalars(
        select(PublishAccount)
        .where(PublishAccount.platform == platform)
        .order_by(PublishAccount.id)
    ).all()
    return [_account_read(account) for account in accounts]


def _require_sau(settings) -> None:
    if not settings.sau_executable.is_file():
        raise AppError(
            503,
            f"找不到 sau 发布器：{settings.sau_executable}。"
            "请确认 social-auto-upload 已安装且路径正确",
            "SAU_NOT_FOUND",
        )


@router.post(
    "/accounts/{account_id}/check", response_model=PublishAccountRead
)
def check_account(
    account_id: int, request: Request, db: Session = Depends(get_db)
) -> PublishAccountRead:
    account = _get_account_or_404(db, account_id)
    settings = request.app.state.app_settings
    _require_sau(settings)
    valid = run_sau_check(settings, account.account_name, account.platform)
    account.status = "valid" if valid else "invalid"
    account.last_checked_at = utc_now()
    db.commit()
    db.refresh(account)
    return _account_read(account)


@router.post(
    "/accounts/{account_id}/login", response_model=PublishLoginRead
)
def login_account(
    account_id: int, request: Request, db: Session = Depends(get_db)
) -> PublishLoginRead:
    account = _get_account_or_404(db, account_id)
    settings = request.app.state.app_settings
    _require_sau(settings)
    start_sau_login(settings, account.account_name, account.platform)
    label = PUBLISH_PLATFORM_LABELS.get(account.platform, account.platform)
    return PublishLoginRead(
        message=(
            f"已打开{label}登录窗口，请在浏览器中扫码。"
            "完成后回到本页点「检测登录」确认状态。"
        )
    )


# ---------------------------------------------------------------------------
# 预览与任务
# ---------------------------------------------------------------------------


@router.post("/preview", response_model=PublishPreviewRead)
def preview_payload(
    payload: PublishPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PublishPreviewRead:
    settings = request.app.state.app_settings
    _, rendered = _render(db, settings, payload)
    account = _get_account_or_404(db, payload.account_id)
    return _preview_read(rendered, account, datetime.now(timezone.utc))


def _copy_snapshot_images(
    upload_dir: Path, job_id: str, rendered: RenderedPayload
) -> tuple[str, list[str]]:
    relative_dir = Path("publish-jobs") / job_id
    target_dir = upload_dir / relative_dir
    target_dir.mkdir(parents=True, exist_ok=False)
    paths: list[str] = []
    for index, image in enumerate(rendered.images, start=1):
        label = _UNSAFE_LABEL_CHARS.sub("_", image.label).strip() or "图"
        name = f"{index:02d}_{label}{image.path.suffix.lower()}"
        target = target_dir / name
        shutil.copy2(image.path, target)
        paths.append(str(target.resolve()))
    return relative_dir.as_posix(), paths


@router.post("/jobs", response_model=PublishJobRead, status_code=201)
def create_job(
    payload: PublishJobCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> PublishJobRead:
    settings = request.app.state.app_settings
    _, rendered = _render(db, settings, payload)

    if rendered.is_blocked:
        raise AppError(
            422,
            "发布载荷校验未通过：" + "；".join(rendered.errors),
            "PUBLISH_PAYLOAD_INVALID",
        )
    if not payload.confirm:
        raise AppError(422, "请先确认预览内容再创建发布任务", "PUBLISH_NOT_CONFIRMED")
    if not rendered.payload_hash or payload.preview_hash != rendered.payload_hash:
        raise AppError(
            409,
            "内容或定时时间与预览时不一致，请重新预览后再发布",
            "PUBLISH_PREVIEW_STALE",
        )

    account = _get_account_or_404(db, payload.account_id)

    job_id = uuid.uuid4().hex
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_dir, image_paths = _copy_snapshot_images(
            settings.upload_dir, job_id, rendered
        )
    except OSError as exc:
        raise AppError(
            500, f"复制发布图片失败：{exc}", "PUBLISH_SNAPSHOT_FAILED"
        ) from exc

    # scheduled_at 列不可为空；立即任务存创建时刻，仅作执行锚点。
    anchor = rendered.schedule_at or utc_now()
    job = PublishJob(
        id=job_id,
        story_id=payload.story_id,
        chapter_number=payload.chapter_number,
        platform=payload.platform,
        account_id=account.id,
        status="queued",
        # SQLite 会丢弃时区；统一存 UTC，读取时才能按 naive UTC 正确还原。
        scheduled_at=anchor.astimezone(timezone.utc),
        payload_json=rendered.to_json_dict(image_paths),
        payload_hash=rendered.payload_hash,
        source_hash=rendered.source_hash,
        snapshot_dir=snapshot_dir,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    start_job_thread(request.app.state.session_factory, settings, job.id)
    return _job_read(
        job, settings.upload_dir, settings.resolved_publish_log_dir
    )


@router.get("/jobs", response_model=list[PublishJobRead])
def list_jobs(
    request: Request,
    story_id: int | None = Query(default=None, ge=1),
    chapter_number: int | None = Query(default=None, ge=1),
    status: PublishJobStatus | None = Query(default=None),
    platform: PublishPlatform | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[PublishJobRead]:
    settings = request.app.state.app_settings
    query = select(PublishJob).order_by(PublishJob.created_at.desc()).limit(limit)
    if story_id is not None:
        query = query.where(PublishJob.story_id == story_id)
    if chapter_number is not None:
        query = query.where(PublishJob.chapter_number == chapter_number)
    if status is not None:
        query = query.where(PublishJob.status == status)
    if platform is not None:
        query = query.where(PublishJob.platform == platform)
    jobs = db.scalars(query).all()
    return [
        _job_read(job, settings.upload_dir, settings.resolved_publish_log_dir)
        for job in jobs
    ]


@router.get("/jobs/{job_id}", response_model=PublishJobRead)
def get_job(
    job_id: str, request: Request, db: Session = Depends(get_db)
) -> PublishJobRead:
    job = db.get(PublishJob, job_id)
    if job is None:
        raise AppError(404, "发布任务不存在", "PUBLISH_JOB_NOT_FOUND")
    settings = request.app.state.app_settings
    return _job_read(
        job, settings.upload_dir, settings.resolved_publish_log_dir
    )


_MANUAL_TRANSITIONS = {
    "unknown": {"scheduled", "failed", "published"},
    "scheduled": {"published"},
    "failed": {"published"},
    "published": set(),
}

# 只有已提交到平台的任务才有作品可抓：本地排队 / 执行中 / 失败均无意义。
_LINK_CAPTURE_STATUSES = {"scheduled", "unknown", "published"}


@router.post("/jobs/{job_id}/fetch-link", response_model=PublishJobRead)
def fetch_job_link(
    job_id: str, request: Request, db: Session = Depends(get_db)
) -> PublishJobRead:
    """按任务标题到创作中心匹配已发布作品，只回填 external_url。"""
    job = db.get(PublishJob, job_id)
    if job is None:
        raise AppError(404, "发布任务不存在", "PUBLISH_JOB_NOT_FOUND")
    if job.status not in _LINK_CAPTURE_STATUSES:
        raise AppError(
            409,
            f"任务当前状态为 {job.status}，提交平台后才能抓取作品链接",
            "PUBLISH_LINK_STATUS_INVALID",
        )
    account = db.get(PublishAccount, job.account_id)
    if account is None:
        raise AppError(
            404, "任务关联的发布账号已不存在", "PUBLISH_LINK_ACCOUNT_MISSING"
        )

    settings = request.app.state.app_settings
    title = str((job.payload_json or {}).get("title") or "")
    job.external_url = fetch_published_link(
        settings,
        platform=job.platform,
        account_name=account.account_name,
        title=title,
    )
    db.commit()
    db.refresh(job)
    return _job_read(
        job, settings.upload_dir, settings.resolved_publish_log_dir
    )


@router.patch("/jobs/{job_id}", response_model=PublishJobRead)
def patch_job(
    job_id: str,
    payload: PublishJobPatch,
    request: Request,
    db: Session = Depends(get_db),
) -> PublishJobRead:
    job = db.get(PublishJob, job_id)
    if job is None:
        raise AppError(404, "发布任务不存在", "PUBLISH_JOB_NOT_FOUND")

    if payload.status is not None:
        allowed = _MANUAL_TRANSITIONS.get(job.status, set())
        if payload.status not in allowed:
            raise AppError(
                409,
                f"任务当前状态为 {job.status}，不能手动改为 {payload.status}",
                "PUBLISH_STATUS_INVALID",
            )
        job.status = payload.status
        if payload.status in ("scheduled", "failed", "published"):
            job.finished_at = job.finished_at or utc_now()
    if payload.external_url is not None:
        job.external_url = payload.external_url
    db.commit()
    db.refresh(job)
    settings = request.app.state.app_settings
    return _job_read(
        job, settings.upload_dir, settings.resolved_publish_log_dir
    )


@router.get("/jobs/{job_id}/log", response_model=PublishJobLogRead)
def get_job_log(
    job_id: str, request: Request, db: Session = Depends(get_db)
) -> PublishJobLogRead:
    if db.get(PublishJob, job_id) is None:
        raise AppError(404, "发布任务不存在", "PUBLISH_JOB_NOT_FOUND")
    settings = request.app.state.app_settings
    path = _log_path(settings.resolved_publish_log_dir, job_id)
    if not path.is_file():
        return PublishJobLogRead(job_id=job_id, text="", truncated=False)
    data = path.read_bytes()
    text = strip_ansi(data.decode("utf-8", errors="replace"))
    max_chars = 100_000
    truncated = len(text) > max_chars
    return PublishJobLogRead(
        job_id=job_id,
        text=text[-max_chars:] if truncated else text,
        truncated=truncated,
    )
