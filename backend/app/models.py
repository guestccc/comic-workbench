"""ORM 模型：设置、故事、发文、故事拆解与发文配置。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
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
    MAX_DESIGN_FEEDBACK_CONTENT_LENGTH,
    MAX_DESIGN_FEEDBACK_IMAGE_URL_LENGTH,
    MAX_DESIGN_FEEDBACK_SOURCE_URL_LENGTH,
    MAX_DESIGN_FEEDBACK_SUMMARY_LENGTH,
    MAX_DESIGN_FEEDBACK_TITLE_LENGTH,
    MAX_POST_TITLE_LENGTH,
    MAX_STORY_CONTENT_LENGTH,
    MAX_STORY_NAME_LENGTH,
    MAX_ZHIHU_ALIAS_LENGTH,
    MAX_ZHIHU_ARTICLE_ID_LENGTH,
    XHS_DEFAULT_DECLARATION,
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
    # 敏感词替换审计：原文、替换后文本、逐词次数、词库版本与时间
    sensitive_edit: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 小红书发布设置（故事级，所有章节共用）：合集名、内容声明与来源媒体名
    xhs_collection: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
    )
    # 平台固定文案之一；空串表示不声明
    xhs_declaration: Mapped[str] = mapped_column(
        String(32), default=XHS_DEFAULT_DECLARATION, nullable=False
    )
    # 仅当声明为「来源转载」时生效
    xhs_repost_source: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
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


class ImageGeneration(Base):
    """一次生图调用的历史记录与暂存文件索引。

    生成结果先写入历史目录，用户在对比弹窗确认后才复制到正式路径；
    清除历史只删除历史文件与记录，不影响正式角色资产图 / 封面 / 分镜图。
    """

    __tablename__ = "image_generations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('generated', 'used', 'failed')",
            name="ck_image_generations_status",
        ),
        Index("ix_image_generations_story_target", "story_id", "target_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    character_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[str] = mapped_column(String(20), nullable=False)
    quality: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    reference_names: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_bytes: Mapped[int] = mapped_column("bytes", Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="generated", nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DesignFeedback(Base):
    """设计建议库：小红书 / 手动建议，可关联故事或章节。

    建议本身是源数据；每次实际改动通过 DesignFeedbackApplication 记录，
    应用记录里的改前 / 改后只是审计快照，不反向成为封面或正文的源。
    """

    __tablename__ = "design_feedbacks"
    __table_args__ = (
        CheckConstraint(
            "source IN ('xiaohongshu', 'manual')",
            name="ck_design_feedbacks_source",
        ),
        CheckConstraint(
            "category IN ('cover', 'comic', 'title', 'color', "
            "'expression', 'text', 'pacing', 'other')",
            name="ck_design_feedbacks_category",
        ),
        CheckConstraint(
            "scope IN ('global', 'story', 'chapter')",
            name="ck_design_feedbacks_scope",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high')",
            name="ck_design_feedbacks_priority",
        ),
        CheckConstraint(
            "status IN ('open', 'applied', 'verified', 'archived')",
            name="ck_design_feedbacks_status",
        ),
        CheckConstraint(
            "rule_target IN ('cover', 'comic', 'all')",
            name="ck_design_feedbacks_rule_target",
        ),
        Index("ix_design_feedbacks_status", "status"),
        Index("ix_design_feedbacks_story_id", "story_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(
        String(MAX_DESIGN_FEEDBACK_TITLE_LENGTH), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), default="xiaohongshu", nullable=False
    )
    source_url: Mapped[str] = mapped_column(
        String(MAX_DESIGN_FEEDBACK_SOURCE_URL_LENGTH), default="", nullable=False
    )
    screenshot_filename: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    category: Mapped[str] = mapped_column(
        String(20), default="other", nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(20), default="global", nullable=False
    )
    # 指定故事 / 章节时使用；故事删除后保留建议，只解除关联
    story_id: Mapped[int | None] = mapped_column(
        ForeignKey("stories.id", ondelete="SET NULL"), nullable=True
    )
    chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(10), default="medium", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False
    )
    # 升级为通用规则后，rendered prompt 会自动追加【设计规则】分块。
    # rule_target=cover 进封面，comic 进正文，all 两边都进。
    is_rule: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    rule_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rule_target: Mapped[str] = mapped_column(
        String(20), default="cover", nullable=False
    )
    rule_promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    applications: Mapped[list["DesignFeedbackApplication"]] = relationship(
        back_populates="feedback",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    rules: Mapped[list["DesignRule"]] = relationship(
        back_populates="feedback",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DesignFeedbackApplication(Base):
    """一次建议应用：目标 + 改前 / 改后快照。"""

    __tablename__ = "design_feedback_applications"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('cover', 'page', 'guide', 'character', 'other')",
            name="ck_design_feedback_applications_target_type",
        ),
        Index(
            "ix_design_feedback_applications_feedback_id", "feedback_id"
        ),
        Index("ix_design_feedback_applications_story_id", "story_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("design_feedbacks.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(
        String(MAX_DESIGN_FEEDBACK_SUMMARY_LENGTH), nullable=False
    )
    before_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_image_url: Mapped[str | None] = mapped_column(
        String(MAX_DESIGN_FEEDBACK_IMAGE_URL_LENGTH), nullable=True
    )
    after_image_url: Mapped[str | None] = mapped_column(
        String(MAX_DESIGN_FEEDBACK_IMAGE_URL_LENGTH), nullable=True
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    feedback: Mapped[DesignFeedback] = relationship(
        back_populates="applications"
    )


class DesignRule(Base):
    """结构化设计规则：从建议提炼，按范围/目标/类型编译进提示词或审片。

    draft 不生效；active 才参与渲染；disabled 保留历史但不使用。
    每次修改/状态变化写入 DesignRuleRevision，便于回滚。
    """

    __tablename__ = "design_rules"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('prompt', 'negative', 'text', 'review', 'check')",
            name="ck_design_rules_kind",
        ),
        CheckConstraint(
            "target IN ('cover', 'body', 'guide', 'all')",
            name="ck_design_rules_target",
        ),
        CheckConstraint(
            "slot IN ('scene', 'cover_mode', 'text_zone', 'none')",
            name="ck_design_rules_slot",
        ),
        CheckConstraint(
            "scope_type IN ('global', 'story', 'chapter', 'pages')",
            name="ck_design_rules_scope_type",
        ),
        CheckConstraint(
            "priority IN ('hard', 'soft')",
            name="ck_design_rules_priority",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'disabled')",
            name="ck_design_rules_status",
        ),
        CheckConstraint(
            "created_by IN ('claude', 'user')",
            name="ck_design_rules_created_by",
        ),
        Index("ix_design_rules_feedback_id", "feedback_id"),
        Index("ix_design_rules_status", "status"),
        Index("ix_design_rules_target", "target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("design_feedbacks.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(MAX_DESIGN_FEEDBACK_TITLE_LENGTH), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), default="prompt", nullable=False)
    target: Mapped[str] = mapped_column(String(20), default="cover", nullable=False)
    slot: Mapped[str] = mapped_column(String(20), default="scene", nullable=False)
    scope_type: Mapped[str] = mapped_column(
        String(20), default="global", nullable=False
    )
    story_id: Mapped[int | None] = mapped_column(
        ForeignKey("stories.id", ondelete="SET NULL"), nullable=True
    )
    chapter_numbers: Mapped[list[int]] = mapped_column(
        JSON, default=list, nullable=False
    )
    page_numbers: Mapped[list[int]] = mapped_column(
        JSON, default=list, nullable=False
    )
    priority: Mapped[str] = mapped_column(
        String(10), default="soft", nullable=False
    )
    requirement: Mapped[str] = mapped_column(Text, default="", nullable=False)
    negative_terms: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    review_check: Mapped[str] = mapped_column(Text, default="", nullable=False)
    check_spec: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str] = mapped_column(
        String(20), default="user", nullable=False
    )
    template_applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    feedback: Mapped[DesignFeedback] = relationship(back_populates="rules")
    revisions: Mapped[list["DesignRuleRevision"]] = relationship(
        back_populates="rule",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DesignRuleRevision(Base):
    """规则版本快照：每次编辑 / 激活 / 停用 / 回滚追加一条。"""

    __tablename__ = "design_rule_revisions"
    __table_args__ = (
        Index("ix_design_rule_revisions_rule_id", "rule_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("design_rules.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    change_note: Mapped[str] = mapped_column(
        String(MAX_DESIGN_FEEDBACK_SUMMARY_LENGTH), default="", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    rule: Mapped[DesignRule] = relationship(back_populates="revisions")


class DesignRuleResult(Base):
    """规则核验结果：提示词硬检查或生成图审片的人工 / Claude 判定。"""

    __tablename__ = "design_rule_results"
    __table_args__ = (
        CheckConstraint(
            "result IN ('passed', 'failed', 'unknown')",
            name="ck_design_rule_results_result",
        ),
        CheckConstraint(
            "reviewer IN ('claude', 'user')",
            name="ck_design_rule_results_reviewer",
        ),
        Index("ix_design_rule_results_rule_id", "rule_id"),
        Index("ix_design_rule_results_story_id", "story_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("design_rules.id", ondelete="CASCADE"), nullable=False
    )
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewer: Mapped[str] = mapped_column(
        String(20), default="claude", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PromptRenderSnapshot(Base):
    """一次渲染的提示词快照：用于追溯用了哪些规则，并支持恢复上一版提示词。"""

    __tablename__ = "prompt_render_snapshots"
    __table_args__ = (
        Index("ix_prompt_render_snapshots_story_target", "story_id", "target_type"),
        Index("ix_prompt_render_snapshots_chapter", "story_id", "chapter_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    applied_rules: Mapped[list[dict]] = mapped_column(
        JSON, default=list, nullable=False
    )
    rule_checks: Mapped[list[dict]] = mapped_column(
        JSON, default=list, nullable=False
    )
    restored_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PromptTemplateVersion(Base):
    """正文 / 封面提示词模板的历史版本；保存或恢复时追加，不删除旧版本。"""

    __tablename__ = "prompt_template_versions"
    __table_args__ = (
        Index("ix_prompt_template_versions_type", "template_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class MappingReview(Base):
    """分镜对照审阅草稿：一个故事一份，随故事删除级联清理。

    proposal / decisions 用 JSON 存储；mapping 仍是唯一源，应用前不写入。
    """

    __tablename__ = "mapping_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'applied', 'discarded')",
            name="ck_mapping_reviews_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False
    )
    # 创建草稿时的 mapping SHA-256；mapping 变了就拒绝应用
    base_mapping_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # 变更列表：包含服务端计算的 risk / page_delta / crosses_chapter
    proposal: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    # change_id -> approved / rejected / undecided
    decisions: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    # 本章选中的发布标签；全局预设标签只是候选项，不是第二份章节标签。
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PublishAccount(Base):
    """外部 sau 的本地账号别名；Cookie 只存在于 sau 项目，不落本库。"""

    __tablename__ = "publish_accounts"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "account_name",
            name="uq_publish_account_platform_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    account_name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="unknown", nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class PublishJob(Base):
    """一次发布任务：载荷与图片快照创建后不可变，重发必须新建任务。"""

    __tablename__ = "publish_jobs"
    __table_args__ = (
        Index("ix_publish_jobs_story_chapter", "story_id", "chapter_number"),
        Index("ix_publish_jobs_status", "status"),
        Index("ix_publish_jobs_platform", "platform"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("stories.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("publish_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_dir: Mapped[str] = mapped_column(
        String(255), default="", nullable=False
    )
    external_url: Mapped[str] = mapped_column(
        String(500), default="", nullable=False
    )
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout_excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class DesignRuleCoverageRun(Base):
    """规则落实检测：按规则范围扫描提示词，AI 判定后等待人工确认。"""

    __tablename__ = "design_rule_coverage_runs"
    __table_args__ = (
        Index("ix_design_rule_coverage_runs_rule_id", "rule_id"),
        Index("ix_design_rule_coverage_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("design_rules.id", ondelete="CASCADE"), nullable=False
    )
    feedback_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    scope_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    covered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
