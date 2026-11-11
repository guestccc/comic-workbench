"""发布账号：工作台只保存 sau 的本地账号别名与检测状态。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import PUBLISH_PLATFORM_LABELS, PUBLISH_PLATFORMS
from ...models import PublishAccount

DEFAULT_ACCOUNT_NAME = "default"


def ensure_default_accounts(db: Session) -> None:
    """为每个平台补种默认账号；重复调用安全，不影响已有账号。"""
    existing_platforms = set(
        db.scalars(select(PublishAccount.platform).distinct()).all()
    )
    added = False
    for platform in PUBLISH_PLATFORMS:
        if platform in existing_platforms:
            continue
        db.add(
            PublishAccount(
                platform=platform,
                account_name=DEFAULT_ACCOUNT_NAME,
                display_name=f"{PUBLISH_PLATFORM_LABELS[platform]}主账号",
                status="unknown",
            )
        )
        added = True
    if added:
        db.commit()
