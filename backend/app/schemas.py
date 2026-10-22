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
    MAX_ART_STYLE_NAME_LENGTH,
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

    id: str = Field(min_length=1, max_length=64)
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
    name: str = Field(min_length=1, max_length=MAX_STORY_NAME_LENGTH)
    content: str = Field(min_length=1, max_length=MAX_STORY_CONTENT_LENGTH)
    cover_filename: str | None = Field(default=None, max_length=64)

    @field_validator("name", "content")
    @classmethod
    def _strip_required(cls, value: str) -> str:
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


class UploadRead(BaseModel):
    filename: str
    url: str


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
