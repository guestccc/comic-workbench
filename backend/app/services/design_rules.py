"""结构化设计规则：草案、版本、范围预览、渲染匹配与编译。"""

from __future__ import annotations

import copy
import re

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import (
    DesignFeedback,
    DesignRule,
    DesignRuleCoverageRun,
    DesignRuleResult,
    DesignRuleRevision,
    Story,
    StoryBreakdown,
    utc_now,
)
from ..schemas import (
    DesignRuleCreate,
    DesignRuleOnceTarget,
    DesignRulePreviewRequest,
    DesignRuleResultCreate,
    DesignRuleUpdate,
    _validate_rule_scope,
)

EDITABLE_FIELDS = (
    "title",
    "kind",
    "target",
    "slot",
    "scope_type",
    "story_id",
    "chapter_numbers",
    "page_numbers",
    "priority",
    "requirement",
    "negative_terms",
    "review_check",
    "check_spec",
    "status",
)

PRIORITY_RANK = {"hard": 0, "soft": 1}
IGNORED = re.compile(r"[\s，。！？；：、「」『』“”‘’（）()…—·,.!?;:\"'-]")


def _count_chars(text: str) -> int:
    return len(IGNORED.sub("", text or ""))


def _rule_snapshot(rule: DesignRule) -> dict:
    return {
        field: getattr(rule, field)
        for field in EDITABLE_FIELDS
    } | {"version": rule.version}


def _save_revision(db: Session, rule: DesignRule, note: str) -> None:
    db.add(
        DesignRuleRevision(
            rule_id=rule.id,
            version=rule.version,
            snapshot=_rule_snapshot(rule),
            change_note=note,
        )
    )


def _story_name(db: Session, story_id: int | None) -> str | None:
    if story_id is None:
        return None
    story = db.get(Story, story_id)
    return story.name if story is not None else None


def _rule_read(
    db: Session,
    rule: DesignRule,
    feedback_title: str | None = None,
    result_stats: dict | None = None,
    coverage: dict | None = None,
) -> dict:
    stats = result_stats or {}
    coverage = coverage or {}
    return {
        "id": rule.id,
        "feedback_id": rule.feedback_id,
        "feedback_title": feedback_title,
        "title": rule.title,
        "kind": rule.kind,
        "target": rule.target,
        "slot": rule.slot,
        "scope_type": rule.scope_type,
        "story_id": rule.story_id,
        "story_name": _story_name(db, rule.story_id),
        "chapter_numbers": rule.chapter_numbers or [],
        "page_numbers": rule.page_numbers or [],
        "priority": rule.priority,
        "requirement": rule.requirement,
        "negative_terms": rule.negative_terms or [],
        "review_check": rule.review_check,
        "check_spec": rule.check_spec or {},
        "status": rule.status,
        "version": rule.version,
        "created_by": rule.created_by,
        "check_count": stats.get("check_count", 0),
        "passed_count": stats.get("passed_count", 0),
        "failed_count": stats.get("failed_count", 0),
        "latest_result": stats.get("latest_result"),
        "template_applied_at": rule.template_applied_at,
        "coverage_run_id": coverage.get("id"),
        "coverage_status": coverage.get("status"),
        "coverage_total": coverage.get("total", 0),
        "coverage_pending": coverage.get("pending", 0),
        "coverage_updated_at": coverage.get("created_at"),
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _ensure_story(db: Session, story_id: int | None) -> None:
    if story_id is not None and db.get(Story, story_id) is None:
        raise AppError(404, "故事不存在或已被删除", "STORY_NOT_FOUND")


def list_rules_for_feedback(db: Session, feedback_id: int) -> list[dict]:
    feedback = db.get(DesignFeedback, feedback_id)
    if feedback is None:
        raise AppError(404, "设计建议不存在或已被删除", "DESIGN_FEEDBACK_NOT_FOUND")
    rules = list(
        db.scalars(
            select(DesignRule)
            .where(DesignRule.feedback_id == feedback_id)
            .order_by(DesignRule.created_at.asc(), DesignRule.id.asc())
        ).all()
    )
    rule_ids = [rule.id for rule in rules]
    results = (
        list(
            db.scalars(
                select(DesignRuleResult)
                .where(DesignRuleResult.rule_id.in_(rule_ids))
                .order_by(DesignRuleResult.created_at.desc())
            ).all()
        )
        if rule_ids
        else []
    )
    stats: dict[int, dict] = {}
    for result in results:
        item = stats.setdefault(
            result.rule_id,
            {
                "check_count": 0,
                "passed_count": 0,
                "failed_count": 0,
                "latest_result": None,
            },
        )
        item["check_count"] += 1
        if result.result == "passed":
            item["passed_count"] += 1
        elif result.result == "failed":
            item["failed_count"] += 1
        if item["latest_result"] is None:
            item["latest_result"] = result.result
    coverage_by_rule: dict[int, dict] = {}
    if rule_ids:
        runs = list(
            db.scalars(
                select(DesignRuleCoverageRun)
                .where(DesignRuleCoverageRun.rule_id.in_(rule_ids))
                .order_by(
                    DesignRuleCoverageRun.created_at.desc(),
                    DesignRuleCoverageRun.id.desc(),
                )
            ).all()
        )
        for run in runs:
            coverage_by_rule.setdefault(
                run.rule_id,
                {
                    "id": run.id,
                    "status": run.status,
                    "total": run.total,
                    "pending": run.pending,
                    "created_at": run.created_at,
                },
            )
    return [
        _rule_read(
            db,
            rule,
            feedback.title,
            stats.get(rule.id),
            coverage_by_rule.get(rule.id),
        )
        for rule in rules
    ]


def get_rule(db: Session, rule_id: int) -> DesignRule:
    rule = db.get(DesignRule, rule_id)
    if rule is None:
        raise AppError(404, "设计规则不存在或已被删除", "DESIGN_RULE_NOT_FOUND")
    return rule


def create_rule(
    db: Session, feedback_id: int, payload: DesignRuleCreate
) -> dict:
    feedback = db.get(DesignFeedback, feedback_id)
    if feedback is None:
        raise AppError(404, "设计建议不存在或已被删除", "DESIGN_FEEDBACK_NOT_FOUND")
    _ensure_story(db, payload.story_id)
    rule = DesignRule(
        feedback_id=feedback_id,
        title=payload.title,
        kind=payload.kind,
        target=payload.target,
        slot=payload.slot,
        scope_type=payload.scope_type,
        story_id=payload.story_id,
        chapter_numbers=payload.chapter_numbers,
        page_numbers=payload.page_numbers,
        priority=payload.priority,
        requirement=payload.requirement,
        negative_terms=payload.negative_terms,
        review_check=payload.review_check,
        check_spec=payload.check_spec,
        status="draft",
        version=1,
        created_by=payload.created_by,
    )
    db.add(rule)
    db.flush()
    _save_revision(db, rule, "创建规则草案")
    db.commit()
    db.refresh(rule)
    return _rule_read(db, rule, feedback.title)


def update_rule(
    db: Session, rule_id: int, payload: DesignRuleUpdate
) -> dict:
    rule = get_rule(db, rule_id)
    current = {field: getattr(rule, field) for field in EDITABLE_FIELDS}
    data = payload.model_dump(exclude_unset=True)
    current.update(data)
    current["created_by"] = rule.created_by
    validated = DesignRuleCreate(**current)
    for field in EDITABLE_FIELDS:
        if field == "status":
            continue
        setattr(rule, field, getattr(validated, field))
    rule.version += 1
    _ensure_story(db, rule.story_id)
    _save_revision(db, rule, "编辑规则")
    db.commit()
    db.refresh(rule)
    return _rule_read(db, rule)


def set_rule_status(db: Session, rule_id: int, status: str) -> dict:
    rule = get_rule(db, rule_id)
    if status not in {"active", "disabled"}:
        raise AppError(422, "规则状态不合法", "DESIGN_RULE_STATUS_INVALID")
    if status == "active" and rule.template_applied_at is not None:
        raise AppError(
            422,
            "规则已写入模板；如需重新启用，请先恢复模板或新建规则",
            "DESIGN_RULE_TEMPLATE_APPLIED",
        )
    if rule.status == status:
        return _rule_read(db, rule)
    rule.status = status
    rule.version += 1
    _save_revision(db, rule, "激活规则" if status == "active" else "停用规则")
    db.commit()
    db.refresh(rule)
    return _rule_read(db, rule)


def delete_rule(db: Session, rule_id: int) -> None:
    rule = get_rule(db, rule_id)
    db.delete(rule)
    db.commit()


def rollback_rule(db: Session, rule_id: int) -> dict:
    rule = get_rule(db, rule_id)
    previous = db.scalar(
        select(DesignRuleRevision)
        .where(
            DesignRuleRevision.rule_id == rule_id,
            DesignRuleRevision.version < rule.version,
        )
        .order_by(DesignRuleRevision.version.desc())
        .limit(1)
    )
    if previous is None:
        raise AppError(422, "没有可回退的历史版本", "DESIGN_RULE_NO_HISTORY")
    snapshot = previous.snapshot or {}
    for field in EDITABLE_FIELDS:
        if field in snapshot:
            setattr(rule, field, snapshot[field])
    rule.version = rule.version + 1
    _ensure_story(db, rule.story_id)
    _save_revision(db, rule, f"回滚到 v{previous.version}")
    db.commit()
    db.refresh(rule)
    return _rule_read(db, rule)


def _matches_chapter(
    breakdown: StoryBreakdown,
    chapter_number: int,
    payload: DesignRulePreviewRequest,
) -> bool:
    if payload.scope_type == "global":
        return True
    if payload.scope_type == "story":
        return breakdown.story_id == payload.story_id
    if payload.scope_type in ("chapter", "pages"):
        return (
            breakdown.story_id == payload.story_id
            and chapter_number in set(payload.chapter_numbers)
        )
    return False


def preview_impact(
    db: Session, payload: DesignRulePreviewRequest
) -> dict:
    breakdowns = list(db.scalars(select(StoryBreakdown)).all())
    names = {
        story.id: story.name
        for story in db.scalars(select(Story)).all()
    }
    cover = 0
    body = 0
    guide = 0
    samples: list[str] = []

    def add_sample(text: str) -> None:
        if len(samples) < 6:
            samples.append(text)

    for breakdown in breakdowns:
        story_name = names.get(breakdown.story_id, f"故事 {breakdown.story_id}")
        chapters = breakdown.chapters or []
        pages = breakdown.pages or []
        matched_chapters = [
            chapter
            for chapter in chapters
            if _matches_chapter(
                breakdown, chapter.get("chapter_number", 0), payload
            )
        ]
        chapter_set = {
            chapter.get("chapter_number") for chapter in matched_chapters
        }
        matched_pages = [
            page
            for page in pages
            if page.get("chapter_number") in chapter_set
            and (
                payload.scope_type != "pages"
                or page.get("chapter_page_number") in set(payload.page_numbers)
            )
        ]
        if payload.target in ("cover", "all"):
            cover += len(matched_chapters)
            for chapter in matched_chapters:
                add_sample(
                    f"{story_name} · 第{chapter.get('chapter_number')}章封面"
                )
        if payload.target in ("body", "all"):
            body += len(matched_pages)
            for page in matched_pages:
                add_sample(
                    f"{story_name} · 第{page.get('chapter_number')}章"
                    f"第{page.get('chapter_page_number')}页"
                )
        if payload.target in ("guide", "all"):
            guide += len(matched_chapters)
            for chapter in matched_chapters:
                add_sample(
                    f"{story_name} · 第{chapter.get('chapter_number')}章引导卡"
                )
    return {
        "cover": cover,
        "body": body,
        "guide": guide,
        "total": cover + body + guide,
        "samples": samples,
    }


def matching_rules(
    db: Session,
    *,
    target: str,
    story_id: int,
    chapter_number: int | None,
    page_number: int | None,
) -> list[DesignRule]:
    rules = list(
        db.scalars(
            select(DesignRule).where(
                DesignRule.status == "active",
                DesignRule.target.in_({target, "all"}),
                or_(
                    DesignRule.scope_type == "global",
                    DesignRule.story_id == story_id,
                ),
            )
        ).all()
    )

    def matches(rule: DesignRule) -> bool:
        if rule.scope_type == "global":
            return True
        if rule.scope_type == "story":
            return rule.story_id == story_id
        if rule.scope_type == "chapter":
            return (
                rule.story_id == story_id
                and chapter_number is not None
                and chapter_number in (rule.chapter_numbers or [])
            )
        if rule.scope_type == "pages":
            return (
                rule.story_id == story_id
                and chapter_number is not None
                and page_number is not None
                and chapter_number in (rule.chapter_numbers or [])
                and page_number in (rule.page_numbers or [])
            )
        return False

    rules = [rule for rule in rules if matches(rule)]
    rules.sort(
        key=lambda rule: (
            PRIORITY_RANK.get(rule.priority, 9),
            rule.created_at,
            rule.id,
        )
    )
    return rules


def compile_rule_fragments(rules: list[DesignRule]) -> dict:
    fragments = {
        "scene": [],
        "cover_mode": [],
        "text_zone": [],
        "negative_terms": [],
        "applied": [],
    }
    for rule in rules:
        if rule.kind in ("prompt", "text") and rule.requirement.strip():
            if rule.slot == "cover_mode":
                fragments["cover_mode"].append(rule.requirement.strip())
            elif rule.slot == "text_zone":
                fragments["text_zone"].append(rule.requirement.strip())
            else:
                fragments["scene"].append(rule.requirement.strip())
        if rule.kind == "negative":
            fragments["negative_terms"].extend(rule.negative_terms or [])
        fragments["applied"].append(
            {
                "id": rule.id,
                "title": rule.title,
                "kind": rule.kind,
                "target": rule.target,
                "scope_type": rule.scope_type,
                "priority": rule.priority,
                "requirement": rule.requirement,
                "negative_terms": rule.negative_terms or [],
                "review_check": rule.review_check,
                "check_spec": rule.check_spec or {},
            }
        )
    return fragments


def evaluate_check_rules(
    rules: list[DesignRule], prompt: str, context: dict
) -> list[dict]:
    results: list[dict] = []
    for rule in rules:
        if rule.kind != "check":
            continue
        spec = rule.check_spec or {}
        check_type = spec.get("type")
        passed = True
        message = ""
        if check_type == "required_terms":
            terms = [str(term) for term in spec.get("terms") or []]
            missing = [term for term in terms if term not in prompt]
            passed = not missing
            if missing:
                message = "缺少必要词：" + "、".join(missing)
        elif check_type == "forbidden_terms":
            terms = [str(term) for term in spec.get("terms") or []]
            found = [term for term in terms if term in prompt]
            passed = not found
            if found:
                message = "出现禁用词：" + "、".join(found)
        elif check_type == "max_chars":
            field = str(spec.get("field") or "prompt")
            limit = int(spec.get("value") or 0)
            text = prompt if field == "prompt" else str(context.get(field) or "")
            count = _count_chars(text)
            passed = count <= limit
            if not passed:
                message = f"{field} {count} 字，超过上限 {limit}"
        elif check_type == "regex":
            pattern = str(spec.get("pattern") or "")
            try:
                passed = bool(re.search(pattern, prompt))
            except re.error:
                passed = False
                message = "正则表达式无效"
            if not passed and not message:
                message = "提示词未匹配正则：" + pattern
        results.append(
            {
                "rule_id": rule.id,
                "title": rule.title,
                "passed": passed,
                "message": message,
            }
        )
    return results


def _result_read(result: DesignRuleResult) -> dict:
    return {
        "id": result.id,
        "rule_id": result.rule_id,
        "story_id": result.story_id,
        "target_type": result.target_type,
        "chapter_number": result.chapter_number,
        "page_number": result.page_number,
        "result": result.result,
        "message": result.message,
        "image_url": result.image_url,
        "snapshot_id": result.snapshot_id,
        "reviewer": result.reviewer,
        "created_at": result.created_at,
    }


def create_rule_result(
    db: Session, rule_id: int, payload: DesignRuleResultCreate
) -> dict:
    rule = get_rule(db, rule_id)
    _ensure_story(db, payload.story_id)
    result = DesignRuleResult(
        rule_id=rule.id,
        story_id=payload.story_id,
        target_type=payload.target_type,
        chapter_number=payload.chapter_number,
        page_number=payload.page_number,
        result=payload.result,
        message=payload.message,
        image_url=payload.image_url,
        snapshot_id=payload.snapshot_id,
        reviewer=payload.reviewer,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return _result_read(result)


def list_rule_results(db: Session, rule_id: int) -> list[dict]:
    get_rule(db, rule_id)
    results = list(
        db.scalars(
            select(DesignRuleResult)
            .where(DesignRuleResult.rule_id == rule_id)
            .order_by(DesignRuleResult.created_at.desc())
        ).all()
    )
    return [_result_read(result) for result in results]


def _template_types(rule: DesignRule) -> list[str]:
    if rule.scope_type != "global":
        raise AppError(
            422,
            "只有全局规则可以写入全局模板；故事/章节/页面规则请保持规则形态",
            "DESIGN_RULE_TEMPLATE_SCOPE_INVALID",
        )
    if rule.kind not in ("prompt", "negative", "text"):
        raise AppError(
            422,
            "只有正面提示词 / 负面约束 / 文字规则可以写入模板",
            "DESIGN_RULE_TEMPLATE_KIND_INVALID",
        )
    if rule.status != "active":
        raise AppError(
            422,
            "请先激活规则，再写入模板",
            "DESIGN_RULE_TEMPLATE_NOT_ACTIVE",
        )
    if rule.target == "cover":
        return ["cover"]
    if rule.target == "body":
        return ["body"]
    if rule.target == "all":
        return ["body", "cover"]
    raise AppError(
        422,
        "引导卡规则暂不支持写入模板",
        "DESIGN_RULE_TEMPLATE_TARGET_INVALID",
    )


def _rule_template_block(rule: DesignRule) -> str:
    if rule.kind == "negative":
        terms = "、".join(rule.negative_terms or [])
        return f"【固定规则】\n- 禁止：{terms}"
    return f"【固定规则】\n- {rule.requirement.strip()}"


def _insert_template_block(template: str, block: str) -> str:
    if block in template:
        return template
    if "【固定规则】" in template:
        start = template.index("【固定规则】") + len("【固定规则】")
        next_section = template.find("\n【", start)
        insert_at = next_section if next_section != -1 else len(template)
        lines = block.splitlines()[1:]
        addition = "\n" + "\n".join(lines)
        return template[:insert_at] + addition + template[insert_at:]
    if "【负面提示词】" in template:
        index = template.index("【负面提示词】")
        return template[:index] + block + "\n" + template[index:]
    return template.rstrip() + "\n\n" + block


def preview_template_write(db: Session, rule_id: int) -> dict:
    rule = get_rule(db, rule_id)
    types = _template_types(rule)
    from .prompt_templates import get_prompt_templates

    templates = get_prompt_templates(db)
    block = _rule_template_block(rule)
    items = []
    for template_type in types:
        before = templates[template_type]
        after = _insert_template_block(before, block)
        items.append(
            {
                "template_type": template_type,
                "before": before,
                "after": after,
                "inserted_block": block,
            }
        )
    return {"items": items}


def apply_template_write(db: Session, rule_id: int) -> dict:
    rule = get_rule(db, rule_id)
    types = _template_types(rule)
    from .prompt_templates import (
        get_prompt_templates,
        save_prompt_templates,
    )

    templates = get_prompt_templates(db)
    block = _rule_template_block(rule)
    body = templates["body"]
    cover = templates["cover"]
    if "body" in types:
        body = _insert_template_block(body, block)
    if "cover" in types:
        cover = _insert_template_block(cover, block)
    saved = save_prompt_templates(db, body, cover)
    rule.status = "disabled"
    rule.template_applied_at = utc_now()
    rule.version += 1
    _save_revision(db, rule, "写入模板后停用")
    db.commit()
    db.refresh(rule)
    return {
        "templates": saved,
        "rule": _rule_read(db, rule),
        "applied_template_types": types,
    }


def _once_block(rule: DesignRule) -> str:
    if rule.kind == "negative":
        terms = "、".join(rule.negative_terms or [])
        return f"【本次规则】\n- 禁止：{terms}"
    return f"【本次规则】\n- {rule.requirement.strip()}"


def _insert_once_block(prompt: str, block: str) -> str:
    if block in prompt:
        return prompt
    if "【本次规则】" in prompt:
        start = prompt.index("【本次规则】") + len("【本次规则】")
        next_section = prompt.find("\n【", start)
        insert_at = next_section if next_section != -1 else len(prompt)
        lines = block.splitlines()[1:]
        addition = "\n" + "\n".join(lines)
        return prompt[:insert_at] + addition + prompt[insert_at:]
    if "【负面提示词】" in prompt:
        index = prompt.index("【负面提示词】")
        return prompt[:index] + block + "\n" + prompt[index:]
    return prompt.rstrip() + "\n\n" + block


def _validate_once_rule(rule: DesignRule) -> None:
    if rule.kind not in ("prompt", "negative", "text"):
        raise AppError(
            422,
            "只有正面提示词 / 负面约束 / 文字规则支持仅本次应用",
            "DESIGN_RULE_ONCE_KIND_INVALID",
        )
    if rule.status not in ("draft", "disabled"):
        raise AppError(
            422,
            "仅本次应用请使用草案或已停用规则；已激活规则会全局生效",
            "DESIGN_RULE_ONCE_STATUS_INVALID",
        )
    if rule.template_applied_at is not None:
        raise AppError(
            422,
            "规则已写入模板，不能再仅本次应用",
            "DESIGN_RULE_ONCE_TEMPLATE_APPLIED",
        )


def _resolve_once_target(
    db: Session, payload: DesignRuleOnceTarget
) -> tuple[StoryBreakdown, list[dict], dict, str]:
    _ensure_story(db, payload.story_id)
    breakdown = db.scalar(
        select(StoryBreakdown).where(
            StoryBreakdown.story_id == payload.story_id
        )
    )
    if breakdown is None:
        raise AppError(404, "故事拆解结果不存在", "BREAKDOWN_NOT_FOUND")
    if payload.target_type == "cover":
        chapters = copy.deepcopy(list(breakdown.chapters or []))
        target = next(
            (
                chapter
                for chapter in chapters
                if chapter.get("chapter_number") == payload.chapter_number
            ),
            None,
        )
        if target is None:
            raise AppError(404, "章节封面不存在", "ONCE_TARGET_NOT_FOUND")
        before = str((target.get("cover") or {}).get("image_prompt") or "")
        return breakdown, chapters, target, before

    pages = copy.deepcopy(list(breakdown.pages or []))
    target = next(
        (
            page
            for page in pages
            if page.get("chapter_number") == payload.chapter_number
            and page.get("chapter_page_number") == payload.page_number
        ),
        None,
    )
    if target is None:
        target = next(
            (
                page
                for page in pages
                if page.get("page_number") == payload.page_number
            ),
            None,
        )
    if target is None:
        raise AppError(404, "正文页不存在", "ONCE_TARGET_NOT_FOUND")
    before = str(target.get("image_prompt") or "")
    return breakdown, pages, target, before


def preview_once(
    db: Session, rule_id: int, payload: DesignRuleOnceTarget
) -> dict:
    rule = get_rule(db, rule_id)
    _validate_once_rule(rule)
    _, _, _, before = _resolve_once_target(db, payload)
    block = _once_block(rule)
    after = _insert_once_block(before, block)
    return {
        "target_type": payload.target_type,
        "story_id": payload.story_id,
        "chapter_number": payload.chapter_number,
        "page_number": payload.page_number,
        "before": before,
        "after": after,
        "inserted_block": block,
    }


def apply_once(
    db: Session, rule_id: int, payload: DesignRuleOnceTarget
) -> dict:
    rule = get_rule(db, rule_id)
    _validate_once_rule(rule)
    breakdown, items, target, before = _resolve_once_target(db, payload)
    block = _once_block(rule)
    after = _insert_once_block(before, block)
    if payload.target_type == "cover":
        target.setdefault("cover", {})["image_prompt"] = after
        breakdown.chapters = items
        template_type = "cover"
    else:
        target["image_prompt"] = after
        breakdown.pages = items
        template_type = "body"
    db.commit()

    from .prompt_snapshots import create_snapshot

    snapshot = create_snapshot(
        db,
        story_id=payload.story_id,
        template_type=template_type,
        context={
            "chapter_number": payload.chapter_number,
            "page_number": payload.page_number,
            "source": "once",
            "rule_id": rule.id,
        },
        prompt=after,
        applied_rules=[
            {
                "id": rule.id,
                "title": rule.title,
                "kind": rule.kind,
                "target": rule.target,
                "scope_type": rule.scope_type,
                "priority": rule.priority,
                "requirement": rule.requirement,
                "negative_terms": rule.negative_terms or [],
                "review_check": rule.review_check,
                "check_spec": rule.check_spec or {},
            }
        ],
        rule_checks=[],
    )
    db.add(
        DesignRuleResult(
            rule_id=rule.id,
            story_id=payload.story_id,
            target_type=payload.target_type,
            chapter_number=payload.chapter_number,
            page_number=payload.page_number,
            result="unknown",
            message="仅本次应用",
            snapshot_id=snapshot["id"],
            reviewer="user",
        )
    )
    db.commit()
    return {
        "rule": _rule_read(db, rule),
        "target_type": payload.target_type,
        "story_id": payload.story_id,
        "chapter_number": payload.chapter_number,
        "page_number": payload.page_number,
        "prompt": after,
    }


def migrate_legacy_rules(db: Session) -> None:
    """把旧版 feedback.is_rule 迁移成 draft 审片规则，避免历史建议丢失。"""
    feedbacks = list(
        db.scalars(
            select(DesignFeedback).where(DesignFeedback.is_rule.is_(True))
        ).all()
    )
    for feedback in feedbacks:
        existing = db.scalar(
            select(DesignRule.id).where(
                DesignRule.feedback_id == feedback.id
            )
        )
        if existing is not None:
            continue
        rule = DesignRule(
            feedback_id=feedback.id,
            title=feedback.title,
            kind="review",
            target="cover",
            slot="none",
            scope_type=feedback.scope if feedback.scope != "chapter" else "chapter",
            story_id=feedback.story_id,
            chapter_numbers=(
                [feedback.chapter_number]
                if feedback.chapter_number is not None
                else []
            ),
            priority="soft",
            requirement="",
            negative_terms=[],
            review_check=feedback.rule_text,
            check_spec={},
            status="draft",
            version=1,
            created_by="user",
        )
        db.add(rule)
        db.flush()
        _save_revision(db, rule, "从旧版规则迁移")
    db.commit()
