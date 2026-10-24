"""知乎推广信息：别名格式校验与正文别名开头同步。"""

from __future__ import annotations

import re

from ..errors import AppError

# 别名只允许中文，6–8 个字
ALIAS_PATTERN = re.compile(r"[一-鿿]{6,8}")
# 正文开头可能已有的【别名】行
LEADING_ALIAS_PATTERN = re.compile(r"^\s*【[^】]{1,20}】\s*")


def title_bigrams(title: str) -> set[str]:
    """提取标题中的连续两个字，用于判断别名是否复用了原文文案。"""
    chars = "".join(
        char for char in title if "一" <= char <= "鿿"
    )
    return {
        chars[index : index + 2]
        for index in range(max(0, len(chars) - 1))
        if len(chars[index : index + 2]) == 2
    }


def validate_alias(title: str, alias: str) -> None:
    """校验别名格式，并禁止复用原文标题里的连续两个字。"""
    if not ALIAS_PATTERN.fullmatch(alias):
        raise AppError(
            422,
            "别名必须是 6–8 个汉字，不能包含字母、数字、标点或空格",
            "INVALID_ZHIHU_ALIAS",
        )
    if not title:
        raise AppError(
            422,
            "填写别名前请先填写知乎原文标题",
            "ZHIHU_TITLE_REQUIRED",
        )
    overlap = title_bigrams(title) & {
        alias[index : index + 2] for index in range(len(alias) - 1)
    }
    if overlap:
        raise AppError(
            422,
            f"别名不能使用原文标题中的连续两个字「{next(iter(overlap))}」",
            "ALIAS_REUSES_TITLE_TEXT",
        )


def strip_leading_alias(content: str) -> str:
    """去掉正文开头已有的【别名】行，保留后面的正文。"""
    return LEADING_ALIAS_PATTERN.sub("", content, count=1).strip()


def apply_alias_prefix(content: str, alias: str) -> str:
    """把正文开头统一成【alias】；alias 为空时移除旧别名。"""
    if not content.strip():
        return content
    body = strip_leading_alias(content)
    if not body:
        return f"【{alias}】" if alias else ""
    return f"【{alias}】\n{body}" if alias else body
