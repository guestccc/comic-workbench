"""Pydantic 请求 / 响应模型。"""

from __future__ import annotations

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
    MAX_API_KEY_LENGTH,
    MAX_ART_STYLES,
    MAX_ART_STYLE_CONTENT_LENGTH,
    MAX_ART_STYLE_ID_LENGTH,
    MAX_ART_STYLE_NAME_LENGTH,
    MAX_BREAKDOWN_CONTENT_LENGTH,
    MAX_BREAKDOWN_PAGES,
    MAX_CHARACTER_APPEARANCE_LENGTH,
    MAX_CHARACTER_CARDS,
    MAX_CHARACTER_GROUP_PROMPT_LENGTH,
    MAX_CHARACTER_NAME_LENGTH,
    MAX_CHARACTER_ROLE_LENGTH,
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
    MAX_PROMPT_LENGTH,
    MAX_PROMPT_OPTIMIZE_MESSAGES,
    MAX_PROMPT_OPTIMIZE_TOTAL_CHARS,
    MAX_STORY_CONTENT_LENGTH,
    MAX_STORY_NAME_LENGTH,
)

PostStatus = Literal["draft", "published"]


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


class SettingsRead(BaseModel):
    prompt: str
    is_default: bool
    prompt_updated_at: datetime | None = None
    deepseek: DeepSeekStatus
    art_styles: list[ArtStyleItem] = Field(default_factory=list)
    active_art_style: str | None = None

    @field_serializer("prompt_updated_at")
    def _serialize_prompt_time(self, value: datetime | None) -> str | None:
        return utc_iso(value)


class PromptUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)

    @field_validator("content")
    @classmethod
    def _strip_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("启动提示词不能为空")
        return value


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


class StoryCreate(BaseModel):
    """新建故事；名称可留空，拆解后再补填。"""

    name: str = Field(default="", max_length=MAX_STORY_NAME_LENGTH)
    content: str = Field(min_length=1, max_length=MAX_STORY_CONTENT_LENGTH)
    cover_filename: str | None = Field(default=None, max_length=64)
    # 该故事拆解时使用的画风 id；为空表示尚未选择
    art_style_id: str | None = Field(
        default=None, max_length=MAX_ART_STYLE_ID_LENGTH
    )

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


class UploadRead(BaseModel):
    filename: str
    url: str


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


class StoryboardPagePayload(BaseModel):
    """单页分镜的写入内容；页码由 URL 提供，不放在请求体里。"""

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

    @field_validator("narration_highlight", "page_role")
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


class StoryBreakdownUpdate(BaseModel):
    """拆解头部信息的局部更新；未提供的字段保持不变。"""

    optimized_content: str | None = Field(
        default=None, max_length=MAX_BREAKDOWN_CONTENT_LENGTH
    )
    characters: list[CharacterCard] | None = Field(
        default=None, max_length=MAX_CHARACTER_CARDS
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
    characters: list[CharacterCard]
    group_photo_prompt: str
    pages: list[StoryboardPageRead]
    # 生成时使用的画风快照；画风被删除时仍保留旧值
    art_style_id: str | None = None
    art_style_name: str | None = None
    art_style_content: str | None = None
    # 由后端对比当前故事计算：原文已更新 / 画风已变更
    is_content_stale: bool = False
    is_art_style_stale: bool = False


# ---------------------------------------------------------------------------
# 每条故事一份的小红书发文配置
# ---------------------------------------------------------------------------


class StoryPostConfigUpdate(BaseModel):
    """全量保存发文配置；标题与正文都允许为空。

    标题限制 18 字：小红书信息流第一眼只能看到标题与第 1 页封面，
    过长会被折叠，也容易分散注意力。
    """

    title: str = Field(default="", max_length=MAX_POST_CONFIG_TITLE_LENGTH)
    content: str = Field(default="", max_length=MAX_POST_CONTENT_LENGTH)

    @field_validator("title", "content")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class StoryPostConfigRead(_TimestampMixin):
    id: int
    story_id: int
    title: str
    content: str


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


class GenerateResponse(BaseModel):
    story_id: int
    title: str
    content: str
