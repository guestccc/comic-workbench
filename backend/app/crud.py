"""数据库读写辅助函数。

约定：本模块只负责查询与对象变更，不提交事务；事务边界由路由层控制。
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from .config import DEEPSEEK_KEY, DEFAULT_START_PROMPT, PROMPT_KEY
from .models import Setting


def get_setting(db: Session, key: str) -> Setting | None:
    return db.get(Setting, key)


def upsert_setting(db: Session, key: str, value: str) -> Setting:
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    return row


def delete_setting(db: Session, key: str) -> bool:
    row = db.get(Setting, key)
    if row is None:
        return False
    db.delete(row)
    return True


def get_start_prompt(db: Session) -> tuple[str, Setting | None]:
    """返回当前启动提示词及对应设置行（默认提示词时行为 None）。"""
    row = db.get(Setting, PROMPT_KEY)
    if row is None or not row.value.strip():
        return DEFAULT_START_PROMPT, None
    return row.value, row


def resolve_deepseek_key(db: Session) -> tuple[str | None, str, bool]:
    """解析生效的 DeepSeek Key。

    优先级：环境变量 DEEPSEEK_API_KEY > SQLite 设置。
    返回 (key, source, db_configured)。
    """
    row = db.get(Setting, DEEPSEEK_KEY)
    db_key = row.value.strip() if row is not None and row.value.strip() else None
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key, "env", db_key is not None
    if db_key:
        return db_key, "db", True
    return None, "none", False


def mask_key(key: str | None) -> str | None:
    """只展示末 4 位，任何响应都不得返回完整 Key。"""
    if not key:
        return None
    tail = key[-4:] if len(key) >= 4 else key
    return f"****{tail}"
