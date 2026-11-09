"""敏感词词库、扫描与替换。

词库保存在 app_settings 的 JSON 列表中，扫描只做精确匹配：
按词长从长到短组成正则，命中后不再匹配其中的短词，避免重叠替换。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..crud import get_setting, upsert_setting
from ..errors import AppError
from .sensitive_word_defaults import default_sensitive_words

SENSITIVE_WORDS_KEY = "sensitive_words"
MAX_SENSITIVE_WORDS = 5000
MAX_WORD_LENGTH = 50
MAX_REPLACEMENT_LENGTH = 100


def _normalize_word(item: dict) -> dict | None:
    word = str(item.get("word") or "").strip()
    if not word or len(word) > MAX_WORD_LENGTH:
        return None
    replacement = str(item.get("replacement") or "")[:MAX_REPLACEMENT_LENGTH]
    category = str(item.get("category") or "").strip()[:50]
    return {
        "word": word,
        "replacement": replacement,
        "category": category,
        "enabled": bool(item.get("enabled", True)),
    }


def load_sensitive_words(db: Session) -> list[dict]:
    row = get_setting(db, SENSITIVE_WORDS_KEY)
    # 未初始化时给商业合规默认包；用户保存过 [] 时保持明确清空。
    if row is None or not row.value.strip():
        return default_sensitive_words()
    try:
        parsed = json.loads(row.value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    words: list[dict] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_word(item)
        if normalized is None:
            continue
        key = normalized["word"].casefold()
        if key in seen:
            continue
        seen.add(key)
        words.append(normalized)
    return words[:MAX_SENSITIVE_WORDS]


def save_sensitive_words(db: Session, words: list[dict]) -> list[dict]:
    if len(words) > MAX_SENSITIVE_WORDS:
        raise AppError(
            422,
            f"敏感词最多 {MAX_SENSITIVE_WORDS} 条",
            "SENSITIVE_WORD_TOO_MANY",
        )
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in words:
        word = _normalize_word(item)
        if word is None:
            raise AppError(422, "敏感词不能为空，且不能超过 50 字", "SENSITIVE_WORD_INVALID")
        key = word["word"].casefold()
        if key in seen:
            raise AppError(
                422,
                f"敏感词「{word['word']}」重复",
                "SENSITIVE_WORD_DUPLICATE",
            )
        seen.add(key)
        normalized.append(word)
    upsert_setting(db, SENSITIVE_WORDS_KEY, json.dumps(normalized, ensure_ascii=False))
    db.commit()
    return normalized


def dictionary_version(words: list[dict]) -> str:
    enabled = [
        {
            "word": item["word"],
            "replacement": item["replacement"],
            "category": item["category"],
        }
        for item in words
        if item.get("enabled", True)
    ]
    payload = json.dumps(enabled, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _enabled_words(words: list[dict]) -> list[dict]:
    return [item for item in words if item.get("enabled", True) and item["word"]]


def _match_words(text: str, words: list[dict]) -> list[dict]:
    enabled = _enabled_words(words)
    if not text or not enabled:
        return []
    # 长词优先；同一位置不会被短词截胡。
    ordered = sorted(enabled, key=lambda item: (-len(item["word"]), item["word"]))
    pattern = re.compile(
        "|".join(re.escape(item["word"]) for item in ordered),
        re.IGNORECASE,
    )
    by_fold = {item["word"].casefold(): item for item in ordered}
    matches: list[dict] = []
    for match in pattern.finditer(text):
        item = by_fold.get(match.group(0).casefold())
        if item is None:
            continue
        matches.append(
            {
                "word": item["word"],
                "replacement": item["replacement"],
                "category": item["category"],
                "start": match.start(),
                "end": match.end(),
            }
        )
    return matches


def scan_text(text: str, words: list[dict]) -> dict:
    matches = _match_words(text, words)
    counts: dict[str, int] = {}
    for match in matches:
        counts[match["word"]] = counts.get(match["word"], 0) + 1
    return {
        "matches": matches,
        "total": len(matches),
        "counts": counts,
        "dictionary_version": dictionary_version(words),
    }


def apply_text(text: str, words: list[dict], items: list[dict]) -> tuple[str, list[dict]]:
    if not items:
        raise AppError(422, "请至少选择一个要替换的词", "SENSITIVE_WORD_SELECTION_EMPTY")
    available = {item["word"]: item for item in _enabled_words(words)}
    replacements: dict[str, str] = {}
    for item in items:
        word = str(item.get("word") or "").strip()
        if word not in available:
            raise AppError(
                422,
                f"敏感词「{word}」不在词库中或已停用",
                "SENSITIVE_WORD_NOT_FOUND",
            )
        replacement = str(item.get("replacement") or "")[:MAX_REPLACEMENT_LENGTH]
        replacements[word] = replacement

    matches = [m for m in _match_words(text, words) if m["word"] in replacements]
    if not matches:
        raise AppError(
            422,
            "所选敏感词在原文中没有命中",
            "SENSITIVE_WORD_NO_MATCH",
        )
    counts: dict[str, int] = {}
    result = text
    # 从后往前替换，前面的位置不会因文本长度变化而失效。
    for match in reversed(matches):
        result = result[: match["start"]] + replacements[match["word"]] + result[match["end"] :]
        counts[match["word"]] = counts.get(match["word"], 0) + 1
    applied = [
        {
            "word": word,
            "replacement": replacement,
            "count": counts.get(word, 0),
        }
        for word, replacement in replacements.items()
        if counts.get(word, 0) > 0
    ]
    return result, applied


def build_sensitive_edit(
    original: str,
    result: str,
    items: list[dict],
    version: str,
) -> dict:
    return {
        "original_content": original,
        "result_content": result,
        "items": items,
        "applied_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dictionary_version": version,
    }
