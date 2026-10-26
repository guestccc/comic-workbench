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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .config import (
    MAX_ART_STYLE_ID_LENGTH,
    MAX_ART_STYLE_NAME_LENGTH,
    MAX_POST_TITLE_LENGTH,
    MAX_STORY_CONTENT_LENGTH,
    MAX_STORY_NAME_LENGTH,
    MAX_ZHIHU_ALIAS_LENGTH,
    MAX_ZHIHU_ARTICLE_ID_LENGTH,
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
    """故事：名称（同时作为知乎原名标题）、原文、封面文件名、拆解使用的画风。"""

    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(MAX_STORY_NAME_LENGTH), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    cover_filename: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 引用画风列表（app_settings 中的 JSON）里的 id；画风被删除时允许悬空，
    # 读取时解析不到名称/描述，由前端提示重新选择。
    art_style_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 知乎推广信息：原文 ID、在知乎注册的搜索别名
    zhihu_article_id: Mapped[str] = mapped_column(
        String(MAX_ZHIHU_ARTICLE_ID_LENGTH), default="", nullable=False
    )
    zhihu_alias: Mapped[str] = mapped_column(
        String(MAX_ZHIHU_ALIAS_LENGTH), default="", nullable=False
    )
    # 候选别名列表；用户在知乎注册多个时先保存，最终用 zhihu_alias 标注
    zhihu_aliases: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
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
    # 分镜对照表：页码 → 原文摘录。第一步只写这张表，第二步据此生成分镜页
    mapping: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    # 章节 = 一篇小红书笔记：封面、正文对照段、引导卡。空列表表示未启用章节
    chapters: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
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
    """每个故事一份的旧版发文配置，与 posts 的多条发文记录互不影响。

    启用章节后，每章文案写在 StoryChapterPostConfig；这里仅给没有章节的
    老故事兜底。
    """

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


class StoryChapterPostConfig(Base):
    """一章一份的小红书发文配置，一章对应一篇笔记。"""

    __tablename__ = "story_chapter_post_configs"
    __table_args__ = (
        UniqueConstraint(
            "story_id",
            "chapter_number",
            name="uq_story_chapter_post_config",
        ),
        Index(
            "ix_story_chapter_post_configs_story_id",
            "story_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
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
