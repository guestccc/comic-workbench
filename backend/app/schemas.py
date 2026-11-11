"""Pydantic 请求 / 响应模型。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_serializer,
    field_validator,
    model_validator,
)

from .config import (
    CHARACTER_ASSET_FILENAME_PATTERN,
    MAX_API_KEY_LENGTH,
    MAX_ART_STYLES,
    MAX_ART_STYLE_CONTENT_LENGTH,
    MAX_ART_STYLE_ID_LENGTH,
    MAX_ART_STYLE_NAME_LENGTH,
    MAX_BATCH_INGEST_ITEMS,
    MAX_BREAKDOWN_CONTENT_LENGTH,
    MAX_BREAKDOWN_PAGES,
    MAX_CHARACTER_APPEARANCE_LENGTH,
    MAX_CHARACTER_CARDS,
    MAX_CHARACTER_GROUP_PROMPT_LENGTH,
    MAX_CHARACTER_NAME_LENGTH,
    MAX_CHARACTER_ROLE_LENGTH,
    MAX_CHAPTERS,
    MAX_CHAPTER_CONTENT_PAGES,
    MAX_CHAPTER_GUIDE_SUB_TEXT_LENGTH,
    MAX_CHAPTER_GUIDE_TEXT_LENGTH,
    MAX_CHAPTER_LABEL_LENGTH,
    MAX_CHAPTER_TITLE_LENGTH,
    MAX_DESIGN_FEEDBACK_APPLICATIONS,
    MAX_DESIGN_FEEDBACK_CONTENT_LENGTH,
    MAX_DESIGN_FEEDBACK_IMAGE_URL_LENGTH,
    MAX_DESIGN_FEEDBACK_PROMPT_LENGTH,
    MAX_DESIGN_FEEDBACK_SOURCE_URL_LENGTH,
    MAX_DESIGN_FEEDBACK_SUMMARY_LENGTH,
    MAX_DESIGN_FEEDBACK_TAG_LENGTH,
    MAX_DESIGN_FEEDBACK_TAGS,
    MAX_DESIGN_FEEDBACK_TITLE_LENGTH,
    MAX_COPY_OPTION_FEATURE_LENGTH,
    MAX_COPY_OPTION_REASON_LENGTH,
    MAX_COPY_OPTION_STYLE_LENGTH,
    MAX_IMAGE_PREFIX_PROMPT_LENGTH,
    MAX_PAGE_CAMERA_ANGLE_LENGTH,
    MAX_PAGE_CHARACTERS,
    MAX_PAGE_DIALOGUES,
    MAX_PAGE_DIALOGUE_LENGTH,
    MAX_PAGE_HIGHLIGHT_LENGTH,
    MAX_PAGE_IMAGE_PROMPT_LENGTH,
    MAX_PAGE_ROLE_LENGTH,
    MAX_PAGE_SHORT_TEXT_LENGTH,
    MAX_OPTIMIZE_ANALYZE_CHANGES,
    MAX_OPTIMIZE_ANALYZE_QUOTE_LENGTH,
    MAX_OPTIMIZE_ANALYZE_REASON_LENGTH,
    MAX_OPTIMIZE_ANALYZE_SUMMARY_LENGTH,
    MAX_PAGE_TEXT_LENGTH,
    MAX_POST_CONFIG_TITLE_LENGTH,
    MAX_POST_CONTENT_LENGTH,
    MAX_POST_TITLE_LENGTH,
    MAX_PUBLISH_TAGS,
    MAX_PUBLISH_TAG_LENGTH,
    PUBLISH_TIMEZONE,
    MAX_PROMPT_LENGTH,
    MAX_PROMPT_OPTIMIZE_MESSAGES,
    MAX_PROMPT_TEMPLATE_LENGTH,
    MAX_PROMPT_OPTIMIZE_TOTAL_CHARS,
    MAX_STORY_CONTENT_LENGTH,
    MAX_STORY_NAME_LENGTH,
    MAX_ZHIHU_ALIASES,
    MAX_ZHIHU_ALIAS_LENGTH,
    MAX_ZHIHU_ARTICLE_ID_LENGTH,
    MAX_XHS_DECLARATION_LENGTH,
    MAX_XHS_REPOST_SOURCE_LENGTH,
    XHS_DEFAULT_DECLARATION,
)

PostStatus = Literal["draft", "published"]
PublishPlatform = Literal["douyin", "xiaohongshu"]
PublishMode = Literal["scheduled", "immediate"]
PublishJobStatus = Literal[
    "queued", "running", "scheduled", "failed", "unknown", "published"
]
PublishAccountStatus = Literal["unknown", "valid", "invalid"]


def utc_iso(value: datetime | None) -> str | None:
    """SQLite 读出的是 naive UTC 时间，统一补上时区后序列化。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_timestamp(self, value: datetime) -> str:
        return utc_iso(value) or ""


# ---------------------------------------------------------------------------
# 设置 / 启动提示词
# ---------------------------------------------------------------------------


class DeepSeekStatus(BaseModel):
    configured: bool
    source: Literal["env", "db", "none"]
    masked_key: str | None = None
    db_configured: bool = False


class ArtStyleItem(BaseModel):
    """一条命名的画风设定；生成 / 复制提示词时替换画风占位符。

    name 替换 {art_style_name}，content 替换 {art_style}。
    """

    id: str = Field(min_length=1, max_length=MAX_ART_STYLE_ID_LENGTH)
    name: str = Field(min_length=1, max_length=MAX_ART_STYLE_NAME_LENGTH)
    content: str = Field(min_length=1, max_length=MAX_ART_STYLE_CONTENT_LENGTH)

    @field_validator("id", "name", "content")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class ArtStylesUpdate(BaseModel):
    """全量保存画风列表与当前选用项，单次请求保证两者一致。"""

    styles: list[ArtStyleItem] = Field(default_factory=list, max_length=MAX_ART_STYLES)
    active_id: str | None = None

    @field_validator("active_id")
    @classmethod
    def _strip_active(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _validate_styles(self) -> "ArtStylesUpdate":
        ids = [style.id for style in self.styles]
        if len(ids) != len(set(ids)):
            raise ValueError("画风 id 不能重复")

        names = [style.name for style in self.styles]
        if len(names) != len(set(names)):
            raise ValueError("画风名称不能重复")

        if self.active_id is not None and self.active_id not in set(ids):
            raise ValueError("选用的画风必须存在于列表中")
        return self


ImageGenerationTarget = Literal[
    "character_asset", "chapter_cover", "chapter_guide", "page"
]


class ImageProviderStatus(BaseModel):
    """生图服务配置状态；Key 只返回脱敏值。"""

    configured: bool
    source: Literal["env", "db", "none"] = "none"
    masked_key: str | None = None
    base_url: str
    model: str
    size: str
    quality: str
    db_configured: bool = False


class ImageProviderUpdate(BaseModel):
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=100)
    size: str = Field(min_length=3, max_length=20)
    quality: Literal["auto", "low", "medium", "high"] = "high"
    # 为空表示保持已保存的 Key 不变
    api_key: SecretStr | None = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("接口地址必须以 http:// 或 https:// 开头")
        return value

    @field_validator("model", "size")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("size")
    @classmethod
    def _validate_size(cls, value: str) -> str:
        if not re.fullmatch(r"\d{2,5}x\d{2,5}", value):
            raise ValueError("尺寸格式应为 宽x高，例如 1024x1536")
        return value

    @field_validator("api_key")
    @classmethod
    def _strip_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        if not value.get_secret_value().strip():
            return None
        return value


class ImageProviderTestResult(BaseModel):
    ok: bool
    models: list[str] = Field(default_factory=list)
    message: str = ""


class CharacterAssetGenerateRequest(BaseModel):
    character_name: str = Field(min_length=1, max_length=MAX_CHARACTER_NAME_LENGTH)

    @field_validator("character_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("角色名不能为空")
        return value


class ImageGenerationPreview(BaseModel):
    generation_id: str
    target_type: ImageGenerationTarget
    old_url: str | None = None
    new_url: str
    model: str
    size: str
    elapsed_ms: int


class ImageGenerationItem(BaseModel):
    id: str
    target_type: ImageGenerationTarget
    url: str
    created_at: datetime
    model: str
    size: str
    file_bytes: int
    used_at: datetime | None = None
    is_current: bool = False
    prompt: str = ""
    reference_names: list[str] = Field(default_factory=list)

    @field_serializer("created_at", "used_at")
    def _serialize_time(self, value: datetime | None) -> str | None:
        return utc_iso(value)


class ImageGenerationList(BaseModel):
    items: list[ImageGenerationItem] = Field(default_factory=list)
    total_bytes: int = 0


class ImageGenerationClearResult(BaseModel):
    deleted: int
    freed_bytes: int


class SettingsRead(BaseModel):
    prompt: str
    is_default: bool
    prompt_updated_at: datetime | None = None
    deepseek: DeepSeekStatus
    art_styles: list[ArtStyleItem] = Field(default_factory=list)
    active_art_style: str | None = None
    # 生图前置提示词：全局生效，复制角色卡与分镜提示词时自动拼在开头
    image_prefix_prompt: str = ""
    image_provider: ImageProviderStatus

    @field_serializer("prompt_updated_at")
    def _serialize_prompt_time(self, value: datetime | None) -> str | None:
        return utc_iso(value)


class PromptTemplatesRead(BaseModel):
    body: str
    cover: str
    body_default: str
    cover_default: str
    body_is_default: bool
    cover_is_default: bool
    placeholders: list[str] = Field(default_factory=list)


class PromptTemplatesUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_PROMPT_TEMPLATE_LENGTH)
    cover: str = Field(min_length=1, max_length=MAX_PROMPT_TEMPLATE_LENGTH)


class PromptTemplateVersionRead(BaseModel):
    id: int
    template_type: Literal["body", "cover"]
    content: str
    note: str
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return utc_iso(value) or ""


class PromptRenderContext(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_PAGE_IMAGE_PROMPT_LENGTH)
    character_consistency: str = Field(
        default="", max_length=MAX_PAGE_TEXT_LENGTH
    )
    narration_main: str = Field(
        default="", max_length=MAX_PAGE_SHORT_TEXT_LENGTH
    )
    narration_sub: str = Field(default="", max_length=MAX_PAGE_TEXT_LENGTH)
    narration_highlight: str = Field(
        default="", max_length=MAX_PAGE_HIGHLIGHT_LENGTH
    )
    dialogues: list[str] = Field(
        default_factory=list, max_length=MAX_PAGE_DIALOGUES
    )
    page_number: int | None = Field(
        default=None, ge=1, le=MAX_BREAKDOWN_PAGES
    )
    chapter_number: int | None = Field(
        default=None, ge=1, le=MAX_CHAPTERS
    )
    label: str = Field(default="", max_length=MAX_CHAPTER_LABEL_LENGTH)


class PromptRenderRequest(BaseModel):
    template_type: Literal["body", "cover"]
    story_id: int = Field(ge=1)
    context: PromptRenderContext
    # 设置页预览不落提示词快照
    preview: bool = False


class PromptRenderResult(BaseModel):
    prompt: str
    template_type: Literal["body", "cover"]
    story_id: int
    # 本次实际匹配到的设计规则；供 cover-director / 审计使用
    applied_rules: list[dict] = Field(default_factory=list)
    rule_checks: list[dict] = Field(default_factory=list)
    snapshot_id: int | None = None


class PromptSnapshotRead(BaseModel):
    id: int
    story_id: int
    target_type: Literal["cover", "body"]
    chapter_number: int | None = None
    page_number: int | None = None
    template_type: Literal["body", "cover"]
    prompt: str
    applied_rules: list[dict] = Field(default_factory=list)
    rule_checks: list[dict] = Field(default_factory=list)
    restored_from_id: int | None = None
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return utc_iso(value) or ""


class PromptSnapshotRestoreResult(BaseModel):
    snapshot: PromptSnapshotRead
    target_type: Literal["cover", "body"]
    chapter_number: int | None = None
    page_number: int | None = None


class PromptUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)

    @field_validator("content")
    @classmethod
    def _strip_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("启动提示词不能为空")
        return value


class ImagePrefixPromptUpdate(BaseModel):
    """保存全局生图前置提示词；允许为空，空值表示复制时不拼任何前置内容。"""

    content: str = Field(max_length=MAX_IMAGE_PREFIX_PROMPT_LENGTH)


class DeepSeekKeyUpdate(BaseModel):
    api_key: SecretStr = Field(min_length=1, max_length=MAX_API_KEY_LENGTH)

    @field_validator("api_key")
    @classmethod
    def _strip_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("API Key 不能为空")
        return value


class PromptOptimizeMessage(BaseModel):
    """AI 优化对话中的单条消息；只允许用户与助手角色。"""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)

    @field_validator("content")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("消息内容不能为空")
        return value


class PromptOptimizeRequest(BaseModel):
    """AI 优化启动提示词请求。

    current_prompt 使用前端编辑器中的当前值（可能尚未保存），
    messages 为多轮对话历史，最后一条必须是用户本轮诉求。
    """

    current_prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    messages: list[PromptOptimizeMessage] = Field(
        min_length=1, max_length=MAX_PROMPT_OPTIMIZE_MESSAGES
    )

    @field_validator("current_prompt")
    @classmethod
    def _strip_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("启动提示词不能为空")
        return value

    @model_validator(mode="after")
    def _validate_conversation(self) -> "PromptOptimizeRequest":
        if self.messages[-1].role != "user":
            raise ValueError("最后一条消息必须是用户消息")

        total_chars = len(self.current_prompt) + sum(
            len(message.content) for message in self.messages
        )
        if total_chars > MAX_PROMPT_OPTIMIZE_TOTAL_CHARS:
            raise ValueError(
                f"提示词与对话总长度不能超过 {MAX_PROMPT_OPTIMIZE_TOTAL_CHARS} 字符"
            )
        return self


class CharacterOptimizeRequest(BaseModel):
    """AI 优化角色设定卡外形描述；对话规则与启动提示词一致。"""

    character_name: str = Field(min_length=1, max_length=MAX_CHARACTER_NAME_LENGTH)
    character_role: str = Field(default="", max_length=MAX_CHARACTER_ROLE_LENGTH)
    current_appearance: str = Field(
        min_length=1, max_length=MAX_CHARACTER_APPEARANCE_LENGTH
    )
    messages: list[PromptOptimizeMessage] = Field(
        min_length=1, max_length=MAX_PROMPT_OPTIMIZE_MESSAGES
    )

    @field_validator("character_name", "current_appearance")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("character_role")
    @classmethod
    def _strip_optional(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _validate_conversation(self) -> "CharacterOptimizeRequest":
        if self.messages[-1].role != "user":
            raise ValueError("最后一条消息必须是用户消息")

        total_chars = len(self.character_name) + len(self.character_role) + len(
            self.current_appearance
        ) + sum(len(message.content) for message in self.messages)
        if total_chars > MAX_PROMPT_OPTIMIZE_TOTAL_CHARS:
            raise ValueError(
                f"外形描述与对话总长度不能超过 {MAX_PROMPT_OPTIMIZE_TOTAL_CHARS} 字符"
            )
        return self


class ChapterCoverOptimizeRequest(BaseModel):
    """AI 优化章节封面：只允许改主标题、副标题与画面提示词。"""

    chapter_title: str = Field(default="", max_length=MAX_CHAPTER_TITLE_LENGTH)
    cover_label: str = Field(default="", max_length=MAX_CHAPTER_LABEL_LENGTH)
    cover_main: str = Field(
        default="", max_length=MAX_PAGE_SHORT_TEXT_LENGTH
    )
    cover_sub: str = Field(default="", max_length=MAX_PAGE_TEXT_LENGTH)
    cover_highlight: str = Field(
        default="", max_length=MAX_PAGE_HIGHLIGHT_LENGTH
    )
    current_prompt: str = Field(
        default="", max_length=MAX_PAGE_IMAGE_PROMPT_LENGTH
    )
    suggestion: str = Field(
        min_length=1, max_length=MAX_PAGE_TEXT_LENGTH
    )

    @field_validator(
        "chapter_title",
        "cover_label",
        "cover_main",
        "cover_sub",
        "cover_highlight",
        "current_prompt",
    )
    @classmethod
    def _strip_optional(cls, value: str) -> str:
        return value.strip()

    @field_validator("suggestion")
    @classmethod
    def _strip_suggestion(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("优化建议不能为空")
        return value


class ChapterCoverOptimizeResult(BaseModel):
    """章节封面 AI 优化结果：只有三项允许变化。"""

    narration_main: str = Field(
        min_length=1, max_length=MAX_PAGE_SHORT_TEXT_LENGTH
    )
    narration_sub: str = Field(min_length=1, max_length=MAX_PAGE_TEXT_LENGTH)
    image_prompt: str = Field(
        min_length=1, max_length=MAX_PAGE_IMAGE_PROMPT_LENGTH
    )

    @field_validator("narration_main", "narration_sub", "image_prompt")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class CoverCopyOptionsRequest(BaseModel):
    """生成封面文案方案：可带当前未保存的封面文字和用户方向。"""

    chapter_title: str = Field(default="", max_length=MAX_CHAPTER_TITLE_LENGTH)
    cover_label: str = Field(default="", max_length=MAX_CHAPTER_LABEL_LENGTH)
    cover_main: str = Field(default="", max_length=MAX_PAGE_SHORT_TEXT_LENGTH)
    cover_highlight: str = Field(
        default="", max_length=MAX_PAGE_HIGHLIGHT_LENGTH
    )
    cover_sub: str = Field(default="", max_length=MAX_PAGE_TEXT_LENGTH)
    direction: str = Field(default="", max_length=MAX_PAGE_TEXT_LENGTH)

    @field_validator(
        "chapter_title",
        "cover_label",
        "cover_main",
        "cover_highlight",
        "cover_sub",
        "direction",
    )
    @classmethod
    def _strip_optional(cls, value: str) -> str:
        return value.strip()


class CoverCopyOption(BaseModel):
    """单个封面文案方案：主标题、标红词、副标题和画面建议。"""

    style: str = Field(min_length=1, max_length=20)
    feature: str = Field(min_length=1, max_length=200)
    hook_source: str = Field(default="", max_length=30)
    visual_hint: str = Field(default="", max_length=300)
    visual_content: str = Field(min_length=1, max_length=2_000)
    narration_main: str = Field(
        min_length=1, max_length=MAX_PAGE_SHORT_TEXT_LENGTH
    )
    narration_highlight: str = Field(
        default="", max_length=MAX_PAGE_HIGHLIGHT_LENGTH
    )
    narration_sub: str = Field(min_length=1, max_length=MAX_PAGE_TEXT_LENGTH)
    recommended: bool = False
    recommend_reason: str = Field(default="", max_length=200)
    image_prompt: str = Field(
        default="", max_length=MAX_PAGE_IMAGE_PROMPT_LENGTH
    )

    @field_validator(
        "style",
        "feature",
        "hook_source",
        "visual_hint",
        "visual_content",
        "narration_main",
        "narration_highlight",
        "narration_sub",
        "recommend_reason",
        "image_prompt",
    )
    @classmethod
    def _strip_option(cls, value: str) -> str:
        return value.strip()


class CoverCopyOptionsPayload(BaseModel):
    """DeepSeek 原始输出；契约要求 3 个，容忍 2–4 个。"""

    options: list[CoverCopyOption] = Field(min_length=2, max_length=4)


class CoverCopyOptionsResponse(BaseModel):
    story_id: int
    chapter_number: int
    post_title: str | None = None
    options: list[CoverCopyOption]


class CharacterSyncItem(BaseModel):
    """从生图平台同步回来的单个角色：名字用于匹配，外形整体覆盖。"""

    name: str = Field(min_length=1, max_length=MAX_CHARACTER_NAME_LENGTH)
    appearance: str = Field(
        min_length=1, max_length=MAX_CHARACTER_APPEARANCE_LENGTH
    )

    @field_validator("name", "appearance")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class CharacterSyncRequest(BaseModel):
    """同步生图平台返回的角色卡；由前端解析原始文本后提交。"""

    characters: list[CharacterSyncItem] = Field(
        min_length=1, max_length=MAX_CHARACTER_CARDS
    )


class CharacterSyncResult(BaseModel):
    """同步结果摘要：哪些角色卡被更新/新增，分镜人物回顾是否同步。"""

    # 按名匹配后更新了外形的角色
    updated_names: list[str]
    # 平台返回了但工作台还没有的新角色
    created_names: list[str]
    # 人物回顾被 AI 重写的分镜页页码
    review_updated_pages: list[int]
    # 未配置 Key 或没有受影响页面时跳过人物回顾同步的原因；正常同步为 None
    review_warning: str | None = None


class ArtStyleOptimizeRequest(BaseModel):
    """AI 优化画风描述请求；对话规则与启动提示词一致。"""

    current_style: str = Field(min_length=1, max_length=MAX_ART_STYLE_CONTENT_LENGTH)
    messages: list[PromptOptimizeMessage] = Field(
        min_length=1, max_length=MAX_PROMPT_OPTIMIZE_MESSAGES
    )

    @field_validator("current_style")
    @classmethod
    def _strip_style(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("画风描述不能为空")
        return value

    @model_validator(mode="after")
    def _validate_conversation(self) -> "ArtStyleOptimizeRequest":
        if self.messages[-1].role != "user":
            raise ValueError("最后一条消息必须是用户消息")

        total_chars = len(self.current_style) + sum(
            len(message.content) for message in self.messages
        )
        if total_chars > MAX_PROMPT_OPTIMIZE_TOTAL_CHARS:
            raise ValueError(
                f"画风描述与对话总长度不能超过 {MAX_PROMPT_OPTIMIZE_TOTAL_CHARS} 字符"
            )
        return self


# ---------------------------------------------------------------------------
# 故事
# ---------------------------------------------------------------------------


class SensitiveWordItem(BaseModel):
    """敏感词词条：替换为、分类与是否启用。"""

    word: str = Field(min_length=1, max_length=50)
    replacement: str = Field(default="", max_length=100)
    category: str = Field(default="", max_length=50)
    enabled: bool = True

    @field_validator("word")
    @classmethod
    def _strip_word(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("敏感词不能为空")
        return value

    @field_validator("replacement", "category")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class SensitiveWordsPayload(BaseModel):
    words: list[SensitiveWordItem] = Field(default_factory=list, max_length=5000)


class SensitiveWordsRead(BaseModel):
    words: list[SensitiveWordItem] = Field(default_factory=list)


class SensitiveScanRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_STORY_CONTENT_LENGTH)


class SensitiveWordMatch(BaseModel):
    word: str
    replacement: str
    category: str
    start: int
    end: int


class SensitiveScanResult(BaseModel):
    matches: list[SensitiveWordMatch]
    total: int
    counts: dict[str, int]
    dictionary_version: str


class SensitiveApplyItem(BaseModel):
    word: str = Field(min_length=1, max_length=50)
    replacement: str = Field(default="", max_length=100)


class SensitiveApplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_STORY_CONTENT_LENGTH)
    items: list[SensitiveApplyItem] = Field(min_length=1)


class SensitiveStoryApplyRequest(BaseModel):
    items: list[SensitiveApplyItem] = Field(min_length=1)


class SensitiveAppliedItem(BaseModel):
    word: str
    replacement: str
    count: int


class SensitiveApplyResult(BaseModel):
    content: str
    items: list[SensitiveAppliedItem]
    dictionary_version: str
    sensitive_edit: dict


class StoryCreate(BaseModel):
    """新建故事；名称可留空，拆解后再补填。"""

    name: str = Field(default="", max_length=MAX_STORY_NAME_LENGTH)
    content: str = Field(min_length=1, max_length=MAX_STORY_CONTENT_LENGTH)
    cover_filename: str | None = Field(default=None, max_length=64)
    # 该故事拆解时使用的画风 id；为空表示尚未选择
    art_style_id: str | None = Field(
        default=None, max_length=MAX_ART_STYLE_ID_LENGTH
    )
    # 敏感词替换审计（原文、替换后文本、逐词次数）；不传表示没有执行过
    sensitive_edit: dict | None = None

    @field_validator("name")
    @classmethod
    def _strip_optional_name(cls, value: str) -> str:
        # 名称允许为空字符串，统一去掉首尾空白
        return value.strip()

    @field_validator("art_style_id")
    @classmethod
    def _strip_optional_art_style(cls, value: str | None) -> str | None:
        # 空字符串与纯空白视为未选择画风
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("content")
    @classmethod
    def _strip_required_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class StoryUpdate(StoryCreate):
    """PUT 全量更新；cover_filename 传 null 表示清除封面。"""


class StoryZhihuUpdate(BaseModel):
    """更新故事级知乎推广信息；知乎原名标题直接取故事名。"""

    zhihu_article_id: str = Field(
        default="", max_length=MAX_ZHIHU_ARTICLE_ID_LENGTH
    )
    zhihu_alias: str = Field(default="", max_length=MAX_ZHIHU_ALIAS_LENGTH)
    # 候选别名列表；最终使用哪个由 zhihu_alias 标注
    zhihu_aliases: list[str] | None = Field(
        default=None, max_length=MAX_ZHIHU_ALIASES
    )

    @field_validator("zhihu_article_id", "zhihu_alias")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("zhihu_article_id")
    @classmethod
    def _validate_article_id(cls, value: str) -> str:
        if value and not re.fullmatch(r"\d{1,64}", value):
            raise ValueError("知乎原文 ID 只能是数字")
        return value

    @field_validator("zhihu_alias")
    @classmethod
    def _validate_alias(cls, value: str) -> str:
        if value and not re.fullmatch(r"[一-鿿]{6,8}", value):
            raise ValueError("别名必须是 6–8 个汉字，不能包含字母、数字、标点或空格")
        return value

    @field_validator("zhihu_aliases")
    @classmethod
    def _clean_aliases(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned: list[str] = []
        for value in values:
            value = value.strip()
            if not value:
                continue
            if len(value) > MAX_ZHIHU_ALIAS_LENGTH:
                raise ValueError(
                    f"单个别名不能超过 {MAX_ZHIHU_ALIAS_LENGTH} 个汉字"
                )
            if value not in cleaned:
                cleaned.append(value)
        return cleaned


class ZhihuAliasSuggestionsRead(BaseModel):
    aliases: list[str]


class StoryXiaohongshuUpdate(BaseModel):
    """故事级小红书发布设置；所有章节共用同一份。"""

    # 取值必须是平台选项文案之一；空串表示不声明
    declaration: str = Field(
        default=XHS_DEFAULT_DECLARATION, max_length=MAX_XHS_DECLARATION_LENGTH
    )
    # 仅「来源转载」生效；其他声明下原样保存但不进入载荷
    repost_source: str = Field(
        default="", max_length=MAX_XHS_REPOST_SOURCE_LENGTH
    )

    @field_validator("declaration", "repost_source")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class StoryRead(_TimestampMixin):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    content: str
    cover_filename: str | None = None
    cover_url: str | None = None
    art_style_id: str | None = None
    # 从画风列表中解析出的名称与描述；画风不存在（已删除）时为 None
    art_style_name: str | None = None
    art_style_content: str | None = None
    # 知乎推广信息：原文标题直接取故事名（派生值），另有原文 ID / 搜索别名
    zhihu_title: str = ""
    zhihu_article_id: str = ""
    zhihu_alias: str = ""
    zhihu_aliases: list[str] = Field(default_factory=list)
    # 敏感词替换审计；没有执行过时为 None
    sensitive_edit: dict | None = None
    # 小红书发布设置（故事级）
    xhs_collection: str = ""
    xhs_declaration: str = XHS_DEFAULT_DECLARATION
    xhs_repost_source: str = ""


class UploadRead(BaseModel):
    filename: str
    url: str


# ---------------------------------------------------------------------------
# 设计建议库
# ---------------------------------------------------------------------------

DesignFeedbackSource = Literal["xiaohongshu", "manual"]
DesignFeedbackCategory = Literal[
    "cover", "comic", "title", "color", "expression", "text", "pacing", "other"
]
DesignFeedbackScope = Literal["global", "story", "chapter"]
DesignFeedbackPriority = Literal["low", "medium", "high"]
DesignFeedbackStatus = Literal["open", "applied", "verified", "archived"]
DesignFeedbackTargetType = Literal[
    "cover", "page", "guide", "character", "other"
]
DesignFeedbackRuleTarget = Literal["cover", "comic", "all"]


def _clean_design_feedback_tags(values: list[str] | None) -> list[str]:
    """去空白、去重并限制标签数量与单标签长度。"""
    cleaned: list[str] = []
    for value in values or []:
        value = value.strip()
        if not value:
            continue
        if len(value) > MAX_DESIGN_FEEDBACK_TAG_LENGTH:
            raise ValueError(
                f"单个标签不能超过 {MAX_DESIGN_FEEDBACK_TAG_LENGTH} 字"
            )
        if value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > MAX_DESIGN_FEEDBACK_TAGS:
        raise ValueError(f"标签最多 {MAX_DESIGN_FEEDBACK_TAGS} 个")
    return cleaned


class DesignFeedbackCreate(BaseModel):
    """新建设计建议；用户只提交原始素材，标题可空、由服务层生成。"""

    title: str = Field(default="", max_length=MAX_DESIGN_FEEDBACK_TITLE_LENGTH)
    content: str = Field(
        default="", max_length=MAX_DESIGN_FEEDBACK_CONTENT_LENGTH
    )
    source: DesignFeedbackSource = "xiaohongshu"
    source_url: str = Field(
        default="", max_length=MAX_DESIGN_FEEDBACK_SOURCE_URL_LENGTH
    )
    screenshot_filename: str | None = Field(default=None, max_length=64)
    category: DesignFeedbackCategory = "other"
    scope: DesignFeedbackScope = "global"
    story_id: int | None = Field(default=None, ge=1)
    chapter_number: int | None = Field(default=None, ge=1, le=MAX_CHAPTERS)
    tags: list[str] = Field(
        default_factory=list, max_length=MAX_DESIGN_FEEDBACK_TAGS
    )
    priority: DesignFeedbackPriority = "medium"

    @field_validator("title", "content")
    @classmethod
    def _strip_material(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _require_material(self) -> "DesignFeedbackCreate":
        if not self.content and not self.screenshot_filename:
            raise ValueError("建议原文和截图至少填一个")
        return self

    @field_validator("source_url")
    @classmethod
    def _strip_source_url(cls, value: str) -> str:
        return value.strip()

    @field_validator("screenshot_filename")
    @classmethod
    def _strip_screenshot(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, value: list[str]) -> list[str]:
        return _clean_design_feedback_tags(value)


class DesignFeedbackUpdate(BaseModel):
    """局部更新建议；跨字段的范围校验在服务层合并后执行。"""

    title: str | None = Field(
        default=None, min_length=1, max_length=MAX_DESIGN_FEEDBACK_TITLE_LENGTH
    )
    content: str | None = Field(
        default=None, min_length=1, max_length=MAX_DESIGN_FEEDBACK_CONTENT_LENGTH
    )
    source: DesignFeedbackSource | None = None
    source_url: str | None = Field(
        default=None, max_length=MAX_DESIGN_FEEDBACK_SOURCE_URL_LENGTH
    )
    screenshot_filename: str | None = Field(default=None, max_length=64)
    category: DesignFeedbackCategory | None = None
    scope: DesignFeedbackScope | None = None
    story_id: int | None = Field(default=None, ge=1)
    chapter_number: int | None = Field(default=None, ge=1, le=MAX_CHAPTERS)
    tags: list[str] | None = Field(
        default=None, max_length=MAX_DESIGN_FEEDBACK_TAGS
    )
    priority: DesignFeedbackPriority | None = None
    status: DesignFeedbackStatus | None = None

    @field_validator("title", "content")
    @classmethod
    def _strip_optional_material(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("source_url")
    @classmethod
    def _strip_optional_url(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("screenshot_filename")
    @classmethod
    def _strip_optional_screenshot(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("tags")
    @classmethod
    def _validate_optional_tags(cls, value: list[str] | None) -> list[str] | None:
        return _clean_design_feedback_tags(value) if value is not None else None


class DesignFeedbackRead(_TimestampMixin):
    """建议列表项；story_name / screenshot_url / application_count 由服务层计算。"""

    id: int
    title: str
    content: str
    source: DesignFeedbackSource
    source_url: str
    screenshot_filename: str | None = None
    screenshot_url: str | None = None
    category: DesignFeedbackCategory
    scope: DesignFeedbackScope
    story_id: int | None = None
    story_name: str | None = None
    chapter_number: int | None = None
    tags: list[str] = Field(default_factory=list)
    priority: DesignFeedbackPriority
    status: DesignFeedbackStatus
    application_count: int = 0
    is_rule: bool = False
    rule_text: str = ""
    rule_target: DesignFeedbackRuleTarget = "cover"
    rule_promoted_at: datetime | None = None

    @field_serializer("rule_promoted_at")
    def _serialize_rule_promoted_at(self, value: datetime | None) -> str | None:
        return utc_iso(value)


class DesignFeedbackRulePromote(BaseModel):
    """把建议升级为通用规则；规则文本会进入后续渲染的提示词。"""

    rule_text: str = Field(
        min_length=1, max_length=MAX_DESIGN_FEEDBACK_PROMPT_LENGTH
    )
    rule_target: DesignFeedbackRuleTarget = "cover"

    @field_validator("rule_text")
    @classmethod
    def _strip_rule_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


DesignRuleKind = Literal["prompt", "negative", "text", "review", "check"]
DesignRuleTarget = Literal["cover", "body", "guide", "all"]
DesignRuleSlot = Literal["scene", "cover_mode", "text_zone", "none"]
DesignRuleScopeType = Literal["global", "story", "chapter", "pages"]
DesignRulePriority = Literal["hard", "soft"]
DesignRuleStatus = Literal["draft", "active", "disabled"]
DesignRuleCreatedBy = Literal["claude", "user"]


def _unique_positive_ints(
    values: list[int] | None, *, label: str, maximum: int
) -> list[int]:
    cleaned: list[int] = []
    for value in values or []:
        if value < 1 or value > maximum:
            raise ValueError(f"{label}必须在 1–{maximum} 之间")
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


def _validate_rule_scope(
    scope_type: str,
    target: str,
    story_id: int | None,
    chapter_numbers: list[int],
    page_numbers: list[int],
) -> tuple[int | None, list[int], list[int]]:
    if scope_type == "global":
        return None, [], []
    if scope_type == "story":
        if story_id is None:
            raise ValueError("指定故事必须选择故事")
        return story_id, [], []
    if scope_type == "chapter":
        if story_id is None or not chapter_numbers:
            raise ValueError("指定章节必须选择故事和至少一个章节")
        return story_id, chapter_numbers, []
    if scope_type == "pages":
        if target != "body":
            raise ValueError("页码范围只适用于正文规则")
        if story_id is None or not chapter_numbers or not page_numbers:
            raise ValueError("页码范围必须选择故事、章节和至少一个页面")
        return story_id, chapter_numbers, page_numbers
    raise ValueError("规则范围不合法")


def _validate_check_spec(spec: dict) -> None:
    check_type = spec.get("type")
    if check_type in ("required_terms", "forbidden_terms"):
        terms = spec.get("terms")
        if not isinstance(terms, list) or not terms or not all(
            isinstance(term, str) and term.strip() for term in terms
        ):
            raise ValueError("检查配置 terms 必须是非空字符串数组")
        return
    if check_type == "max_chars":
        field = spec.get("field")
        value = spec.get("value")
        if field not in {
            "content",
            "narration_main",
            "narration_sub",
            "narration_highlight",
            "label",
            "prompt",
        }:
            raise ValueError("max_chars 的 field 不合法")
        if not isinstance(value, int) or value < 1:
            raise ValueError("max_chars 的 value 必须是正整数")
        return
    if check_type == "regex":
        pattern = spec.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError("regex 检查必须填写 pattern")
        return
    raise ValueError("check_spec.type 只能是 required_terms / forbidden_terms / max_chars / regex")


class DesignRuleCreate(BaseModel):
    """创建规则草案；默认 draft，不参与渲染。"""

    title: str = Field(min_length=1, max_length=MAX_DESIGN_FEEDBACK_TITLE_LENGTH)
    kind: DesignRuleKind = "prompt"
    target: DesignRuleTarget = "cover"
    slot: DesignRuleSlot = "scene"
    scope_type: DesignRuleScopeType = "global"
    story_id: int | None = Field(default=None, ge=1)
    chapter_numbers: list[int] = Field(
        default_factory=list, max_length=MAX_CHAPTERS
    )
    page_numbers: list[int] = Field(
        default_factory=list, max_length=MAX_BREAKDOWN_PAGES
    )
    priority: DesignRulePriority = "soft"
    requirement: str = Field(
        default="", max_length=MAX_DESIGN_FEEDBACK_PROMPT_LENGTH
    )
    negative_terms: list[str] = Field(default_factory=list)
    review_check: str = Field(
        default="", max_length=MAX_DESIGN_FEEDBACK_PROMPT_LENGTH
    )
    check_spec: dict = Field(default_factory=dict)
    created_by: DesignRuleCreatedBy = "user"

    @field_validator("title")
    @classmethod
    def _strip_rule_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("requirement", "review_check")
    @classmethod
    def _strip_rule_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("chapter_numbers")
    @classmethod
    def _clean_chapters(cls, value: list[int]) -> list[int]:
        return _unique_positive_ints(
            value, label="章节号", maximum=MAX_CHAPTERS
        )

    @field_validator("page_numbers")
    @classmethod
    def _clean_pages(cls, value: list[int]) -> list[int]:
        return _unique_positive_ints(
            value, label="章内页码", maximum=MAX_BREAKDOWN_PAGES
        )

    @model_validator(mode="after")
    def _validate_rule(self) -> "DesignRuleCreate":
        story_id, chapters, pages = _validate_rule_scope(
            self.scope_type,
            self.target,
            self.story_id,
            self.chapter_numbers,
            self.page_numbers,
        )
        self.story_id = story_id
        self.chapter_numbers = chapters
        self.page_numbers = pages
        if self.kind == "negative" and not self.negative_terms:
            raise ValueError("负面规则至少需要一个负面词")
        if self.kind in ("prompt", "text") and not self.requirement:
            raise ValueError("提示词 / 文字规则必须填写规则正文")
        if self.kind == "review" and not self.review_check:
            raise ValueError("审片规则必须填写检查标准")
        if self.kind == "check":
            if not self.check_spec:
                raise ValueError("硬检查规则必须填写检查配置")
            _validate_check_spec(self.check_spec)
        return self


class DesignRuleUpdate(BaseModel):
    """局部更新规则；合并后由服务层重新校验范围。"""

    title: str | None = Field(
        default=None, min_length=1, max_length=MAX_DESIGN_FEEDBACK_TITLE_LENGTH
    )
    kind: DesignRuleKind | None = None
    target: DesignRuleTarget | None = None
    slot: DesignRuleSlot | None = None
    scope_type: DesignRuleScopeType | None = None
    story_id: int | None = Field(default=None, ge=1)
    chapter_numbers: list[int] | None = Field(
        default=None, max_length=MAX_CHAPTERS
    )
    page_numbers: list[int] | None = Field(
        default=None, max_length=MAX_BREAKDOWN_PAGES
    )
    priority: DesignRulePriority | None = None
    requirement: str | None = Field(
        default=None, max_length=MAX_DESIGN_FEEDBACK_PROMPT_LENGTH
    )
    negative_terms: list[str] | None = None
    review_check: str | None = Field(
        default=None, max_length=MAX_DESIGN_FEEDBACK_PROMPT_LENGTH
    )
    check_spec: dict | None = None

    @field_validator("chapter_numbers")
    @classmethod
    def _clean_optional_chapters(
        cls, value: list[int] | None
    ) -> list[int] | None:
        return (
            _unique_positive_ints(value, label="章节号", maximum=MAX_CHAPTERS)
            if value is not None
            else None
        )

    @field_validator("page_numbers")
    @classmethod
    def _clean_optional_pages(
        cls, value: list[int] | None
    ) -> list[int] | None:
        return (
            _unique_positive_ints(
                value, label="章内页码", maximum=MAX_BREAKDOWN_PAGES
            )
            if value is not None
            else None
        )

    @field_validator("title")
    @classmethod
    def _strip_optional_rule_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("requirement", "review_check")
    @classmethod
    def _strip_optional_rule_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class DesignRuleRead(_TimestampMixin):
    id: int
    feedback_id: int
    feedback_title: str | None = None
    title: str
    kind: DesignRuleKind
    target: DesignRuleTarget
    slot: DesignRuleSlot
    scope_type: DesignRuleScopeType
    story_id: int | None = None
    story_name: str | None = None
    chapter_numbers: list[int] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list)
    priority: DesignRulePriority
    requirement: str
    negative_terms: list[str] = Field(default_factory=list)
    review_check: str
    check_spec: dict = Field(default_factory=dict)
    status: DesignRuleStatus
    version: int
    created_by: DesignRuleCreatedBy
    check_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    latest_result: str | None = None
    template_applied_at: datetime | None = None
    coverage_run_id: int | None = None
    coverage_status: str | None = None
    coverage_total: int = 0
    coverage_pending: int = 0
    coverage_updated_at: datetime | None = None

    @field_serializer("template_applied_at", "coverage_updated_at")
    def _serialize_template_applied_at(
        self, value: datetime | None
    ) -> str | None:
        return utc_iso(value)


class DesignRuleRevisionRead(BaseModel):
    id: int
    rule_id: int
    version: int
    change_note: str
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return utc_iso(value) or ""


class DesignRuleTemplatePreviewItem(BaseModel):
    template_type: Literal["body", "cover"]
    before: str
    after: str
    inserted_block: str


class DesignRuleTemplatePreview(BaseModel):
    items: list[DesignRuleTemplatePreviewItem] = Field(default_factory=list)


class DesignRuleTemplateApplyResult(BaseModel):
    templates: PromptTemplatesRead
    rule: DesignRuleRead
    applied_template_types: list[Literal["body", "cover"]] = Field(
        default_factory=list
    )


class DesignRuleOnceTarget(BaseModel):
    target_type: Literal["cover", "body"]
    story_id: int = Field(ge=1)
    chapter_number: int = Field(ge=1, le=MAX_CHAPTERS)
    page_number: int | None = Field(
        default=None, ge=1, le=MAX_BREAKDOWN_PAGES
    )

    @model_validator(mode="after")
    def _validate_once_target(self) -> "DesignRuleOnceTarget":
        if self.target_type == "body" and self.page_number is None:
            raise ValueError("正文页仅本次应用必须填写章内页码")
        if self.target_type == "cover" and self.page_number is not None:
            raise ValueError("封面仅本次应用不能填写页码")
        return self


class DesignRuleOncePreview(BaseModel):
    target_type: Literal["cover", "body"]
    story_id: int
    chapter_number: int
    page_number: int | None = None
    before: str
    after: str
    inserted_block: str


class DesignRuleOnceApplyResult(BaseModel):
    rule: DesignRuleRead
    target_type: Literal["cover", "body"]
    story_id: int
    chapter_number: int
    page_number: int | None = None
    prompt: str


class DesignRuleResultCreate(BaseModel):
    result: Literal["passed", "failed", "unknown"]
    story_id: int = Field(ge=1)
    target_type: Literal["cover", "body", "guide", "other"]
    chapter_number: int | None = Field(default=None, ge=1, le=MAX_CHAPTERS)
    page_number: int | None = Field(
        default=None, ge=1, le=MAX_BREAKDOWN_PAGES
    )
    message: str = Field(
        default="", max_length=MAX_DESIGN_FEEDBACK_SUMMARY_LENGTH
    )
    image_url: str | None = Field(
        default=None, max_length=MAX_DESIGN_FEEDBACK_IMAGE_URL_LENGTH
    )
    snapshot_id: int | None = Field(default=None, ge=1)
    reviewer: Literal["claude", "user"] = "claude"

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        return value.strip()

    @field_validator("image_url")
    @classmethod
    def _strip_image_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _validate_target(self) -> "DesignRuleResultCreate":
        if self.target_type in ("cover", "guide") and self.chapter_number is None:
            raise ValueError("封面 / 引导卡核验必须填写章节号")
        if self.target_type == "page" and self.page_number is None:
            raise ValueError("正文页核验必须填写页码")
        return self


class DesignRuleResultRead(BaseModel):
    id: int
    rule_id: int
    story_id: int
    target_type: Literal["cover", "body", "guide", "other"]
    chapter_number: int | None = None
    page_number: int | None = None
    result: Literal["passed", "failed", "unknown"]
    message: str
    image_url: str | None = None
    snapshot_id: int | None = None
    reviewer: Literal["claude", "user"]
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return utc_iso(value) or ""


class DesignRulePreviewRequest(BaseModel):
    target: DesignRuleTarget
    scope_type: DesignRuleScopeType
    story_id: int | None = Field(default=None, ge=1)
    chapter_numbers: list[int] = Field(
        default_factory=list, max_length=MAX_CHAPTERS
    )
    page_numbers: list[int] = Field(
        default_factory=list, max_length=MAX_BREAKDOWN_PAGES
    )

    @field_validator("chapter_numbers")
    @classmethod
    def _clean_preview_chapters(cls, value: list[int]) -> list[int]:
        return _unique_positive_ints(
            value, label="章节号", maximum=MAX_CHAPTERS
        )

    @field_validator("page_numbers")
    @classmethod
    def _clean_preview_pages(cls, value: list[int]) -> list[int]:
        return _unique_positive_ints(
            value, label="章内页码", maximum=MAX_BREAKDOWN_PAGES
        )

    @model_validator(mode="after")
    def _validate_preview(self) -> "DesignRulePreviewRequest":
        story_id, chapters, pages = _validate_rule_scope(
            self.scope_type,
            self.target,
            self.story_id,
            self.chapter_numbers,
            self.page_numbers,
        )
        self.story_id = story_id
        self.chapter_numbers = chapters
        self.page_numbers = pages
        return self


class DesignRulePreviewRead(BaseModel):
    cover: int = 0
    body: int = 0
    guide: int = 0
    total: int = 0
    samples: list[str] = Field(default_factory=list)


class DesignRuleApplied(BaseModel):
    id: int
    title: str
    kind: DesignRuleKind
    target: DesignRuleTarget
    scope_type: DesignRuleScopeType
    priority: DesignRulePriority
    requirement: str
    negative_terms: list[str] = Field(default_factory=list)
    review_check: str = ""


class DesignFeedbackApplicationCreate(BaseModel):
    """记录一次建议应用；目标定位与改前 / 改后快照。"""

    target_type: DesignFeedbackTargetType
    story_id: int = Field(ge=1)
    chapter_number: int | None = Field(default=None, ge=1, le=MAX_CHAPTERS)
    page_number: int | None = Field(
        default=None, ge=1, le=MAX_BREAKDOWN_PAGES
    )
    summary: str = Field(
        min_length=1, max_length=MAX_DESIGN_FEEDBACK_SUMMARY_LENGTH
    )
    before_prompt: str | None = Field(
        default=None, max_length=MAX_DESIGN_FEEDBACK_PROMPT_LENGTH
    )
    after_prompt: str | None = Field(
        default=None, max_length=MAX_DESIGN_FEEDBACK_PROMPT_LENGTH
    )
    before_image_url: str | None = Field(
        default=None, max_length=MAX_DESIGN_FEEDBACK_IMAGE_URL_LENGTH
    )
    after_image_url: str | None = Field(
        default=None, max_length=MAX_DESIGN_FEEDBACK_IMAGE_URL_LENGTH
    )

    @field_validator("summary")
    @classmethod
    def _strip_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator(
        "before_prompt",
        "after_prompt",
        "before_image_url",
        "after_image_url",
    )
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _validate_target(self) -> "DesignFeedbackApplicationCreate":
        if self.target_type in ("cover", "guide") and self.chapter_number is None:
            raise ValueError("封面 / 引导卡应用必须填写章节号")
        if self.target_type == "page" and self.page_number is None:
            raise ValueError("正文页应用必须填写页码")
        return self


class DesignFeedbackApplicationRead(BaseModel):
    """应用记录；story_name 由服务层计算。"""

    id: int
    feedback_id: int
    target_type: DesignFeedbackTargetType
    story_id: int
    story_name: str | None = None
    chapter_number: int | None = None
    page_number: int | None = None
    summary: str
    before_prompt: str | None = None
    after_prompt: str | None = None
    before_image_url: str | None = None
    after_image_url: str | None = None
    applied_at: datetime

    @field_serializer("applied_at")
    def _serialize_applied_at(self, value: datetime) -> str:
        return utc_iso(value) or ""


class DesignFeedbackDetail(DesignFeedbackRead):
    applications: list[DesignFeedbackApplicationRead] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 故事拆解 / 分镜
# ---------------------------------------------------------------------------

StoryboardShotType = Literal["全景", "中景", "特写"]


class CharacterCard(BaseModel):
    """角色设定卡：一段外形描述覆盖发型、长相、年龄感、服装、配饰与体态。"""

    name: str = Field(min_length=1, max_length=MAX_CHARACTER_NAME_LENGTH)
    role: str = Field(default="", max_length=MAX_CHARACTER_ROLE_LENGTH)
    appearance: str = Field(
        min_length=1, max_length=MAX_CHARACTER_APPEARANCE_LENGTH
    )
    # 角色资产图文件名（服务端生成，仅本地存档）；与角色名解耦，改名不丢图
    asset_filename: str | None = Field(default=None, max_length=64)

    @field_validator("name", "appearance")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("role")
    @classmethod
    def _strip_optional(cls, value: str) -> str:
        return value.strip()

    @field_validator("asset_filename")
    @classmethod
    def _validate_asset_filename(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not CHARACTER_ASSET_FILENAME_PATTERN.fullmatch(value):
            raise ValueError("角色资产图文件名不合法")
        return value


class CharacterCardRead(CharacterCard):
    """角色卡读取模型：额外带上资产图访问地址（不接受写入）。"""

    asset_url: str | None = None


class StoryboardPagePayload(BaseModel):
    """单页分镜的写入内容；页码由 URL 提供，不放在请求体里。"""

    # 来源对照段号：本页由 mapping 的哪一段生成。
    # 旧数据可能没有该字段；写入时未提供则保留原值。
    mapping_page_number: int | None = Field(
        default=None, ge=1, le=MAX_BREAKDOWN_PAGES
    )
    # 所属章节与章内页码；未启用章节的旧数据为空。
    chapter_number: int | None = Field(default=None, ge=1, le=MAX_CHAPTERS)
    chapter_page_number: int | None = Field(
        default=None, ge=1, le=MAX_CHAPTER_CONTENT_PAGES
    )
    is_flashback: bool = False
    # 本页在故事中的作用，例如「钩子封面」「铺垫」「冲突」「反转」「爆点」「情绪高潮」「收尾」
    page_role: str = Field(default="", max_length=MAX_PAGE_ROLE_LENGTH)
    story_content: str = Field(min_length=1, max_length=MAX_PAGE_TEXT_LENGTH)
    characters: list[str] = Field(
        default_factory=list, max_length=MAX_PAGE_CHARACTERS
    )
    character_review: str = Field(
        min_length=1, max_length=MAX_PAGE_TEXT_LENGTH
    )
    scene: str = Field(min_length=1, max_length=MAX_PAGE_TEXT_LENGTH)
    action_state: str = Field(min_length=1, max_length=MAX_PAGE_TEXT_LENGTH)
    change_note: str = Field(min_length=1, max_length=MAX_PAGE_TEXT_LENGTH)
    narration_main: str = Field(
        min_length=1, max_length=MAX_PAGE_SHORT_TEXT_LENGTH
    )
    narration_highlight: str = Field(
        default="", max_length=MAX_PAGE_HIGHLIGHT_LENGTH
    )
    narration_sub: str = Field(min_length=1, max_length=MAX_PAGE_TEXT_LENGTH)
    dialogues: list[str] = Field(
        default_factory=list, max_length=MAX_PAGE_DIALOGUES
    )
    shot_type: StoryboardShotType
    # 机位方位（如「过肩视角」「俯视·侧面」）；允许为空以兼容旧数据，新拆解由技能强制填写
    camera_angle: str = Field(default="", max_length=MAX_PAGE_CAMERA_ANGLE_LENGTH)
    image_prompt: str = Field(
        min_length=1, max_length=MAX_PAGE_IMAGE_PROMPT_LENGTH
    )

    @field_validator(
        "story_content",
        "character_review",
        "scene",
        "action_state",
        "change_note",
        "narration_main",
        "narration_sub",
        "image_prompt",
    )
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("narration_highlight", "page_role", "camera_angle")
    @classmethod
    def _strip_optional_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("characters")
    @classmethod
    def _validate_characters(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = value.strip()
            if not value:
                raise ValueError("出场人物不能为空")
            if len(value) > MAX_CHARACTER_NAME_LENGTH:
                raise ValueError(
                    f"角色名不能超过 {MAX_CHARACTER_NAME_LENGTH} 字"
                )
            cleaned.append(value)
        return cleaned

    @field_validator("dialogues")
    @classmethod
    def _validate_dialogues(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = value.strip()
            if not value:
                raise ValueError("台词不能为空")
            if len(value) > MAX_PAGE_DIALOGUE_LENGTH:
                raise ValueError(
                    f"单句台词不能超过 {MAX_PAGE_DIALOGUE_LENGTH} 字"
                )
            cleaned.append(value)
        return cleaned


class StoryboardPageRead(StoryboardPagePayload):
    page_number: int = Field(ge=1, le=MAX_BREAKDOWN_PAGES)
    # 图片上显示的页码：有章内页码时用章内页码，否则回退全局页码。
    # 由服务端计算，不接受写入，避免前端/复制/导出各自推导。
    display_page_number: int | None = Field(default=None, ge=1)
    # 成品图访问地址；有图即视为该页已完成。由服务端按文件是否存在计算，不接受写入
    image_url: str | None = None


class ImageIngestPayload(BaseModel):
    """外部生图接口回传一张图片：URL 或 base64 二选一。"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "image_url": "https://example.com/story4/ch3-p1.png"
                },
                {
                    "image_base64": "iVBORw0KGgo...",
                    "filename": "ch3-p1.png",
                },
            ]
        }
    )

    image_url: str | None = Field(
        default=None,
        max_length=2048,
        description=(
            "公网可访问的图片地址，后端会主动下载；"
            "与 image_base64 二选一"
        ),
        examples=["https://example.com/story4/ch3-p1.png"],
    )
    image_base64: str | None = Field(
        default=None,
        description=(
            "图片 base64，可带 data:image/png;base64, 前缀；"
            "与 image_url 二选一"
        ),
        examples=["iVBORw0KGgo..."],
    )
    filename: str | None = Field(
        default=None,
        max_length=128,
        description="可选文件名，只用于判断图片格式；省略时按图片头推断",
        examples=["ch3-p1.png"],
    )

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "ImageIngestPayload":
        has_url = bool((self.image_url or "").strip())
        has_base64 = bool((self.image_base64 or "").strip())
        if has_url == has_base64:
            raise ValueError("image_url 和 image_base64 必须且只能提供一个")
        return self


class ImageBatchIngestItem(ImageIngestPayload):
    """批量回传中的一张正文页图片：页码 + URL 或 base64。"""

    page_number: int = Field(
        ge=1,
        le=MAX_BREAKDOWN_PAGES,
        description="全局页码，不是章内页码",
        examples=[17],
    )


class ImageBatchIngestRequest(BaseModel):
    """批量回传正文页成品图：一次最多 20 张。"""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "page_number": 17,
                            "image_url": "https://example.com/story4/p17.png",
                        },
                        {
                            "page_number": 18,
                            "image_base64": "iVBORw0KGgo...",
                            "filename": "page-0018.png",
                        },
                    ]
                }
            ]
        }
    )

    items: list[ImageBatchIngestItem] = Field(
        min_length=1,
        max_length=MAX_BATCH_INGEST_ITEMS,
        description=(
            f"要回传的正文页列表，1–{MAX_BATCH_INGEST_ITEMS} 张；"
            "页码不能重复"
        ),
    )

    @model_validator(mode="after")
    def _unique_page_numbers(self) -> "ImageBatchIngestRequest":
        numbers = [item.page_number for item in self.items]
        if len(numbers) != len(set(numbers)):
            raise ValueError("items 里的 page_number 不能重复")
        return self


class ImageBatchIngestItemResult(BaseModel):
    """批量回传的单页结果；一项失败不影响其他项。"""

    page_number: int
    ok: bool
    image_url: str | None = None
    error: str | None = None
    code: str | None = None


class ImageBatchIngestResponse(BaseModel):
    """批量回传汇总：成功数、失败数与逐页结果。"""

    total: int
    succeeded: int
    failed: int
    items: list[ImageBatchIngestItemResult]


class CharacterAssetBatchIngestItem(ImageIngestPayload):
    """批量回传中的一张角色资产图：角色下标 + URL 或 base64。"""

    character_index: int = Field(
        ge=0,
        le=MAX_CHARACTER_CARDS - 1,
        description="characters 数组下标，从 0 开始",
        examples=[0],
    )


class CharacterAssetBatchIngestRequest(BaseModel):
    """批量回传角色资产图：一次最多 20 张。"""

    items: list[CharacterAssetBatchIngestItem] = Field(
        min_length=1,
        max_length=MAX_BATCH_INGEST_ITEMS,
        description=(
            f"要回传的角色资产图列表，1–{MAX_BATCH_INGEST_ITEMS} 张；"
            "character_index 不能重复"
        ),
    )

    @model_validator(mode="after")
    def _unique_character_indexes(self) -> "CharacterAssetBatchIngestRequest":
        indexes = [item.character_index for item in self.items]
        if len(indexes) != len(set(indexes)):
            raise ValueError("items 里的 character_index 不能重复")
        return self


class CharacterAssetBatchIngestItemResult(BaseModel):
    """批量回传的单角色结果；一项失败不影响其他项。"""

    character_index: int
    name: str | None = None
    ok: bool
    asset_url: str | None = None
    error: str | None = None
    code: str | None = None


class CharacterAssetBatchIngestResponse(BaseModel):
    """批量回传汇总：成功数、失败数与逐角色结果。"""

    total: int
    succeeded: int
    failed: int
    items: list[CharacterAssetBatchIngestItemResult]


AliasStampTarget = Literal["page", "cover", "guide"]


class AliasStampRequest(BaseModel):
    """批量给图片底部加别名；不传 alias 时使用故事已保存的知乎别名。"""

    alias: str | None = Field(
        default=None,
        max_length=20,
        description="可选，覆盖故事别名；必须是 6–8 个汉字",
    )
    chapter_number: int | None = Field(
        default=None, ge=1, le=MAX_CHAPTERS,
        description="只处理该 chapter 的封面、正文页、引导卡；不传则处理整个故事",
    )
    chapter_numbers: list[int] | None = Field(
        default=None,
        max_length=MAX_CHAPTERS,
        description="只处理这些章节；与 chapter_number 二选一",
    )
    page_numbers: list[int] | None = Field(
        default=None,
        max_length=MAX_BREAKDOWN_PAGES,
        description="只处理这些全局页码；不传则按章节或全故事处理",
    )

    @model_validator(mode="after")
    def _one_chapter_scope(self) -> "AliasStampRequest":
        if self.chapter_number is not None and self.chapter_numbers:
            raise ValueError("chapter_number 和 chapter_numbers 只能传一个")
        if self.chapter_numbers:
            if len(set(self.chapter_numbers)) != len(self.chapter_numbers):
                raise ValueError("chapter_numbers 不能重复")
        return self


class AliasStampItem(BaseModel):
    target: AliasStampTarget
    chapter_number: int | None = None
    page_number: int | None = None
    ok: bool
    error: str | None = None


class AliasStampResult(BaseModel):
    alias: str
    stamped: int
    failed: int
    items: list[AliasStampItem]
    backup_dir: str


class AliasRestoreResult(BaseModel):
    restored: int
    failed: int
    items: list[AliasStampItem]


class StoryboardMappingItem(BaseModel):
    """分镜对照表的一行：第几页对应优化文的哪一段。"""

    page_number: int = Field(ge=1, le=MAX_BREAKDOWN_PAGES)
    # 该页对应的优化文原文摘录，必须按原文顺序连续
    source_text: str = Field(min_length=1, max_length=MAX_PAGE_TEXT_LENGTH)
    # 给对照表看的一句话简述，不是最终副旁白
    summary: str = Field(default="", max_length=MAX_PAGE_SHORT_TEXT_LENGTH)
    # 例如「第3段」；part 例如「1/2」，便于定位拆分
    paragraph: str = Field(default="", max_length=50)
    part: str = Field(default="", max_length=20)
    # 已弃用：保留在对照表里维持全文覆盖，但不再分入任何章节
    excluded: bool = False

    @field_validator("source_text")
    @classmethod
    def _strip_mapping_source(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("原文摘录不能为空")
        return value

    @field_validator("summary", "paragraph", "part")
    @classmethod
    def _strip_mapping_optional(cls, value: str) -> str:
        return value.strip()


MappingChangeKind = Literal["split", "merge", "keep"]
MappingRisk = Literal["high", "medium", "low"]
MappingDecision = Literal["approved", "rejected", "undecided"]


class ProposedMappingSegment(BaseModel):
    """审阅提案里的一段：只改边界，不改原文。"""

    source_text: str = Field(min_length=1, max_length=MAX_PAGE_TEXT_LENGTH)
    summary: str = Field(default="", max_length=MAX_PAGE_SHORT_TEXT_LENGTH)
    paragraph: str = Field(default="", max_length=50)
    part: str = Field(default="", max_length=20)
    # 以下字段只用于审阅展示，不写入 mapping
    beat_type: str = Field(default="", max_length=20)
    time_place: str = Field(default="", max_length=200)
    characters: list[str] = Field(
        default_factory=list, max_length=MAX_PAGE_CHARACTERS
    )
    visual_load: int | None = Field(default=None, ge=1, le=3)

    @field_validator("source_text")
    @classmethod
    def _source_not_blank(cls, value: str) -> str:
        # 保留换行与首尾空白，保证逐字拼接可以校验
        if not value.strip():
            raise ValueError("原文摘录不能为空")
        return value

    @field_validator(
        "summary", "paragraph", "part", "beat_type", "time_place"
    )
    @classmethod
    def _strip_optional(cls, value: str) -> str:
        return value.strip()


class MappingReviewChange(BaseModel):
    """一条拆分 / 合并 / 保留提案。"""

    id: str = Field(min_length=1, max_length=80)
    kind: MappingChangeKind
    risk: MappingRisk = "medium"
    old_page_numbers: list[int] = Field(
        min_length=1, max_length=MAX_BREAKDOWN_PAGES
    )
    proposed_segments: list[ProposedMappingSegment] = Field(
        default_factory=list, max_length=MAX_BREAKDOWN_PAGES
    )
    reason: str = Field(default="", max_length=MAX_PAGE_TEXT_LENGTH)
    # 服务端计算，客户端传值会被覆盖
    page_delta: int = 0
    crosses_chapter: bool = False

    @field_validator("old_page_numbers")
    @classmethod
    def _ordered_old_pages(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("至少需要一个原对照段")
        if value != sorted(value) or len(set(value)) != len(value):
            raise ValueError("old_page_numbers 必须升序且不重复")
        if value != list(range(value[0], value[0] + len(value))):
            raise ValueError("old_page_numbers 必须是连续的原对照段")
        return value


class MappingReviewCreate(BaseModel):
    """创建 / 替换审阅草稿。"""

    changes: list[MappingReviewChange] = Field(
        min_length=1, max_length=MAX_BREAKDOWN_PAGES
    )


class MappingReviewDecisionUpdate(BaseModel):
    """保存人工决策。"""

    decisions: dict[str, MappingDecision] = Field(default_factory=dict)


class MappingReviewApply(BaseModel):
    """应用已同意的变更。"""

    clear_chapters: bool = False


class MappingReviewSummary(BaseModel):
    current_page_count: int
    proposed_page_count: int
    total_changes: int
    pending_count: int
    auto_approved_count: int
    rejected_count: int
    chapters_count: int
    chapters_locked: bool


class MappingReviewRead(BaseModel):
    id: int
    story_id: int
    status: Literal["draft", "applied", "discarded"]
    base_mapping_hash: str
    changes: list[MappingReviewChange]
    decisions: dict[str, MappingDecision]
    summary: MappingReviewSummary
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None = None


class ChapterCover(BaseModel):
    """章节封面：顶部小字 + 主旁白 + 副旁白 + 生图提示词。

    主旁白 ≤12 个汉字、副旁白 < 35 个汉字（标点不计）由前端自检把关；
    这里只限制最大长度，允许先占位后补。
    """

    label: str = Field(default="", max_length=MAX_CHAPTER_LABEL_LENGTH)
    narration_main: str = Field(default="", max_length=MAX_PAGE_SHORT_TEXT_LENGTH)
    narration_highlight: str = Field(
        default="", max_length=MAX_PAGE_HIGHLIGHT_LENGTH
    )
    narration_sub: str = Field(default="", max_length=MAX_PAGE_TEXT_LENGTH)
    image_prompt: str = Field(
        default="", max_length=MAX_PAGE_IMAGE_PROMPT_LENGTH
    )

    @field_validator(
        "label",
        "narration_main",
        "narration_highlight",
        "narration_sub",
        "image_prompt",
    )
    @classmethod
    def _strip_optional(cls, value: str) -> str:
        return value.strip()


class ChapterCoverRead(ChapterCover):
    image_url: str | None = None


class ChapterGuide(BaseModel):
    """章节末尾引导卡：主文案 + 下一章预告 / 主页简介引导。"""

    text: str = Field(default="", max_length=MAX_CHAPTER_GUIDE_TEXT_LENGTH)
    sub_text: str = Field(
        default="", max_length=MAX_CHAPTER_GUIDE_SUB_TEXT_LENGTH
    )
    image_prompt: str = Field(
        default="", max_length=MAX_PAGE_IMAGE_PROMPT_LENGTH
    )

    @field_validator("text", "sub_text", "image_prompt")
    @classmethod
    def _strip_optional(cls, value: str) -> str:
        return value.strip()


class ChapterGuideRead(ChapterGuide):
    image_url: str | None = None


class ChapterAssetArchiveRead(BaseModel):
    filename: str
    url: str
    bytes: int
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return utc_iso(value) or ""


class ChapterAssetArchiveRestoreResult(BaseModel):
    url: str


class StoryboardChapter(BaseModel):
    """一章 = 一篇小红书笔记：1 封面 + 1..16 正文档 + 1 引导卡。"""

    chapter_number: int = Field(ge=1, le=MAX_CHAPTERS)
    title: str = Field(min_length=1, max_length=MAX_CHAPTER_TITLE_LENGTH)
    # 本章使用的对照段号，必须按 mapping 顺序连续排列
    mapping_page_numbers: list[int] = Field(
        min_length=1, max_length=MAX_CHAPTER_CONTENT_PAGES
    )
    cover: ChapterCover = Field(default_factory=ChapterCover)
    guide: ChapterGuide = Field(default_factory=ChapterGuide)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("章节标题不能为空")
        return value

    @field_validator("mapping_page_numbers")
    @classmethod
    def _validate_mapping_pages(cls, values: list[int]) -> list[int]:
        for value in values:
            if value < 1 or value > MAX_BREAKDOWN_PAGES:
                raise ValueError("对照段号超出范围")
        if len(values) != len(set(values)):
            raise ValueError("同一章内对照段号不能重复")
        return values


class StoryboardChapterRead(StoryboardChapter):
    cover: ChapterCoverRead = Field(default_factory=ChapterCoverRead)
    guide: ChapterGuideRead = Field(default_factory=ChapterGuideRead)


class StoryBreakdownUpdate(BaseModel):
    """拆解头部信息的局部更新；未提供的字段保持不变。"""

    optimized_content: str | None = Field(
        default=None, max_length=MAX_BREAKDOWN_CONTENT_LENGTH
    )
    characters: list[CharacterCard] | None = Field(
        default=None, max_length=MAX_CHARACTER_CARDS
    )
    # 两步拆解的第一步：分镜对照表；只写表，不写分镜页
    mapping: list[StoryboardMappingItem] | None = Field(
        default=None, max_length=MAX_BREAKDOWN_PAGES
    )
    # 章节发布分组：chapter 必须按对照表顺序覆盖全部未弃用段
    chapters: list[StoryboardChapter] | None = Field(
        default=None, max_length=MAX_CHAPTERS
    )
    # 旧流程字段，保留兼容；新流程不再写入人物合影提示词
    group_photo_prompt: str | None = Field(
        default=None, max_length=MAX_CHARACTER_GROUP_PROMPT_LENGTH
    )

    @field_validator("optimized_content")
    @classmethod
    def _strip_optimized(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("优化后文章不能为空")
        return value

    @field_validator("group_photo_prompt")
    @classmethod
    def _strip_group_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def _require_any_field(self) -> "StoryBreakdownUpdate":
        if (
            self.optimized_content is None
            and self.characters is None
            and self.mapping is None
            and self.chapters is None
            and self.group_photo_prompt is None
        ):
            raise ValueError("没有需要更新的内容")
        return self


class OptimizationChangeNote(BaseModel):
    """AI 对单处改动的解读：类型、原文、优化后与原因。"""

    kind: str = Field(min_length=1, max_length=20)
    original: str = Field(default="", max_length=MAX_OPTIMIZE_ANALYZE_QUOTE_LENGTH)
    optimized: str = Field(default="", max_length=MAX_OPTIMIZE_ANALYZE_QUOTE_LENGTH)
    why: str = Field(min_length=1, max_length=MAX_OPTIMIZE_ANALYZE_REASON_LENGTH)

    @field_validator("kind", "original", "optimized", "why")
    @classmethod
    def _strip_fields(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _require_reason(self) -> "OptimizationChangeNote":
        if not self.why:
            raise ValueError("改动原因不能为空")
        return self


class StoryOptimizationAnalysis(BaseModel):
    """原文与优化文的 AI 解读结果。"""

    summary: str = Field(min_length=1, max_length=MAX_OPTIMIZE_ANALYZE_SUMMARY_LENGTH)
    changes: list[OptimizationChangeNote] = Field(
        default_factory=list, max_length=MAX_OPTIMIZE_ANALYZE_CHANGES
    )

    @field_validator("summary")
    @classmethod
    def _strip_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("总结不能为空")
        return value


class StoryBreakdownRead(_TimestampMixin):
    id: int
    story_id: int
    optimized_content: str
    characters: list[CharacterCardRead]
    group_photo_prompt: str
    # 最终确认的人物合照访问地址；由服务端按文件是否存在计算，不接受写入
    group_photo_url: str | None = None
    # 分镜对照表；两步拆解的第一步产物
    mapping: list[StoryboardMappingItem]
    # 章节发布分组；空列表表示未启用章节
    chapters: list[StoryboardChapterRead] = Field(default_factory=list)
    pages: list[StoryboardPageRead]
    # 生成时使用的画风快照；画风被删除时仍保留旧值
    art_style_id: str | None = None
    art_style_name: str | None = None
    art_style_content: str | None = None
    # 由后端对比当前故事计算：原文已更新 / 画风已变更
    is_content_stale: bool = False
    is_art_style_stale: bool = False


class MappingReviewApplyResult(BaseModel):
    """应用结果：返回新 breakdown，并标明严格连续与章节是否被清空。"""

    breakdown: StoryBreakdownRead
    strict_coverage: bool
    chapters_cleared: bool


# ---------------------------------------------------------------------------
# 每条故事一份的小红书发文配置
# ---------------------------------------------------------------------------


def _clean_publish_tags(values: list[str] | None) -> list[str]:
    """发布标签：去空白、去开头的 #、去重，并限制数量与单标签长度。"""
    cleaned: list[str] = []
    for value in values or []:
        value = value.strip().lstrip("#").strip()
        if not value:
            continue
        if len(value) > MAX_PUBLISH_TAG_LENGTH:
            raise ValueError(f"单个标签不能超过 {MAX_PUBLISH_TAG_LENGTH} 字")
        if value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > MAX_PUBLISH_TAGS:
        raise ValueError(f"标签最多 {MAX_PUBLISH_TAGS} 个")
    return cleaned


class StoryPostConfigUpdate(BaseModel):
    """全量保存发文配置；标题与正文都允许为空。

    标题限制 18 字：小红书信息流第一眼只能看到标题与第 1 页封面，
    过长会被折叠，也容易分散注意力。
    """

    title: str = Field(default="", max_length=MAX_POST_CONFIG_TITLE_LENGTH)
    content: str = Field(default="", max_length=MAX_POST_CONTENT_LENGTH)
    # 只有章节配置会保存标签；旧版整篇故事配置忽略该字段。
    tags: list[str] = Field(default_factory=list)

    @field_validator("title", "content")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, value: list[str]) -> list[str]:
        return _clean_publish_tags(value)


class StoryPostConfigRead(_TimestampMixin):
    id: int
    story_id: int
    title: str
    content: str


class StoryChapterPostConfigRead(_TimestampMixin):
    """一章一份的小红书文案；chapter_number 对应 breakdown.chapters。"""

    id: int
    story_id: int
    chapter_number: int
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 发文
# ---------------------------------------------------------------------------


class PostCreate(BaseModel):
    story_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=MAX_POST_TITLE_LENGTH)
    content: str = Field(min_length=1, max_length=MAX_POST_CONTENT_LENGTH)
    status: PostStatus = "draft"

    @field_validator("title", "content")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_POST_TITLE_LENGTH)
    content: str | None = Field(default=None, max_length=MAX_POST_CONTENT_LENGTH)
    status: PostStatus | None = None

    @field_validator("title", "content")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class PostRead(_TimestampMixin):
    id: int
    story_id: int
    story_name: str
    title: str
    content: str
    status: PostStatus


class GenerateRequest(BaseModel):
    story_id: int = Field(gt=0)
    # 指定章节时只生成该章文案；为空时沿用旧版整篇故事生成
    chapter_number: int | None = Field(default=None, ge=1, le=MAX_CHAPTERS)


class GeneratedCopyOption(BaseModel):
    """一个可选文案方案：方案名、特点、标题正文，以及是否为推荐方案。"""

    style: str = Field(min_length=1, max_length=MAX_COPY_OPTION_STYLE_LENGTH)
    feature: str = Field(min_length=1, max_length=MAX_COPY_OPTION_FEATURE_LENGTH)
    title: str = Field(min_length=1, max_length=MAX_POST_CONFIG_TITLE_LENGTH)
    content: str = Field(min_length=1, max_length=MAX_POST_CONTENT_LENGTH)
    recommended: bool = False
    recommend_reason: str = Field(default="", max_length=MAX_COPY_OPTION_REASON_LENGTH)


class GeneratedCopyOptions(BaseModel):
    """DeepSeek 原始输出。

    契约要求 3 个方案；这里放宽到 2～4 个，模型偶尔多给/少给时仍能展示，
    避免整次生成因为数量偏差直接失败。
    """

    options: list[GeneratedCopyOption] = Field(min_length=2, max_length=4)


class GenerateResponse(BaseModel):
    story_id: int
    chapter_number: int | None = None
    options: list[GeneratedCopyOption]


class DesignRuleCoverageConfirm(BaseModel):
    item_keys: list[str] = Field(min_length=1, max_length=2000)
    status: str = Field(pattern="^(covered|missing)$")
    note: str = Field(default="", max_length=500)


class DesignRuleCoverageRunRead(BaseModel):
    id: int
    rule_id: int
    feedback_id: int
    rule_version: int
    scope_snapshot: dict = Field(default_factory=dict)
    status: str
    total: int
    processed: int
    covered: int
    partial: int
    missing: int
    pending: int
    error_count: int
    items: list[dict] = Field(default_factory=list)
    error_message: str = ""
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ---------------------------------------------------------------------------
# 多平台发布（抖音 / 小红书）
# ---------------------------------------------------------------------------


def _normalize_schedule(value: datetime | None) -> datetime | None:
    """无时区输入按北京时间理解，统一转成带时区的值。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=PUBLISH_TIMEZONE)
    return value


class PublishTagPresetsRead(BaseModel):
    tags: list[str] = Field(default_factory=list)


class XhsDeclarationOptionRead(BaseModel):
    """小红书内容声明的一个可选项；value 即写回与预检使用的文案。"""

    value: str
    label: str


class XhsDeclarationOptionsRead(BaseModel):
    """平台内容声明的全部可选文案；前端只渲染，不自行维护列表。"""

    options: list[XhsDeclarationOptionRead] = Field(default_factory=list)
    default: str
    # 「来源转载」需要额外填写媒体名，前端据此显示输入框
    repost_value: str


class PublishTagPresetsUpdate(BaseModel):
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, value: list[str]) -> list[str]:
        return _clean_publish_tags(value)


class PublishAccountRead(_TimestampMixin):
    id: int
    platform: PublishPlatform
    account_name: str
    display_name: str
    status: PublishAccountStatus
    last_checked_at: datetime | None = None

    @field_serializer("last_checked_at")
    def _serialize_checked_at(self, value: datetime | None) -> str | None:
        return utc_iso(value)


class PublishImageRead(BaseModel):
    """预览用图片：label 是发布顺序中的位置，url 是 /uploads 地址。"""

    label: str
    url: str
    filename: str


class PublishPreviewRequest(BaseModel):
    story_id: int = Field(gt=0)
    chapter_number: int = Field(ge=1)
    platform: PublishPlatform = "douyin"
    account_id: int = Field(gt=0)
    publish_mode: PublishMode = "scheduled"
    schedule_at: datetime | None = None

    @field_validator("schedule_at")
    @classmethod
    def _normalize(cls, value: datetime | None) -> datetime | None:
        return _normalize_schedule(value)


PreflightStatus = Literal["pass", "warning", "error"]
PreflightGroup = Literal["content", "alias", "images", "account", "platform"]
PreflightAction = Literal[
    "stamp_alias", "check_login", "open_zhihu", "open_chapters", "open_post_config"
]


class PreflightCheckItemRead(BaseModel):
    label: str
    status: PreflightStatus


class PreflightCheckRead(BaseModel):
    key: str
    group: PreflightGroup
    label: str
    status: PreflightStatus
    message: str
    action: PreflightAction | None = None
    action_label: str | None = None
    items: list[PreflightCheckItemRead] = Field(default_factory=list)


class PublishPreviewRead(BaseModel):
    platform: PublishPlatform
    publish_mode: PublishMode
    account: PublishAccountRead
    title: str
    note: str
    tags: list[str] = Field(default_factory=list)
    images: list[PublishImageRead] = Field(default_factory=list)
    image_count: int = 0
    title_length: int = 0
    note_length: int = 0
    schedule_at: datetime | None = None
    schedule_min_at: datetime
    schedule_max_at: datetime
    payload_hash: str | None = None
    source_hash: str | None = None
    # 小红书发布设置：声明文案、来源媒体名与合集名；抖音恒为 None
    declaration: str | None = None
    repost_source: str | None = None
    collection: str | None = None
    checks: list[PreflightCheckRead] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_serializer("schedule_at", "schedule_min_at", "schedule_max_at")
    def _serialize_schedule(self, value: datetime | None) -> str | None:
        return utc_iso(value)


class PublishJobCreate(PublishPreviewRequest):
    """创建任务必须带上预览返回的哈希，证明用户看过同一份载荷。"""

    preview_hash: str = Field(min_length=64, max_length=64)
    confirm: bool = False


class PublishPayloadRead(BaseModel):
    platform: PublishPlatform
    mode: PublishMode = "scheduled"
    account_name: str
    title: str
    note: str
    tags: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    schedule_at: datetime | None = None
    # 小红书发布设置；抖音或历史载荷没有这几项时按不声明、不加入合集处理
    declaration: str | None = None
    repost_source: str | None = None
    collection: str | None = None

    @field_serializer("schedule_at")
    def _serialize_schedule(self, value: datetime | None) -> str | None:
        return utc_iso(value)


class PublishJobRead(_TimestampMixin):
    id: str
    story_id: int
    chapter_number: int
    platform: PublishPlatform
    account_id: int
    status: PublishJobStatus
    scheduled_at: datetime
    payload: PublishPayloadRead
    payload_hash: str
    source_hash: str
    snapshot_dir: str
    external_url: str
    exit_code: int | None = None
    stdout_excerpt: str
    error_message: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log_available: bool = False

    @field_serializer("scheduled_at", "started_at", "finished_at")
    def _serialize_times(self, value: datetime | None) -> str | None:
        return utc_iso(value)


class PublishJobPatch(BaseModel):
    """人工核对：修正状态（unknown → scheduled/failed）或回填作品链接。"""

    status: Literal["scheduled", "failed", "published"] | None = None
    external_url: str | None = Field(default=None, max_length=500)

    @field_validator("external_url")
    @classmethod
    def _strip_url(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class PublishJobLogRead(BaseModel):
    job_id: str
    text: str
    truncated: bool = False


class PublishLoginRead(BaseModel):
    message: str


class TerminalLaunchRead(BaseModel):
    """打开本机终端的结果；仅用于展示，不写库。"""

    terminal: str
    directory: str
    message: str
