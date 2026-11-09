"""正文 / 封面提示词模板：读取、校验、统一渲染。"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    BODY_PROMPT_TEMPLATE_KEY,
    BODY_TEMPLATE_REQUIRED,
    COVER_PROMPT_TEMPLATE_KEY,
    COVER_TEMPLATE_REQUIRED,
    DEFAULT_BODY_NEGATIVE_PROMPT,
    DEFAULT_BODY_PROMPT_TEMPLATE,
    DEFAULT_CHARACTER_GENDER_RULE,
    DEFAULT_COVER_MODE,
    DEFAULT_COVER_PROMPT_TEMPLATE,
    DEFAULT_COVER_IMPACT_NEGATIVE_TERMS,
    DEFAULT_COVER_NEGATIVE_PROMPT,
    MAX_PAGE_IMAGE_PROMPT_LENGTH,
    MAX_PROMPT_TEMPLATE_LENGTH,
    PROMPT_TEMPLATE_PLACEHOLDERS,
)
from ..crud import get_art_styles, get_setting, upsert_setting
from ..errors import AppError
from ..models import PromptTemplateVersion, Story
from .design_rules import (
    compile_rule_fragments,
    evaluate_check_rules,
    matching_rules,
)

PLACEHOLDER_PATTERN = re.compile(r"\{([a-z_]+)\}")

BODY_ALLOWED = {
    "art_style",
    "content",
    "character_consistency",
    "text_zone",
    "page_number",
    "negative_prompt",
}
COVER_ALLOWED = {
    "art_style",
    "content",
    "character_consistency",
    "text_zone",
    "cover_mode",
    "negative_prompt",
}


def get_prompt_templates(db: Session) -> dict:
    body_row = get_setting(db, BODY_PROMPT_TEMPLATE_KEY)
    cover_row = get_setting(db, COVER_PROMPT_TEMPLATE_KEY)
    body = (body_row.value if body_row is not None else "").strip()
    cover = (cover_row.value if cover_row is not None else "").strip()
    return {
        "body": body or DEFAULT_BODY_PROMPT_TEMPLATE,
        "cover": cover or DEFAULT_COVER_PROMPT_TEMPLATE,
        "body_default": DEFAULT_BODY_PROMPT_TEMPLATE,
        "cover_default": DEFAULT_COVER_PROMPT_TEMPLATE,
        "body_is_default": not body,
        "cover_is_default": not cover,
        "placeholders": list(PROMPT_TEMPLATE_PLACEHOLDERS),
    }


def _validate_template(template: str, template_type: str) -> str:
    value = (template or "").strip()
    if not value:
        raise AppError(422, "提示词模板不能为空", "PROMPT_TEMPLATE_EMPTY")
    if len(value) > MAX_PROMPT_TEMPLATE_LENGTH:
        raise AppError(
            422,
            f"提示词模板不能超过 {MAX_PROMPT_TEMPLATE_LENGTH} 字",
            "PROMPT_TEMPLATE_TOO_LONG",
        )
    allowed = BODY_ALLOWED if template_type == "body" else COVER_ALLOWED
    required = (
        BODY_TEMPLATE_REQUIRED
        if template_type == "body"
        else COVER_TEMPLATE_REQUIRED
    )
    found = set(PLACEHOLDER_PATTERN.findall(value))
    unknown = sorted(found - allowed)
    if unknown:
        raise AppError(
            422,
            f"{'正文' if template_type == 'body' else '封面'}模板包含未知占位符："
            + "、".join("{" + name + "}" for name in unknown),
            "PROMPT_TEMPLATE_UNKNOWN_PLACEHOLDER",
        )
    missing = [name for name in required if name not in found]
    if missing:
        raise AppError(
            422,
            f"{'正文' if template_type == 'body' else '封面'}模板缺少占位符："
            + "、".join("{" + name + "}" for name in missing),
            "PROMPT_TEMPLATE_MISSING_PLACEHOLDER",
        )
    return value


def save_prompt_templates(db: Session, body: str, cover: str) -> dict:
    body_value = _validate_template(body, "body")
    cover_value = _validate_template(cover, "cover")
    current = get_prompt_templates(db)
    for template_type, value, previous in (
        ("body", body_value, current["body"]),
        ("cover", cover_value, current["cover"]),
    ):
        if value != previous:
            db.add(
                PromptTemplateVersion(
                    template_type=template_type,
                    content=value,
                    note="保存模板",
                )
            )
    upsert_setting(db, BODY_PROMPT_TEMPLATE_KEY, body_value)
    upsert_setting(db, COVER_PROMPT_TEMPLATE_KEY, cover_value)
    db.commit()
    return get_prompt_templates(db)


def list_template_versions(
    db: Session, template_type: str, limit: int = 50
) -> list[dict]:
    rows = db.scalars(
        select(PromptTemplateVersion)
        .where(PromptTemplateVersion.template_type == template_type)
        .order_by(
            PromptTemplateVersion.created_at.desc(),
            PromptTemplateVersion.id.desc(),
        )
        .limit(max(1, min(limit, 100)))
    ).all()
    return [
        {
            "id": row.id,
            "template_type": row.template_type,
            "content": row.content,
            "note": row.note,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def restore_template_version(db: Session, version_id: int) -> dict:
    version = db.get(PromptTemplateVersion, version_id)
    if version is None:
        raise AppError(404, "模板版本不存在或已被删除", "PROMPT_TEMPLATE_VERSION_NOT_FOUND")
    value = _validate_template(version.content, version.template_type)
    if version.template_type == "body":
        upsert_setting(db, BODY_PROMPT_TEMPLATE_KEY, value)
    else:
        upsert_setting(db, COVER_PROMPT_TEMPLATE_KEY, value)
    db.add(
        PromptTemplateVersion(
            template_type=version.template_type,
            content=value,
            note=f"恢复 v{version.id}",
        )
    )
    db.commit()
    return get_prompt_templates(db)


def _split_dialogue(dialogue: str) -> tuple[str, str]:
    speaker, _, line = dialogue.partition("：")
    if not line:
        return "角色", dialogue
    return speaker.strip(), line.strip()


def _body_text_zone(context: dict) -> str:
    main = str(context.get("narration_main") or "").strip()
    sub = str(context.get("narration_sub") or "").strip()
    highlight = str(context.get("narration_highlight") or "").strip()
    dialogues = [str(item) for item in (context.get("dialogues") or [])]
    lines = [
        "【文字区】",
        "顶部留白：画面上方预留大面积干净的浅米色素描纸留白（保留纸张颗粒，不铺深色底纹、不压暗、无泛黄底色）。",
    ]
    main_red = bool(highlight and highlight in main)
    if main_red:
        count = len(highlight)
        lines.append(
            f"主旁白：只写一行完整的黑色手写体「{main}」；其中「{highlight}」"
            f"{count}字为红色手写加粗（红色、笔画比其余字粗），其余文字保持黑色不加粗。"
        )
        lines.append(
            f"绝对禁止：不得在主旁白下方或任何位置单独另起一行书写「{highlight}」"
            f"{count}字，除主旁白外不得出现任何其他红色文字，这一行之下不再写第二行相同文字。"
        )
    else:
        lines.append(
            f"主旁白：只写一行完整的黑色手写体「{main}」，全部文字保持黑色不加粗。"
        )

    sub_lines = [line for line in sub.splitlines() if line.strip()]
    if len(sub_lines) <= 1:
        first = sub_lines[0] if sub_lines else sub
        lines.append(
            f"副旁白：紧接主旁白下方，写一行较小的黑色手写体：「{first}」。"
            "副旁白文字须逐字呈现、不得改写，未给换行就写一行，不得替换姓名。"
        )
    else:
        lines.append(
            f"副旁白：紧接主旁白下方，写两行较小的黑色手写体：第一行「{sub_lines[0]}」；"
            f"第二行「{sub_lines[1]}」。副旁白文字须逐字呈现、不得改写，"
            "给定了换行就按换行写，不得替换姓名。"
        )

    # 主旁白已标红时，副旁白不再重复标红，避免两套互斥的「绝对禁止」同时出现。
    sub_red = bool(highlight and highlight in sub and not main_red)
    if sub_red:
        count = len(highlight)
        lines.append(
            f"其中「{highlight}」{count}字为红色手写加粗（红色、笔画比其余字粗），"
            "其余文字保持黑色不加粗。"
        )
        lines.append(
            f"绝对禁止：不得在副旁白下方或任何位置单独另起一行书写「{highlight}」"
            f"{count}字，除副旁白外不得出现任何其他红色文字，这一行之下不再写第二行相同文字。"
        )
    elif not main_red:
        lines.append(
            "绝对禁止：本页旁白文字全部保持黑色不加粗，不得出现任何红色文字，"
            "不得另起一行重复书写旁白中的任何文字。"
        )

    if dialogues:
        lines.append(
            "对话气泡（纯白色实心填充，黑色细手绘轮廓；不要米色、纸色、半透明或与背景同色；"
            "气泡内只画台词文字本身，不画说话人姓名、引号、冒号、序号等任何标注）："
        )
        for dialogue in dialogues:
            speaker, line = _split_dialogue(dialogue)
            lines.append(
                f"- 气泡文字：{line}｜说话人：{speaker}｜气泡位置：{speaker}头部一侧"
            )
    return "\n".join(lines)


def _cover_text_zone(context: dict) -> str:
    label = str(context.get("label") or "").strip()
    main = str(context.get("narration_main") or "").strip()
    sub = str(context.get("narration_sub") or "").strip()
    highlight = str(context.get("narration_highlight") or "").strip()
    lines = ["【文字区】"]
    if label:
        lines.append(f"顶部小字：{label}（小号黑色手写体）。")
    if highlight and highlight in main:
        count = len(highlight)
        lines.append(
            f"主标题：{main}（大号黑色手写体，整句一行；其中仅「{highlight}」"
            f"{count}字为红色手写加粗，内嵌在原句中，绝对禁止单独另起一行）。"
        )
    else:
        lines.append(f"主标题：{main}（大号黑色手写体，整句一行，全部文字保持黑色不加粗）。")
    lines.append(f"副标题：{sub}（较小黑色手写体，主标题下方一行）。")
    lines.append(
        "除以上文字外不得出现任何其他文字、页码、水印、logo、对话气泡。"
    )
    return "\n".join(lines)


def _render_text_zone(template_type: str, context: dict) -> str:
    if template_type == "cover":
        return _cover_text_zone(context)
    return _body_text_zone(context)


def render_prompt_template(
    *,
    template: str,
    template_type: str,
    style_content: str,
    context: dict,
    rule_fragments: dict | None = None,
) -> str:
    if template_type == "body" and not context.get("page_number"):
        raise AppError(422, "正文模板渲染需要 page_number", "PROMPT_RENDER_PAGE_REQUIRED")
    if not str(context.get("content") or "").strip():
        raise AppError(422, "提示词渲染需要 content", "PROMPT_RENDER_CONTENT_REQUIRED")

    content = str(context.get("content") or "").strip()
    text_zone = _render_text_zone(template_type, context)
    cover_mode = DEFAULT_COVER_MODE
    negative_prompt = (
        DEFAULT_COVER_NEGATIVE_PROMPT
        if template_type == "cover"
        else DEFAULT_BODY_NEGATIVE_PROMPT
    )
    if rule_fragments:
        scene_rules = rule_fragments.get("scene") or []
        cover_rules = rule_fragments.get("cover_mode") or []
        text_rules = rule_fragments.get("text_zone") or []
        negative_terms = rule_fragments.get("negative_terms") or []
        if scene_rules:
            content = f"{content}\n【规则要求】\n" + "\n".join(
                f"- {rule}" for rule in scene_rules
            )
        if cover_rules:
            cover_mode = f"{cover_mode}\n【规则要求】\n" + "\n".join(
                f"- {rule}" for rule in cover_rules
            )
        if text_rules:
            text_zone = f"{text_zone}\n【规则要求】\n" + "\n".join(
                f"- {rule}" for rule in text_rules
            )
        if negative_terms:
            negative_prompt = (
                f"{negative_prompt.rstrip('。')}，"
                + "，".join(dict.fromkeys(negative_terms))
            )
    if template_type == "cover":
        # 封面专属：专门拦「丑/脏/贴图感」的冲击线；正文不追加。
        negative_prompt = (
            f"{negative_prompt.rstrip('。')}，"
            f"{DEFAULT_COVER_IMPACT_NEGATIVE_TERMS}"
        )
    character_consistency = str(
        context.get("character_consistency") or ""
    ).strip()
    if character_consistency:
        character_consistency = (
            f"{character_consistency}\n{DEFAULT_CHARACTER_GENDER_RULE}"
        )
    values = {
        "art_style": style_content.strip(),
        "content": content,
        "character_consistency": character_consistency,
        "text_zone": text_zone,
        "page_number": str(context.get("page_number") or ""),
        "cover_mode": cover_mode,
        "negative_prompt": negative_prompt,
    }
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)

    remaining = sorted(set(PLACEHOLDER_PATTERN.findall(result)))
    if remaining:
        raise AppError(
            422,
            "渲染后仍存在未替换的占位符："
            + "、".join("{" + name + "}" for name in remaining),
            "PROMPT_TEMPLATE_UNRESOLVED_PLACEHOLDER",
        )
    if len(result) > MAX_PAGE_IMAGE_PROMPT_LENGTH:
        raise AppError(
            422,
            f"渲染后的提示词超过 {MAX_PAGE_IMAGE_PROMPT_LENGTH} 字",
            "PROMPT_RENDER_TOO_LONG",
        )
    return result


def _story_style_content(db: Session, story_id: int) -> str:
    story = db.get(Story, story_id)
    if story is None:
        raise AppError(404, "故事不存在或已被删除", "STORY_NOT_FOUND")
    styles, _ = get_art_styles(db)
    style = next(
        (item for item in styles if item["id"] == story.art_style_id),
        None,
    )
    if style is None:
        raise AppError(
            409,
            "故事还没有有效画风，请先到故事管理中选择画风",
            "ART_STYLE_REQUIRED",
        )
    return style["content"]


def render_for_story(
    db: Session,
    *,
    template_type: str,
    story_id: int,
    context: dict,
) -> tuple[str, list[dict], list[dict]]:
    templates = get_prompt_templates(db)
    template = templates["cover"] if template_type == "cover" else templates["body"]
    _validate_template(template, template_type)
    style_content = _story_style_content(db, story_id)
    rules = matching_rules(
        db,
        target="cover" if template_type == "cover" else "body",
        story_id=story_id,
        chapter_number=context.get("chapter_number"),
        page_number=context.get("page_number"),
    )
    fragments = compile_rule_fragments(rules)
    prompt = render_prompt_template(
        template=template,
        template_type=template_type,
        style_content=style_content,
        context=context,
        rule_fragments=fragments,
    )
    checks = evaluate_check_rules(rules, prompt, context)
    return prompt, fragments["applied"], checks
