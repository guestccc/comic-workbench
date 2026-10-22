"""ORM 模型：设置、故事、发文。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .config import (
    MAX_POST_TITLE_LENGTH,
    MAX_STORY_CONTENT_LENGTH,
    MAX_STORY_NAME_LENGTH,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Setting(Base):
    """键值设置表：启动提示词、DeepSeek API Key。"""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Story(Base):
    """故事：名称、原文、封面文件名。"""

    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(MAX_STORY_NAME_LENGTH), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    cover_filename: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    posts: Mapped[list["Post"]] = relationship(
        back_populates="story", passive_deletes=True
    )


class Post(Base):
    """发文记录：根据故事生成的小红书标题与正文。"""

    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published')", name="ck_posts_status"),
        Index("ix_posts_story_id", "story_id"),
        Index("ix_posts_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # RESTRICT：有发文的故事不允许删除，避免误删已发布内容
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(MAX_POST_TITLE_LENGTH), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    story: Mapped[Story] = relationship(back_populates="posts")
