"""分镜提示词的写回契约：图片页码必须等于展示页码。"""

from __future__ import annotations

import re

from ..errors import AppError

PAGE_SECTION_PATTERN = re.compile(r"【页码】([^\n]*)")
PAGE_NUMBER_PATTERN = re.compile(r"第\s*(\d+)\s*页")


def prompt_page_numbers(image_prompt: str) -> set[int] | None:
    """读取【页码】分块里的页码；没有该分块时返回 None（兼容旧数据）。"""
    section = PAGE_SECTION_PATTERN.search(image_prompt or "")
    if section is None:
        return None
    return {
        int(number)
        for number in PAGE_NUMBER_PATTERN.findall(section.group(1))
    }


def validate_prompt_page_number(image_prompt: str, expected: int) -> None:
    """有【页码】分块时，其中的页码必须全部等于展示页码。"""
    numbers = prompt_page_numbers(image_prompt)
    if numbers is None:
        return
    if numbers != {expected}:
        found = "、".join(str(number) for number in sorted(numbers)) or "无数字"
        raise AppError(
            422,
            f"提示词页码错误：应写第{expected}页，实际为 {found}",
            "PROMPT_PAGE_MISMATCH",
        )
