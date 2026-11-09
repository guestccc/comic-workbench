"""设计建议库：建议 CRUD、应用记录与改前 / 改后快照。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..config import MAX_DESIGN_FEEDBACK_APPLICATIONS
from ..errors import AppError
from ..models import DesignFeedback, DesignFeedbackApplication, DesignRule, Story, utc_now
from ..schemas import (
    DesignFeedbackApplicationCreate,
    DesignFeedbackCreate,
    DesignFeedbackRulePromote,
    DesignRuleCreate,
    DesignFeedbackUpdate,
)
from .files import delete_cover_file, validate_cover_filename


def _derive_title(content: str) -> str:
    """建议标题只是展示标签；用户不填时从原文首行或截图生成。"""
    first_line = next(
        (line.strip() for line in content.splitlines() if line.strip()), ""
    )
    if first_line:
        return first_line[:40]
    return f"截图建议 · {datetime.now().strftime('%m-%d %H:%M')}"


def _screenshot_url(upload_dir: Path, filename: str | None) -> str | None:
    if not filename:
        return None
    if not (upload_dir / filename).is_file():
        return None
    return f"/uploads/{filename}"


def _normalize_scope(
    scope: str,
    story_id: int | None,
    chapter_number: int | None,
) -> tuple[int | None, int | None]:
    """按范围规范化故事 / 章节绑定，返回最终写入值。"""
    if scope == "global":
        return None, None
    if scope == "story":
        if story_id is None:
            raise AppError(
                422,
                "指定故事的建议必须选择故事",
                "DESIGN_FEEDBACK_STORY_REQUIRED",
            )
        return story_id, None
    if scope == "chapter":
        if story_id is None or chapter_number is None:
            raise AppError(
                422,
                "指定章节的建议必须同时选择故事和章节号",
                "DESIGN_FEEDBACK_CHAPTER_REQUIRED",
            )
        return story_id, chapter_number
    raise AppError(422, "建议范围不合法", "DESIGN_FEEDBACK_SCOPE_INVALID")


def _ensure_story(db: Session, story_id: int | None) -> Story | None:
    if story_id is None:
        return None
    story = db.get(Story, story_id)
    if story is None:
        raise AppError(404, "故事不存在或已被删除", "STORY_NOT_FOUND")
    return story


def _story_names(db: Session, story_ids: set[int]) -> dict[int, str]:
    if not story_ids:
        return {}
    rows = db.execute(
        select(Story.id, Story.name).where(Story.id.in_(story_ids))
    ).all()
    return {story_id: name for story_id, name in rows}


def _feedback_read(
    feedback: DesignFeedback,
    *,
    upload_dir: Path,
    story_name: str | None,
    application_count: int,
) -> dict:
    return {
        "id": feedback.id,
        "title": feedback.title,
        "content": feedback.content,
        "source": feedback.source,
        "source_url": feedback.source_url,
        "screenshot_filename": feedback.screenshot_filename,
        "screenshot_url": _screenshot_url(upload_dir, feedback.screenshot_filename),
        "category": feedback.category,
        "scope": feedback.scope,
        "story_id": feedback.story_id,
        "story_name": story_name,
        "chapter_number": feedback.chapter_number,
        "tags": feedback.tags or [],
        "priority": feedback.priority,
        "status": feedback.status,
        "application_count": application_count,
        "is_rule": feedback.is_rule,
        "rule_text": feedback.rule_text,
        "rule_target": feedback.rule_target,
        "rule_promoted_at": feedback.rule_promoted_at,
        "created_at": feedback.created_at,
        "updated_at": feedback.updated_at,
    }


def _application_read(
    application: DesignFeedbackApplication,
    story_name: str | None,
) -> dict:
    return {
        "id": application.id,
        "feedback_id": application.feedback_id,
        "target_type": application.target_type,
        "story_id": application.story_id,
        "story_name": story_name,
        "chapter_number": application.chapter_number,
        "page_number": application.page_number,
        "summary": application.summary,
        "before_prompt": application.before_prompt,
        "after_prompt": application.after_prompt,
        "before_image_url": application.before_image_url,
        "after_image_url": application.after_image_url,
        "applied_at": application.applied_at,
    }


def list_design_feedbacks(
    db: Session,
    upload_dir: Path,
    *,
    status: str | None = None,
    category: str | None = None,
    story_id: int | None = None,
    scope: str | None = None,
    keyword: str | None = None,
) -> list[dict]:
    stmt = select(DesignFeedback)
    if status:
        stmt = stmt.where(DesignFeedback.status == status)
    if category:
        stmt = stmt.where(DesignFeedback.category == category)
    if story_id is not None:
        stmt = stmt.where(DesignFeedback.story_id == story_id)
    if scope:
        stmt = stmt.where(DesignFeedback.scope == scope)
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                DesignFeedback.title.ilike(pattern),
                DesignFeedback.content.ilike(pattern),
            )
        )
    stmt = stmt.order_by(
        DesignFeedback.created_at.desc(), DesignFeedback.id.desc()
    )
    feedbacks = list(db.scalars(stmt).all())

    counts: dict[int, int] = {}
    story_ids = {item.story_id for item in feedbacks if item.story_id is not None}
    if feedbacks:
        counts = dict(
            db.execute(
                select(
                    DesignFeedbackApplication.feedback_id,
                    func.count(DesignFeedbackApplication.id),
                )
                .where(
                    DesignFeedbackApplication.feedback_id.in_(
                        [item.id for item in feedbacks]
                    )
                )
                .group_by(DesignFeedbackApplication.feedback_id)
            ).all()
        )
    names = _story_names(db, story_ids)
    return [
        _feedback_read(
            feedback,
            upload_dir=upload_dir,
            story_name=names.get(feedback.story_id or 0),
            application_count=counts.get(feedback.id, 0),
        )
        for feedback in feedbacks
    ]


def get_design_feedback_detail(
    db: Session, upload_dir: Path, feedback_id: int
) -> dict:
    feedback = db.get(DesignFeedback, feedback_id)
    if feedback is None:
        raise AppError(404, "设计建议不存在或已被删除", "DESIGN_FEEDBACK_NOT_FOUND")
    applications = list(
        db.scalars(
            select(DesignFeedbackApplication)
            .where(DesignFeedbackApplication.feedback_id == feedback_id)
            .order_by(
                DesignFeedbackApplication.applied_at.desc(),
                DesignFeedbackApplication.id.desc(),
            )
        ).all()
    )
    story_ids = {item.story_id for item in applications}
    if feedback.story_id is not None:
        story_ids.add(feedback.story_id)
    names = _story_names(db, story_ids)
    result = _feedback_read(
        feedback,
        upload_dir=upload_dir,
        story_name=names.get(feedback.story_id or 0),
        application_count=len(applications),
    )
    result["applications"] = [
        _application_read(item, names.get(item.story_id)) for item in applications
    ]
    return result


def create_design_feedback(
    db: Session, upload_dir: Path, payload: DesignFeedbackCreate
) -> dict:
    validate_cover_filename(payload.screenshot_filename, upload_dir)
    story_id, chapter_number = _normalize_scope(
        payload.scope, payload.story_id, payload.chapter_number
    )
    _ensure_story(db, story_id)
    feedback = DesignFeedback(
        title=payload.title or _derive_title(payload.content),
        content=payload.content,
        source=payload.source,
        source_url=payload.source_url,
        screenshot_filename=payload.screenshot_filename,
        category=payload.category,
        scope=payload.scope,
        story_id=story_id,
        chapter_number=chapter_number,
        tags=payload.tags,
        priority=payload.priority,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return get_design_feedback_detail(db, upload_dir, feedback.id)


def update_design_feedback(
    db: Session,
    upload_dir: Path,
    feedback_id: int,
    payload: DesignFeedbackUpdate,
) -> dict:
    feedback = db.get(DesignFeedback, feedback_id)
    if feedback is None:
        raise AppError(404, "设计建议不存在或已被删除", "DESIGN_FEEDBACK_NOT_FOUND")

    data = payload.model_dump(exclude_unset=True)
    old_screenshot = feedback.screenshot_filename
    if "screenshot_filename" in data:
        validate_cover_filename(data["screenshot_filename"], upload_dir)

    for field in (
        "title",
        "content",
        "source",
        "source_url",
        "screenshot_filename",
        "category",
        "priority",
        "status",
    ):
        if field in data:
            setattr(feedback, field, data[field])

    scope = data.get("scope", feedback.scope)
    story_id = data.get("story_id", feedback.story_id)
    chapter_number = data.get("chapter_number", feedback.chapter_number)
    story_id, chapter_number = _normalize_scope(
        scope, story_id, chapter_number
    )
    _ensure_story(db, story_id)
    feedback.scope = scope
    feedback.story_id = story_id
    feedback.chapter_number = chapter_number
    if "tags" in data:
        feedback.tags = data["tags"] or []

    if not (feedback.content or "").strip() and not feedback.screenshot_filename:
        raise AppError(
            422,
            "建议原文和截图至少填一个",
            "DESIGN_FEEDBACK_MATERIAL_REQUIRED",
        )
    if not (feedback.title or "").strip():
        feedback.title = _derive_title(feedback.content or "")

    db.commit()
    db.refresh(feedback)
    if old_screenshot and old_screenshot != feedback.screenshot_filename:
        delete_cover_file(old_screenshot, upload_dir)
    return get_design_feedback_detail(db, upload_dir, feedback.id)


def delete_design_feedback(
    db: Session, upload_dir: Path, feedback_id: int
) -> None:
    feedback = db.get(DesignFeedback, feedback_id)
    if feedback is None:
        raise AppError(404, "设计建议不存在或已被删除", "DESIGN_FEEDBACK_NOT_FOUND")
    screenshot = feedback.screenshot_filename
    db.delete(feedback)
    db.commit()
    delete_cover_file(screenshot, upload_dir)


def create_design_feedback_application(
    db: Session,
    upload_dir: Path,
    feedback_id: int,
    payload: DesignFeedbackApplicationCreate,
) -> dict:
    feedback = db.get(DesignFeedback, feedback_id)
    if feedback is None:
        raise AppError(404, "设计建议不存在或已被删除", "DESIGN_FEEDBACK_NOT_FOUND")
    story = _ensure_story(db, payload.story_id)
    count = db.scalar(
        select(func.count(DesignFeedbackApplication.id)).where(
            DesignFeedbackApplication.feedback_id == feedback_id
        )
    )
    if count is not None and count >= MAX_DESIGN_FEEDBACK_APPLICATIONS:
        raise AppError(
            422,
            f"单条建议最多记录 {MAX_DESIGN_FEEDBACK_APPLICATIONS} 次应用",
            "DESIGN_FEEDBACK_APPLICATION_LIMIT",
        )
    if payload.target_type != "page" and payload.page_number is not None:
        raise AppError(
            422,
            "只有正文页应用可以填写页码",
            "DESIGN_FEEDBACK_PAGE_NOT_APPLICABLE",
        )
    application = DesignFeedbackApplication(
        feedback_id=feedback_id,
        target_type=payload.target_type,
        story_id=payload.story_id,
        chapter_number=payload.chapter_number,
        page_number=payload.page_number,
        summary=payload.summary,
        before_prompt=payload.before_prompt,
        after_prompt=payload.after_prompt,
        before_image_url=payload.before_image_url,
        after_image_url=payload.after_image_url,
    )
    db.add(application)
    if feedback.status == "open":
        feedback.status = "applied"
    db.commit()
    db.refresh(application)
    return _application_read(application, story.name if story else None)


def delete_design_feedback_application(
    db: Session, feedback_id: int, application_id: int
) -> None:
    feedback = db.get(DesignFeedback, feedback_id)
    if feedback is None:
        raise AppError(404, "设计建议不存在或已被删除", "DESIGN_FEEDBACK_NOT_FOUND")
    application = db.get(DesignFeedbackApplication, application_id)
    if application is None or application.feedback_id != feedback_id:
        raise AppError(
            404,
            "应用记录不存在或已被删除",
            "DESIGN_FEEDBACK_APPLICATION_NOT_FOUND",
        )
    db.delete(application)
    db.flush()
    remaining = db.scalar(
        select(func.count(DesignFeedbackApplication.id)).where(
            DesignFeedbackApplication.feedback_id == feedback_id
        )
    )
    if not remaining and feedback.status == "applied":
        feedback.status = "open"
    db.commit()


def promote_design_feedback(
    db: Session,
    upload_dir: Path,
    feedback_id: int,
    payload: DesignFeedbackRulePromote,
) -> dict:
    """兼容旧入口：创建一条简单规则并立即激活。

    新界面使用 /api/design-rules 的结构化草案；这里仅保留给旧调用方。
    """
    from . import design_rules as rule_service

    feedback = db.get(DesignFeedback, feedback_id)
    if feedback is None:
        raise AppError(404, "设计建议不存在或已被删除", "DESIGN_FEEDBACK_NOT_FOUND")
    target = {"cover": "cover", "comic": "body", "all": "all"}[
        payload.rule_target
    ]
    scope_type = feedback.scope
    chapter_numbers = (
        [feedback.chapter_number]
        if feedback.chapter_number is not None
        else []
    )
    if scope_type == "chapter" and not chapter_numbers:
        scope_type = "story" if feedback.story_id is not None else "global"
    rule = rule_service.create_rule(
        db,
        feedback_id,
        DesignRuleCreate(
            title=feedback.title,
            kind="prompt",
            target=target,
            slot="scene",
            scope_type=scope_type,
            story_id=feedback.story_id,
            chapter_numbers=chapter_numbers,
            priority="hard",
            requirement=payload.rule_text,
            created_by="user",
        ),
    )
    rule_service.set_rule_status(db, rule["id"], "active")
    feedback.is_rule = True
    feedback.rule_text = payload.rule_text
    feedback.rule_target = payload.rule_target
    feedback.rule_promoted_at = utc_now()
    feedback.status = "verified"
    db.commit()
    db.refresh(feedback)
    return get_design_feedback_detail(db, upload_dir, feedback.id)


def remove_design_feedback_rule(
    db: Session, upload_dir: Path, feedback_id: int
) -> dict:
    """取消规则；建议本身与历史应用记录保留。"""
    feedback = db.get(DesignFeedback, feedback_id)
    if feedback is None:
        raise AppError(404, "设计建议不存在或已被删除", "DESIGN_FEEDBACK_NOT_FOUND")
    from . import design_rules as rule_service

    active_rules = list(
        db.scalars(
            select(DesignRule).where(
                DesignRule.feedback_id == feedback_id,
                DesignRule.status == "active",
            )
        ).all()
    )
    for rule in active_rules:
        rule_service.set_rule_status(db, rule.id, "disabled")
    if feedback.status == "verified":
        count = db.scalar(
            select(func.count(DesignFeedbackApplication.id)).where(
                DesignFeedbackApplication.feedback_id == feedback_id
            )
        )
        feedback.status = "applied" if count else "open"
    feedback.is_rule = False
    feedback.rule_text = ""
    feedback.rule_promoted_at = None
    db.commit()
    db.refresh(feedback)
    return get_design_feedback_detail(db, upload_dir, feedback.id)


def list_active_rules(
    db: Session,
    *,
    target: str,
    story_id: int | None,
    chapter_number: int | None,
) -> list[str]:
    """返回当前目标可用的规则文本，按升级时间排序并去重。

    target: cover / comic；all 目标两边都生效。
    范围匹配：全局规则始终生效；故事规则匹配 story_id；
    章节规则同时匹配 story_id 与 chapter_number。
    """
    if target not in {"cover", "comic"}:
        return []
    scope_conditions = [DesignFeedback.scope == "global"]
    if story_id is not None:
        scope_conditions.append(
            and_(
                DesignFeedback.scope == "story",
                DesignFeedback.story_id == story_id,
            )
        )
        if chapter_number is not None:
            scope_conditions.append(
                and_(
                    DesignFeedback.scope == "chapter",
                    DesignFeedback.story_id == story_id,
                    DesignFeedback.chapter_number == chapter_number,
                )
            )
    rows = db.scalars(
        select(DesignFeedback)
        .where(
            DesignFeedback.is_rule.is_(True),
            DesignFeedback.rule_target.in_({target, "all"}),
            or_(*scope_conditions),
        )
        .order_by(
            DesignFeedback.rule_promoted_at.asc(),
            DesignFeedback.id.asc(),
        )
    ).all()
    rules: list[str] = []
    seen: set[str] = set()
    for row in rows:
        text = (row.rule_text or "").strip()
        if text and text not in seen:
            seen.add(text)
            rules.append(text)
    return rules
