"""设计规则落实检测：按规则范围扫描提示词，AI 判定后等待人工确认。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    DEEPSEEK_API_URL,
    DEEPSEEK_CONNECT_TIMEOUT,
    DEEPSEEK_MAX_TOKENS,
    DEEPSEEK_MODEL,
    DEEPSEEK_READ_TIMEOUT,
)
from ..crud import resolve_deepseek_key
from ..errors import AppError
from ..models import (
    DesignRule,
    DesignRuleCoverageRun,
    PromptRenderSnapshot,
    Story,
    StoryBreakdown,
)
from .design_rules import evaluate_check_rules

logger = logging.getLogger("comic_workbench")

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rule-coverage")
_AI_BATCH_SIZE = 5
_COVERAGE_PROMPT_MAX = 5000


def _now():
    return datetime.now(timezone.utc)


def scope_snapshot(rule: DesignRule) -> dict:
    return {
        "rule_id": rule.id,
        "title": rule.title,
        "kind": rule.kind,
        "target": rule.target,
        "scope_type": rule.scope_type,
        "story_id": rule.story_id,
        "chapter_numbers": list(rule.chapter_numbers or []),
        "page_numbers": list(rule.page_numbers or []),
        "version": rule.version,
    }


def _chapter_in_scope(rule: DesignRule, chapter_number: int) -> bool:
    if rule.scope_type in ("global", "story"):
        return True
    return chapter_number in set(rule.chapter_numbers or [])


def _page_in_scope(rule: DesignRule, chapter_number: int, page_number: int) -> bool:
    if rule.scope_type == "pages":
        return (
            chapter_number in set(rule.chapter_numbers or [])
            and page_number in set(rule.page_numbers or [])
        )
    return _chapter_in_scope(rule, chapter_number)


def expand_rule_assets(db: Session, rule: DesignRule) -> list[dict]:
    """把规则范围展开成具体提示词资产。"""
    stmt = select(Story).order_by(Story.id.asc())
    if rule.scope_type != "global" and rule.story_id is not None:
        stmt = stmt.where(Story.id == rule.story_id)
    stories = list(db.scalars(stmt).all())
    story_ids = [story.id for story in stories]
    if not story_ids:
        return []
    breakdowns = list(
        db.scalars(
            select(StoryBreakdown).where(StoryBreakdown.story_id.in_(story_ids))
        ).all()
    )
    by_story = {item.story_id: item for item in breakdowns}
    assets: list[dict] = []
    for story in stories:
        breakdown = by_story.get(story.id)
        if breakdown is None:
            continue
        chapters = list(breakdown.chapters or [])
        pages = list(breakdown.pages or [])
        for chapter in chapters:
            chapter_number = chapter.get("chapter_number")
            if chapter_number is None or not _chapter_in_scope(rule, chapter_number):
                continue
            if rule.target in ("cover", "all"):
                cover = chapter.get("cover") or {}
                assets.append(
                    {
                        "item_key": f"cover:{story.id}:{chapter_number}",
                        "story_id": story.id,
                        "story_name": story.name,
                        "target_type": "cover",
                        "chapter_number": chapter_number,
                        "page_number": None,
                        "chapter_title": chapter.get("title") or "",
                        "prompt": str(cover.get("image_prompt") or ""),
                        "context": {
                            "target_type": "cover",
                            "chapter_number": chapter_number,
                            "page_number": None,
                            "chapter_title": chapter.get("title") or "",
                            "narration_main": (cover or {}).get("narration_main") or "",
                            "narration_sub": (cover or {}).get("narration_sub") or "",
                        },
                    }
                )
            if rule.target in ("guide", "all"):
                guide = chapter.get("guide") or {}
                assets.append(
                    {
                        "item_key": f"guide:{story.id}:{chapter_number}",
                        "story_id": story.id,
                        "story_name": story.name,
                        "target_type": "guide",
                        "chapter_number": chapter_number,
                        "page_number": None,
                        "chapter_title": chapter.get("title") or "",
                        "prompt": str(guide.get("image_prompt") or ""),
                        "context": {
                            "target_type": "guide",
                            "chapter_number": chapter_number,
                            "page_number": None,
                            "chapter_title": chapter.get("title") or "",
                            "narration_main": (guide or {}).get("text") or "",
                            "narration_sub": (guide or {}).get("sub_text") or "",
                        },
                    }
                )
        if rule.target in ("body", "all"):
            for page in pages:
                chapter_number = page.get("chapter_number")
                page_number = page.get("chapter_page_number")
                if chapter_number is None or page_number is None:
                    continue
                if not _page_in_scope(rule, chapter_number, page_number):
                    continue
                assets.append(
                    {
                        "item_key": (
                            f"page:{story.id}:{chapter_number}:{page_number}"
                        ),
                        "story_id": story.id,
                        "story_name": story.name,
                        "target_type": "body",
                        "chapter_number": chapter_number,
                        "page_number": page_number,
                        "chapter_title": "",
                        "prompt": str(page.get("image_prompt") or ""),
                        "context": {
                            "target_type": "body",
                            "chapter_number": chapter_number,
                            "page_number": page_number,
                            "page_role": page.get("page_role") or "",
                            "characters": page.get("characters") or [],
                            "scene": page.get("scene") or "",
                            "narration_main": page.get("narration_main") or "",
                            "narration_sub": page.get("narration_sub") or "",
                        },
                    }
                )
    return assets


def _latest_snapshot(db: Session, asset: dict) -> PromptRenderSnapshot | None:
    if asset["target_type"] == "guide":
        return None
    stmt = select(PromptRenderSnapshot).where(
        PromptRenderSnapshot.story_id == asset["story_id"],
        PromptRenderSnapshot.target_type == asset["target_type"],
        PromptRenderSnapshot.chapter_number == asset["chapter_number"],
    )
    if asset["target_type"] == "body":
        stmt = stmt.where(
            PromptRenderSnapshot.page_number == asset["page_number"]
        )
    else:
        stmt = stmt.where(PromptRenderSnapshot.page_number.is_(None))
    return db.scalar(
        stmt.order_by(
            PromptRenderSnapshot.created_at.desc(),
            PromptRenderSnapshot.id.desc(),
        ).limit(1)
    )


def _deterministic(db: Session, rule: DesignRule, asset: dict) -> dict:
    prompt = asset["prompt"]
    if not prompt.strip():
        return {"status": "not_generated", "message": "提示词为空"}
    snapshot = _latest_snapshot(db, asset)
    applied = False
    prompt_matches = False
    checks: list[dict] = []
    if snapshot is not None:
        applied = any(
            str(item.get("id")) == str(rule.id)
            for item in (snapshot.applied_rules or [])
        )
        prompt_matches = (snapshot.prompt or "").strip() == prompt.strip()
        if prompt_matches:
            checks = list(snapshot.rule_checks or [])
    if not checks:
        checks = evaluate_check_rules([rule], prompt, asset.get("context") or {})
    check_failed = any(item.get("passed") is False for item in checks)
    missing_terms = [
        term for term in (rule.negative_terms or []) if term and term not in prompt
    ]
    status = "ok"
    message = ""
    if check_failed:
        status = "check_failed"
        message = next(
            (item.get("message") or "硬检查未通过" for item in checks if item.get("passed") is False),
            "硬检查未通过",
        )
    elif missing_terms:
        status = "negative_missing"
        message = "缺少负面约束：" + "、".join(missing_terms)
    return {
        "status": status,
        "message": message,
        "snapshot_id": snapshot.id if snapshot is not None else None,
        "has_snapshot": snapshot is not None,
        "prompt_matches_snapshot": prompt_matches,
        "rule_applied": applied,
        "checks": checks,
        "negative_missing": missing_terms,
    }


_SYSTEM_PROMPT = """你是条漫工作台的提示词落实审片员。
你的任务：判断一条设计规则是否已经在给定提示词中被真正落实，而不是只判断规则文字有没有被复制进去。
只判断提示词，不判断成品图。
必须输出 JSON，不要输出 markdown 或解释。

输出结构：
{"results":[{"item_key":"原样返回","status":"covered|partial|missing|not_applicable","confidence":0.0,"evidence":["提示词中支持该规则的连续原文"],"missing":["没有落实的具体点"],"suggested_fix":"提示词应补什么","reason":"一句话判断依据"}]}

判定标准：
- covered：规则要求在提示词里有明确、可执行的表达，evidence 必须引用原文；
- partial：只落实一部分，或表达模糊容易被模型忽略；
- missing：提示词没有体现该规则；
- not_applicable：该资产类型不适用这条规则。
没有 evidence 不得判 covered。confidence 取 0–1。"""


def _strip_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _ai_review_batch(
    db: Session, rule: DesignRule, assets: list[dict]
) -> dict[str, dict]:
    key, _source, _db_configured = resolve_deepseek_key(db)
    if not key:
        raise AppError(
            409,
            "尚未配置 AI Key，请先到「设置」页完成配置",
            "DEEPSEEK_KEY_MISSING",
        )
    rule_payload = {
        "title": rule.title,
        "kind": rule.kind,
        "target": rule.target,
        "requirement": rule.requirement,
        "negative_terms": rule.negative_terms or [],
        "review_check": rule.review_check,
        "check_spec": rule.check_spec or {},
    }
    asset_payload = []
    for asset in assets:
        prompt = asset["prompt"][:_COVERAGE_PROMPT_MAX]
        asset_payload.append(
            {
                "item_key": asset["item_key"],
                "target_type": asset["target_type"],
                "chapter_number": asset["chapter_number"],
                "page_number": asset["page_number"],
                "prompt": prompt,
                "context": asset["context"],
                "deterministic": {
                    "rule_applied": asset["deterministic"].get("rule_applied"),
                    "check_message": asset["deterministic"].get("message"),
                },
            }
        )
    user = json.dumps(
        {"rule": rule_payload, "assets": asset_payload},
        ensure_ascii=False,
    )
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": min(DEEPSEEK_MAX_TOKENS, 3000),
        "temperature": 0.2,
        "stream": False,
    }
    timeout = httpx.Timeout(
        DEEPSEEK_READ_TIMEOUT, connect=DEEPSEEK_CONNECT_TIMEOUT
    )
    response = httpx.post(
        DEEPSEEK_API_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if response.status_code != 200:
        raise AppError(
            502,
            f"AI 审片失败（HTTP {response.status_code}）：{response.text[:200]}",
            "DESIGN_COVERAGE_AI_ERROR",
        )
    try:
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(_strip_json(content))
        results = parsed["results"]
        if not isinstance(results, list):
            raise ValueError("results 不是数组")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            502,
            "AI 审片返回格式不正确",
            "DESIGN_COVERAGE_AI_BAD_OUTPUT",
        ) from exc
    by_key: dict[str, dict] = {}
    for item in results:
        if isinstance(item, dict) and item.get("item_key"):
            by_key[str(item["item_key"])] = item
    return by_key


def _make_item(rule: DesignRule, asset: dict, deterministic: dict) -> dict:
    prompt = asset["prompt"]
    return {
        "item_key": asset["item_key"],
        "story_id": asset["story_id"],
        "story_name": asset["story_name"],
        "target_type": asset["target_type"],
        "chapter_number": asset["chapter_number"],
        "page_number": asset["page_number"],
        "chapter_title": asset.get("chapter_title") or "",
        "prompt": prompt,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
        "deterministic": deterministic,
        "cached": False,
        "ai_status": "pending" if prompt.strip() else "not_generated",
        "ai_confidence": 0.0,
        "ai_evidence": [],
        "ai_missing": [],
        "ai_suggested_fix": "",
        "ai_reason": "",
        "confirm_status": "pending",
        "confirmed_at": None,
        "confirmation_note": "",
        "final_status": "not_generated" if not prompt.strip() else "pending_confirmation",
    }


def _recount(run: DesignRuleCoverageRun) -> None:
    items = run.items or []
    run.covered = sum(1 for item in items if item.get("ai_status") == "covered")
    run.partial = sum(1 for item in items if item.get("ai_status") == "partial")
    run.missing = sum(1 for item in items if item.get("ai_status") == "missing")
    run.error_count = sum(1 for item in items if item.get("ai_status") == "error")
    run.pending = sum(
        1
        for item in items
        if item.get("confirm_status") == "pending"
        and item.get("ai_status") not in ("not_generated", "pending", "error")
    )


def run_coverage(run_id: int, session_factory: Any) -> None:
    db: Session = session_factory()
    try:
        run = db.get(DesignRuleCoverageRun, run_id)
        if run is None:
            return
        rule = db.get(DesignRule, run.rule_id)
        if rule is None:
            run.status = "failed"
            run.error_message = "规则不存在"
            run.finished_at = _now()
            db.commit()
            return
        if run.status == "canceled":
            return
        run.status = "running"
        run.started_at = _now()
        db.commit()

        assets = expand_rule_assets(db, rule)
        run.total = len(assets)
        run.items = [
            _make_item(rule, asset, _deterministic(db, rule, asset))
            for asset in assets
        ]
        # 增量：复用同规则、同版本、同 prompt 哈希的 AI 结论，避免重复调用
        previous = db.scalar(
            select(DesignRuleCoverageRun)
            .where(
                DesignRuleCoverageRun.rule_id == rule.id,
                DesignRuleCoverageRun.status == "succeeded",
                DesignRuleCoverageRun.rule_version == rule.version,
                DesignRuleCoverageRun.id != run.id,
            )
            .order_by(
                DesignRuleCoverageRun.created_at.desc(),
                DesignRuleCoverageRun.id.desc(),
            )
            .limit(1)
        )
        cache: dict[str, dict] = {}
        if previous is not None:
            for old in previous.items or []:
                if old.get("prompt_hash") and old.get("ai_status") not in (
                    None,
                    "pending",
                    "not_generated",
                    "error",
                ):
                    cache[str(old["prompt_hash"])] = old
        for item in run.items:
            old = cache.get(item.get("prompt_hash") or "")
            if old is None:
                continue
            for field in (
                "ai_status",
                "ai_confidence",
                "ai_evidence",
                "ai_missing",
                "ai_suggested_fix",
                "ai_reason",
            ):
                item[field] = old.get(field)
            item["cached"] = True
            item["final_status"] = "pending_confirmation"
        _recount(run)
        db.commit()

        for start in range(0, len(assets), _AI_BATCH_SIZE):
            db.refresh(run)
            if run.status == "canceled":
                break
            batch_assets = assets[start : start + _AI_BATCH_SIZE]
            batch_items = run.items[start : start + _AI_BATCH_SIZE]
            reviewable = [
                (asset, item)
                for asset, item in zip(batch_assets, batch_items)
                if item["ai_status"] not in ("not_generated", "covered", "partial", "missing", "not_applicable")
            ]
            if not reviewable:
                continue
            try:
                ai_by_key = _ai_review_batch(
                    db, rule, [asset for asset, _item in reviewable]
                )
            except AppError as exc:
                for _asset, item in reviewable:
                    item["ai_status"] = "error"
                    item["ai_reason"] = exc.message
                    item["final_status"] = "error"
            else:
                for _asset, item in reviewable:
                    result = ai_by_key.get(item["item_key"]) or {}
                    status = str(result.get("status") or "missing")
                    if status not in ("covered", "partial", "missing", "not_applicable"):
                        status = "missing"
                    item["ai_status"] = status
                    item["ai_confidence"] = float(result.get("confidence") or 0)
                    item["ai_evidence"] = result.get("evidence") or []
                    item["ai_missing"] = result.get("missing") or []
                    item["ai_suggested_fix"] = str(result.get("suggested_fix") or "")
                    item["ai_reason"] = str(result.get("reason") or "")
                    item["final_status"] = "pending_confirmation"
            run.processed = min(start + len(batch_items), len(assets))
            _recount(run)
            db.commit()

        db.refresh(run)
        if run.status != "canceled":
            run.status = "succeeded"
        run.finished_at = _now()
        _recount(run)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("设计规则覆盖检测失败")
        try:
            run = db.get(DesignRuleCoverageRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error_message = str(exc)[:1000]
                run.finished_at = _now()
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()


def start_coverage_run(
    db: Session, rule: DesignRule, session_factory: Any
) -> DesignRuleCoverageRun:
    run = DesignRuleCoverageRun(
        rule_id=rule.id,
        feedback_id=rule.feedback_id,
        rule_version=rule.version,
        scope_snapshot=scope_snapshot(rule),
        status="queued",
        items=[],
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    _EXECUTOR.submit(run_coverage, run.id, session_factory)
    return run


def confirm_items(
    db: Session,
    run: DesignRuleCoverageRun,
    item_keys: list[str],
    status: str,
    note: str,
) -> DesignRuleCoverageRun:
    keys = set(item_keys)
    found = 0
    for item in run.items or []:
        if item.get("item_key") not in keys:
            continue
        found += 1
        item["confirm_status"] = "confirmed"
        item["confirmed_at"] = _now().isoformat().replace("+00:00", "Z")
        item["confirmation_note"] = note
        item["final_status"] = (
            "confirmed_covered" if status == "covered" else "confirmed_missing"
        )
    if found == 0:
        raise AppError(404, "没有找到要确认的检测项", "DESIGN_COVERAGE_ITEM_NOT_FOUND")
    _recount(run)
    db.commit()
    db.refresh(run)
    return run
