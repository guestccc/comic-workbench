"""数据库读写辅助函数。

约定：本模块只负责查询与对象变更，不提交事务；事务边界由路由层控制。
"""

from __future__ import annotations

import json
import logging
import os

from sqlalchemy.orm import Session

from .config import (
    ACTIVE_ART_STYLE_KEY,
    ART_STYLES_KEY,
    DEEPSEEK_KEY,
    DEFAULT_IMAGE_PREFIX_PROMPT,
    DEFAULT_START_PROMPT,
    IMAGE_PREFIX_PROMPT_KEY,
    PROMPT_KEY,
)
from .models import Setting

logger = logging.getLogger("comic_workbench")


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


def get_image_prefix_prompt(db: Session) -> tuple[str, Setting | None]:
    """返回生图前置提示词及对应设置行（未保存过时返回默认规则）。

    与启动提示词不同，这里允许保存为空字符串：用户想彻底关掉前置规则时，
    空值代表「不拼任何内容」，而不是回退到默认值。
    """
    row = db.get(Setting, IMAGE_PREFIX_PROMPT_KEY)
    if row is None:
        return DEFAULT_IMAGE_PREFIX_PROMPT, None
    return row.value, row


def get_art_styles(db: Session) -> tuple[list[dict[str, str]], str | None]:
    """读取画风列表与当前选用项。

    数据损坏（非法 JSON 或结构不符）时降级为空列表并记录日志，
    避免整个设置页因一条脏数据无法加载。
    """
    row = db.get(Setting, ART_STYLES_KEY)
    styles: list[dict[str, str]] = []
    if row is not None and row.value.strip():
        try:
            parsed = json.loads(row.value)
        except json.JSONDecodeError:
            logger.warning("画风列表 JSON 解析失败，已按空列表处理")
            parsed = None
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                style_id = item.get("id")
                name = item.get("name")
                content = item.get("content")
                if all(isinstance(value, str) and value.strip() for value in (style_id, name, content)):
                    styles.append(
                        {"id": style_id.strip(), "name": name.strip(), "content": content.strip()}
                    )
        elif parsed is not None:
            logger.warning("画风列表结构异常，已按空列表处理")

    active_row = db.get(Setting, ACTIVE_ART_STYLE_KEY)
    active_id = active_row.value.strip() if active_row is not None else ""
    if active_id and active_id not in {style["id"] for style in styles}:
        active_id = ""
    return styles, active_id or None


def save_art_styles(
    db: Session, styles: list[dict[str, str]], active_id: str | None
) -> None:
    """全量覆盖画风列表；未选用画风时删除 active 设置行。"""
    upsert_setting(db, ART_STYLES_KEY, json.dumps(styles, ensure_ascii=False))
    if active_id:
        upsert_setting(db, ACTIVE_ART_STYLE_KEY, active_id)
    else:
        delete_setting(db, ACTIVE_ART_STYLE_KEY)


def get_active_art_style(db: Session) -> dict[str, str] | None:
    """返回当前选用的画风（含 id / name / content），未选用时返回 None。

    生成文案时用 name 替换 {art_style_name}、用 content 替换 {art_style}。
    """
    styles, active_id = get_art_styles(db)
    if active_id is None:
        return None
    for style in styles:
        if style["id"] == active_id:
            return style
    return None


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
