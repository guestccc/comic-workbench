"""ORM 模型：设置、故事、发文、故事拆解与发文配置。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .config import (
    MAX_ART_STYLE_ID_LENGTH,
    MAX_ART_STYLE_NAME_LENGTH,
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
    """故事：名称、原文、封面文件名、拆解使用的画风。"""

    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(MAX_STORY_NAME_LENGTH), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    cover_filename: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 引用画风列表（app_settings 中的 JSON）里的 id；画风被删除时允许悬空，
    # 读取时解析不到名称/描述，由前端提示重新选择。
    art_style_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
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


class StoryBreakdown(Base):
    """故事拆解结果：一个故事一份，随故事删除级联清理。

    characters / pages 用 JSON 列存储，读写时整体赋值；
    分镜页顺序由 page_number 决定，路由层负责排序。
    """

    __tablename__ = "story_breakdowns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    optimized_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    characters: Mapped[list[dict]] = mapped_column(
        JSON, default=list, nullable=False
    )
    # 旧流程的人物合影提示词；新流程不再生成，字段保留以兼容旧数据
    group_photo_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    pages: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    # 生成时的画风快照：故事之后换画风时据此提示「拆解已过期」
    art_style_id: Mapped[str | None] = mapped_column(
        String(MAX_ART_STYLE_ID_LENGTH), nullable=True
    )
    art_style_name: Mapped[str | None] = mapped_column(
        String(MAX_ART_STYLE_NAME_LENGTH), nullable=True
    )
    art_style_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 写入时故事原文的 SHA-256，用于判断原文是否已变化
    source_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # AI 改动解读缓存：原文 + 优化文的哈希不变时直接复用，避免重复调用模型
    analysis_cache: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analysis_input_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class StoryPostConfig(Base):
    """每个故事一份的小红书发文配置，与 posts 的多条发文记录互不影响。"""

    __tablename__ = "story_post_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(
        String(MAX_POST_TITLE_LENGTH), default="", nullable=False
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
