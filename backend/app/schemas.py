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
    MAX_PROMPT_LENGTH,
    MAX_PROMPT_OPTIMIZE_MESSAGES,
    MAX_PROMPT_OPTIMIZE_TOTAL_CHARS,
    MAX_STORY_CONTENT_LENGTH,
    MAX_STORY_NAME_LENGTH,
    MAX_ZHIHU_ALIASES,
    MAX_ZHIHU_ALIAS_LENGTH,
    MAX_ZHIHU_ARTICLE_ID_LENGTH,
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
    # 生图前置提示词：全局生效，复制角色卡与分镜提示词时自动拼在开头
    image_prefix_prompt: str = ""

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

    主旁白 < 15 个汉字、副旁白 < 35 个汉字（标点不计）由前端自检把关；
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


class StoryChapterPostConfigRead(_TimestampMixin):
    """一章一份的小红书文案；chapter_number 对应 breakdown.chapters。"""

    id: int
    story_id: int
    chapter_number: int
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
