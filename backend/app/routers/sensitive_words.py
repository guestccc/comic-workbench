"""敏感词词库、扫描与无故事上下文的替换接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    SensitiveApplyRequest,
    SensitiveApplyResult,
    SensitiveScanRequest,
    SensitiveScanResult,
    SensitiveWordsPayload,
    SensitiveWordsRead,
)
from ..services.sensitive_word_defaults import default_sensitive_words
from ..services.sensitive_words import (
    apply_text,
    build_sensitive_edit,
    dictionary_version,
    load_sensitive_words,
    save_sensitive_words,
    scan_text,
)

router = APIRouter(prefix="/api", tags=["敏感词"])


@router.get("/settings/sensitive-words", response_model=SensitiveWordsRead)
def read_sensitive_words(db: Session = Depends(get_db)) -> SensitiveWordsRead:
    return SensitiveWordsRead(words=load_sensitive_words(db))


@router.get(
    "/settings/sensitive-words/defaults",
    response_model=SensitiveWordsRead,
)
def read_default_sensitive_words() -> SensitiveWordsRead:
    """返回只读默认词包；用户可合并后手动保存。"""
    return SensitiveWordsRead(words=default_sensitive_words())


@router.put("/settings/sensitive-words", response_model=SensitiveWordsRead)
def update_sensitive_words(
    payload: SensitiveWordsPayload, db: Session = Depends(get_db)
) -> SensitiveWordsRead:
    words = save_sensitive_words(db, [item.model_dump() for item in payload.words])
    return SensitiveWordsRead(words=words)


@router.post("/sensitive-words/scan", response_model=SensitiveScanResult)
def scan_sensitive_words(
    payload: SensitiveScanRequest, db: Session = Depends(get_db)
) -> SensitiveScanResult:
    return SensitiveScanResult(
        **scan_text(payload.text, load_sensitive_words(db))
    )


@router.post("/sensitive-words/apply", response_model=SensitiveApplyResult)
def apply_sensitive_words(
    payload: SensitiveApplyRequest, db: Session = Depends(get_db)
) -> SensitiveApplyResult:
    words = load_sensitive_words(db)
    version = dictionary_version(words)
    content, items = apply_text(
        payload.text,
        words,
        [item.model_dump() for item in payload.items],
    )
    return SensitiveApplyResult(
        content=content,
        items=items,
        dictionary_version=version,
        sensitive_edit=build_sensitive_edit(payload.text, content, items, version),
    )
