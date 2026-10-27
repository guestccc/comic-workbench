"""分镜对照审阅：草稿、决策与服务端应用。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import (
    MappingReview,
    Story,
    StoryBreakdown,
    StoryChapterPostConfig,
)
from ..schemas import (
    MappingReviewChange,
    MappingReviewCreate,
    MappingReviewDecisionUpdate,
    MappingReviewRead,
    MappingReviewSummary,
)
from .files import archive_story_chapter_assets

# 以下阈值与 .claude/skills/story-breakdown/mapping_check.py 保持一致
NORMALIZED_IGNORED = re.compile(
    r"[\s，。！？；：、「」『』“”‘’（）()…—·,.!?;:\"'-]"
)
TRANSITION_MARKERS = (
    "后来",
    "第二天",
    "当晚",
    "那晚",
    "与此同时",
    "几年后",
    "十年后",
    "十五年前",
    "上一世",
    "重生后",
    "回到",
    "那天",
    "次日",
    "从此",
    "不久后",
    "半个月后",
    "一个月后",
    "一年后",
)
RISK_RANK = {"low": 0, "medium": 1, "high": 2}
MAX_QUOTE_PAIRS = 2
MAX_SENTENCE_ENDS = 5
CJK_WARN = 60
CJK_STRONG_WARN = 90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mapping_hash(mapping: list[dict]) -> str:
    payload = json.dumps(
        mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    return NORMALIZED_IGNORED.sub("", text or "")


def _cjk_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text or ""))


def _message_count(text: str) -> int:
    text = text or ""
    quoted = len(re.findall(r"[「“][^」”]{1,300}[」”]", text))
    messages = len(re.findall(r"【[^】]{1,300}】", text))
    return quoted + messages


def _sentence_end_count(text: str) -> int:
    return len(re.findall(r"[。！？!?]", text or ""))


def _transition_markers(text: str) -> list[str]:
    return [marker for marker in TRANSITION_MARKERS if marker in (text or "")]


def _segment_risk(text: str) -> str:
    cjk = _cjk_count(text)
    if (
        cjk > CJK_STRONG_WARN
        or _message_count(text) > MAX_QUOTE_PAIRS
        or len(_transition_markers(text)) >= 2
    ):
        return "high"
    if cjk > CJK_WARN or _sentence_end_count(text) > MAX_SENTENCE_ENDS:
        return "medium"
    return "low"


def _max_risk(left: str, right: str) -> str:
    return left if RISK_RANK[left] >= RISK_RANK[right] else right


def _chapter_map(chapters: list[dict]) -> dict[int, int]:
    result: dict[int, int] = {}
    for chapter in chapters or []:
        number = chapter.get("chapter_number")
        for mapping_number in chapter.get("mapping_page_numbers") or []:
            result[mapping_number] = number
    return result


def _crosses_chapter(
    old_page_numbers: list[int], chapter_map: dict[int, int]
) -> bool:
    if not chapter_map:
        return False
    numbers = {chapter_map.get(number) for number in old_page_numbers}
    return None in numbers or len(numbers) > 1


def _validate_changes(
    changes: list[MappingReviewChange], mapping: list[dict]
) -> None:
    by_number = {
        item.get("page_number"): item for item in mapping
    }
    used: set[int] = set()
    seen_ids: set[str] = set()
    for change in changes:
        if change.id in seen_ids:
            raise AppError(
                422, f"变更 ID 重复：{change.id}", "MAPPING_REVIEW_INVALID_CHANGE"
            )
        seen_ids.add(change.id)
        for number in change.old_page_numbers:
            if number not in by_number:
                raise AppError(
                    422,
                    f"对照第 {number} 段不存在",
                    "MAPPING_REVIEW_INVALID_CHANGE",
                )
            if by_number[number].get("excluded"):
                raise AppError(
                    422,
                    f"对照第 {number} 段已弃用，不能拆并",
                    "MAPPING_REVIEW_INVALID_CHANGE",
                )
            if number in used:
                raise AppError(
                    422,
                    f"多个变更同时引用了对照第 {number} 段",
                    "MAPPING_REVIEW_INVALID_CHANGE",
                )
            used.add(number)

        if change.kind == "keep":
            if change.proposed_segments:
                raise AppError(
                    422,
                    f"变更 {change.id} 是 keep，不应包含新分段",
                    "MAPPING_REVIEW_INVALID_CHANGE",
                )
            continue

        if not change.proposed_segments:
            raise AppError(
                422,
                f"变更 {change.id} 必须提供新分段",
                "MAPPING_REVIEW_INVALID_CHANGE",
            )
        old_text = "".join(
            by_number[number].get("source_text") or ""
            for number in change.old_page_numbers
        )
        new_text = "".join(
            segment.source_text for segment in change.proposed_segments
        )
        if new_text != old_text:
            raise AppError(
                422,
                f"变更 {change.id} 的新分段拼接与原文不一致；"
                "只能移动边界，不能改写原文",
                "MAPPING_REVIEW_COVERAGE_INVALID",
            )


def _enrich_change(
    change: MappingReviewChange,
    chapter_map: dict[int, int],
) -> dict:
    risk = change.risk
    for segment in change.proposed_segments:
        risk = _max_risk(risk, _segment_risk(segment.source_text))
    if risk in ("high", "medium") and not change.reason.strip():
        raise AppError(
            422,
            f"变更 {change.id} 是 {risk} 风险，必须填写理由",
            "MAPPING_REVIEW_INVALID_CHANGE",
        )
    page_delta = (
        0
        if change.kind == "keep"
        else len(change.proposed_segments) - len(change.old_page_numbers)
    )
    data = change.model_dump()
    data["risk"] = risk
    data["page_delta"] = page_delta
    data["crosses_chapter"] = _crosses_chapter(
        change.old_page_numbers, chapter_map
    )
    return data


def _default_decisions(changes: list[dict]) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for change in changes:
        if change.get("kind") == "keep" or change.get("risk") == "low":
            decisions[change["id"]] = "approved"
        else:
            decisions[change["id"]] = "undecided"
    return decisions


def _summary(
    review: MappingReview,
    mapping: list[dict],
    chapters: list[dict],
) -> MappingReviewSummary:
    changes = review.proposal or []
    decisions = review.decisions or {}
    proposed = len(mapping)
    pending = 0
    auto_approved = 0
    rejected = 0
    for change in changes:
        decision = decisions.get(change.get("id"), "undecided")
        if decision == "approved":
            proposed += int(change.get("page_delta") or 0)
            if change.get("risk") == "low":
                auto_approved += 1
        elif decision == "rejected":
            rejected += 1
        else:
            pending += 1
    return MappingReviewSummary(
        current_page_count=len(mapping),
        proposed_page_count=proposed,
        total_changes=len(changes),
        pending_count=pending,
        auto_approved_count=auto_approved,
        rejected_count=rejected,
        chapters_count=len(chapters or []),
        chapters_locked=bool(chapters),
    )


def _to_read(
    review: MappingReview,
    mapping: list[dict],
    chapters: list[dict],
) -> MappingReviewRead:
    return MappingReviewRead(
        id=review.id,
        story_id=review.story_id,
        status=review.status,
        base_mapping_hash=review.base_mapping_hash,
        changes=[
            MappingReviewChange.model_validate(item)
            for item in (review.proposal or [])
        ],
        decisions=review.decisions or {},
        summary=_summary(review, mapping, chapters),
        created_at=review.created_at,
        updated_at=review.updated_at,
        applied_at=review.applied_at,
    )


def _get_review_row(db: Session, story_id: int) -> MappingReview:
    review = db.scalar(
        select(MappingReview).where(MappingReview.story_id == story_id)
    )
    if review is None:
        raise AppError(
            404, "还没有分镜对照审阅草稿", "MAPPING_REVIEW_NOT_FOUND"
        )
    return review


def _get_breakdown_or_404(
    db: Session, story_id: int
) -> StoryBreakdown:
    breakdown = db.scalar(
        select(StoryBreakdown).where(StoryBreakdown.story_id == story_id)
    )
    if breakdown is None:
        raise AppError(404, "该故事还没有拆解结果", "BREAKDOWN_NOT_FOUND")
    return breakdown


def create_or_replace_review(
    db: Session,
    story: Story,
    payload: MappingReviewCreate,
) -> MappingReviewRead:
    breakdown = _get_breakdown_or_404(db, story.id)
    mapping = sorted(
        breakdown.mapping or [], key=lambda item: item.get("page_number", 0)
    )
    if not mapping:
        raise AppError(
            422, "mapping 为空，不能创建审阅草稿", "MAPPING_REVIEW_MAPPING_EMPTY"
        )
    _validate_changes(payload.changes, mapping)
    chapter_map = _chapter_map(breakdown.chapters or [])
    changes = [
        _enrich_change(change, chapter_map)
        for change in payload.changes
    ]
    decisions = _default_decisions(changes)
    review = db.scalar(
        select(MappingReview).where(MappingReview.story_id == story.id)
    )
    if review is None:
        review = MappingReview(story_id=story.id)
        db.add(review)
    review.status = "draft"
    review.base_mapping_hash = _mapping_hash(mapping)
    review.proposal = changes
    review.decisions = decisions
    review.applied_at = None
    review.updated_at = _now()
    db.commit()
    db.refresh(review)
    return _to_read(review, mapping, breakdown.chapters or [])


def get_review(db: Session, story_id: int) -> MappingReviewRead:
    review = _get_review_row(db, story_id)
    breakdown = _get_breakdown_or_404(db, story_id)
    mapping = sorted(
        breakdown.mapping or [], key=lambda item: item.get("page_number", 0)
    )
    return _to_read(review, mapping, breakdown.chapters or [])


def update_decisions(
    db: Session,
    story_id: int,
    payload: MappingReviewDecisionUpdate,
) -> MappingReviewRead:
    review = _get_review_row(db, story_id)
    if review.status != "draft":
        raise AppError(
            409, "该审阅草稿已应用或已丢弃", "MAPPING_REVIEW_NOT_DRAFT"
        )
    valid_ids = {item.get("id") for item in (review.proposal or [])}
    for change_id in payload.decisions:
        if change_id not in valid_ids:
            raise AppError(
                422,
                f"未知变更 ID：{change_id}",
                "MAPPING_REVIEW_INVALID_CHANGE",
            )
    decisions = dict(review.decisions or {})
    decisions.update(payload.decisions)
    review.decisions = decisions
    review.updated_at = _now()
    db.commit()
    db.refresh(review)
    breakdown = _get_breakdown_or_404(db, story_id)
    mapping = sorted(
        breakdown.mapping or [], key=lambda item: item.get("page_number", 0)
    )
    return _to_read(review, mapping, breakdown.chapters or [])


def discard_review(db: Session, story_id: int) -> None:
    review = _get_review_row(db, story_id)
    db.delete(review)
    db.commit()


def apply_review(
    db: Session,
    story: Story,
    clear_chapters: bool,
    upload_dir: Path,
) -> tuple[StoryBreakdown, bool, bool]:
    """应用已同意变更，返回 (breakdown, 严格连续, 是否清空章节)。"""
    review = _get_review_row(db, story.id)
    if review.status != "draft":
        raise AppError(
            409, "该审阅草稿已应用或已丢弃", "MAPPING_REVIEW_NOT_DRAFT"
        )
    breakdown = _get_breakdown_or_404(db, story.id)
    mapping = sorted(
        breakdown.mapping or [], key=lambda item: item.get("page_number", 0)
    )
    if _mapping_hash(mapping) != review.base_mapping_hash:
        raise AppError(
            409,
            "mapping 已变化，请重新生成审阅草稿",
            "MAPPING_REVIEW_STALE",
        )
    if breakdown.pages:
        raise AppError(
            409,
            "已有分镜页，请先清空分镜页再应用对照变更",
            "MAPPING_REVIEW_PAGES_EXIST",
        )
    chapters = breakdown.chapters or []
    if chapters and not clear_chapters:
        raise AppError(
            409,
            "该故事已有章节规划；应用会清空章节与章节文案，请先确认",
            "MAPPING_REVIEW_CHAPTERS_LOCKED",
        )

    decisions = review.decisions or {}
    approved = [
        change
        for change in (review.proposal or [])
        if decisions.get(change.get("id")) == "approved"
        and change.get("kind") != "keep"
    ]
    if not approved:
        raise AppError(
            422, "没有已同意的变更", "MAPPING_REVIEW_NO_APPROVED_CHANGES"
        )

    by_number = {item.get("page_number"): item for item in mapping}
    used: set[int] = set()
    for change in approved:
        for number in change.get("old_page_numbers") or []:
            if number not in by_number or number in used:
                raise AppError(
                    422,
                    "审阅草稿与当前 mapping 不一致",
                    "MAPPING_REVIEW_STALE",
                )
            used.add(number)

    change_by_start = {
        change["old_page_numbers"][0]: change for change in approved
    }
    new_mapping: list[dict] = []
    index = 0
    while index < len(mapping):
        item = mapping[index]
        change = change_by_start.get(item.get("page_number"))
        if change is None:
            new_mapping.append(dict(item))
            index += 1
            continue
        for segment in change.get("proposed_segments") or []:
            new_mapping.append(
                {
                    "page_number": 0,
                    "source_text": segment.get("source_text") or "",
                    "summary": segment.get("summary") or "",
                    "paragraph": segment.get("paragraph") or "",
                    "part": segment.get("part") or "",
                    "excluded": False,
                }
            )
        index += len(change.get("old_page_numbers") or [])

    for number, item in enumerate(new_mapping, start=1):
        item["page_number"] = number

    joined = "".join(item.get("source_text") or "" for item in new_mapping)
    optimized = breakdown.optimized_content or ""
    if _normalize(joined) != _normalize(optimized):
        raise AppError(
            422,
            "应用后的 mapping 不能完整覆盖优化文，已取消",
            "MAPPING_REVIEW_COVERAGE_INVALID",
        )
    strict_coverage = joined == optimized

    chapters_cleared = bool(chapters)
    breakdown.mapping = new_mapping
    if chapters_cleared:
        breakdown.chapters = []
        db.execute(
            delete(StoryChapterPostConfig).where(
                StoryChapterPostConfig.story_id == story.id
            )
        )

    review.status = "applied"
    review.applied_at = _now()
    review.updated_at = _now()
    db.commit()
    db.refresh(breakdown)

    if chapters_cleared:
        archive_story_chapter_assets(upload_dir, story.id)
    return breakdown, strict_coverage, chapters_cleared
