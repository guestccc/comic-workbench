#!/usr/bin/env python3
"""分镜头脚本自检：检查脚本页码、来源对照段、章节与旁白字数。

三个页码概念：
- mapping.page_number：对照段号，按优化文顺序，允许跳号；
- pages.page_number：全局脚本页码，接口与图片文件使用的稳定编号；
- pages.chapter_page_number：章内页码，图片里显示的「第X页」。

章节模式下每章正文最多 16 页（1 封面 + 16 正文 + 1 引导卡 = 18 张）。
封面 / 引导卡不在 pages 中，不参与本检查。

用法：
  python3 script_check.py --story-id 3
  python3 script_check.py --story-id 3 --chapter 2
  python3 script_check.py --story-id 3 --mapping-pages 1,2,3,5
  python3 script_check.py --input script.json --chapter 2

字数规则（按用户约定）：
- 主旁白 narration_main < 15 个汉字
- 副旁白 narration_sub  < 50 个汉字，最多 2 行
标点和空白不计入字数。

退出码：0 = 通过；1 = 发现问题。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

DEFAULT_API = "http://127.0.0.1:8123"
IGNORED = re.compile(r'[\s，。！？；：、「」『』“”‘’（）()…—·,.!?;:"\'-]')
MAX_CHAPTER_CONTENT_PAGES = 16
MAX_SUB_CHARS = 50
MAX_SUB_LINES = 2
REQUIRED_FIELDS = (
    "story_content",
    "character_review",
    "scene",
    "action_state",
    "change_note",
    "narration_main",
    "narration_sub",
    "image_prompt",
)
IMAGE_SECTIONS = (
    "【画风】",
    "【画面】",
    "【角色一致性】",
    "【画面形式】",
    "【文字区】",
    "【页码】",
    "【负面提示词】",
)
PAGE_ROLES = {
    "钩子封面",
    "铺垫",
    "冲突",
    "反转",
    "爆点",
    "情绪高潮",
    "收尾",
}


def count_chars(text: str) -> int:
    return len(IGNORED.sub("", text or ""))


def page_label(page: dict) -> str:
    chapter_number = page.get("chapter_number")
    local_number = page.get("chapter_page_number")
    if chapter_number is not None and local_number is not None:
        return f"第{chapter_number}章第{local_number}页"
    return f"全局第{page.get('page_number')}页"


# 旁白里禁止用第三人称代词；排除「其他」「吉他」这类非代词。
PRONOUN = re.compile(r"(?<!其)(?<!吉)[他她]")
TEXT_ZONE = re.compile(r"【文字区】(.*?)(?=\n【页码】|$)", re.S)


def extract_text_zone(prompt: str) -> str:
    match = TEXT_ZONE.search(prompt or "")
    return match.group(1) if match else ""


def load_breakdown(args: argparse.Namespace) -> dict:
    if args.input:
        return json.loads(Path(args.input).read_text(encoding="utf-8"))
    url = f"{args.api}/api/stories/{args.story_id}/breakdown"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data:
        raise SystemExit(f"{url} 返回空，故事还没有拆解结果")
    return data


def parse_numbers(
    value: str, option: str, parser: argparse.ArgumentParser
) -> list[int]:
    try:
        return sorted(
            {int(part) for part in value.split(",") if part.strip()}
        )
    except ValueError:
        parser.error(f"{option} 必须是逗号分隔的页码，例如 1,2,3")


def chapter_offset(chapters: list[dict], chapter_number: int) -> int:
    return sum(
        len(chapter.get("mapping_page_numbers") or [])
        for chapter in chapters
        if chapter.get("chapter_number", 0) < chapter_number
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="分镜头脚本自检")
    parser.add_argument("--story-id", type=int)
    parser.add_argument("--input", help="本地 breakdown JSON 文件")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument(
        "--chapter",
        type=int,
        help="只检查某一章；要求该章正文页完整生成",
    )
    parser.add_argument(
        "--mapping-pages",
        help="只检查这些对照段生成的脚本页，逗号分隔，例如 1,2,3,5",
    )
    parser.add_argument(
        "--pages",
        help="只检查这些全局脚本页码（旧参数），逗号分隔，例如 1,2,3",
    )
    args = parser.parse_args()

    if not args.story_id and not args.input:
        parser.error("需要 --story-id 或 --input")
    if args.pages and args.mapping_pages:
        parser.error("--pages 与 --mapping-pages 不能同时使用")
    if args.chapter is not None and (args.pages or args.mapping_pages):
        parser.error("--chapter 不能与 --pages / --mapping-pages 同时使用")
    if args.chapter is not None and args.chapter < 1:
        parser.error("--chapter 必须是从 1 开始的章节号")

    breakdown = load_breakdown(args)
    mapping = breakdown.get("mapping") or []
    chapters = breakdown.get("chapters") or []
    pages = sorted(
        breakdown.get("pages") or [], key=lambda page: page.get("page_number", 0)
    )
    mapping_numbers = [item.get("page_number") for item in mapping]
    page_numbers = [page.get("page_number") for page in pages]
    character_names = {
        card.get("name")
        for card in (breakdown.get("characters") or [])
        if card.get("name")
    }

    issues: list[str] = []
    if not mapping:
        issues.append("mapping 为空：先执行「分镜对照」")
    elif mapping_numbers != list(range(1, len(mapping) + 1)):
        issues.append(f"mapping 页码不连续：{mapping_numbers}")

    if not pages:
        issues.append("pages 为空：还没有分镜脚本")
    if page_numbers != list(range(1, len(pages) + 1)):
        issues.append(f"全局脚本页码必须从 1 连续、无空号：{page_numbers}")

    # ---------- 章节结构检查 ----------
    chapter_by_number: dict[int, dict] = {}
    for index, chapter in enumerate(chapters, start=1):
        number = chapter.get("chapter_number")
        if number != index:
            issues.append(
                f"章节号必须从 1 连续编号：第 {index} 个章节写的是 {number}"
            )
        if number is not None:
            chapter_by_number[number] = chapter
        mappings = chapter.get("mapping_page_numbers") or []
        if not mappings:
            issues.append(f"第 {number} 章没有分配对照段")
        if len(mappings) > MAX_CHAPTER_CONTENT_PAGES:
            issues.append(
                f"第 {number} 章正文 {len(mappings)} 页，"
                f"超过 {MAX_CHAPTER_CONTENT_PAGES} 页上限（总图会超过 18 张）"
            )

    excluded = {
        item.get("page_number")
        for item in mapping
        if item.get("excluded")
    }
    active_mapping = [
        number for number in mapping_numbers if number not in excluded
    ]
    if chapters:
        ordered: list[int] = []
        for chapter in sorted(
            chapters, key=lambda item: item.get("chapter_number", 0)
        ):
            number = chapter.get("chapter_number")
            for mapping_number in chapter.get("mapping_page_numbers") or []:
                if mapping_number in excluded:
                    issues.append(
                        f"第 {number} 章使用了已弃用的对照第 {mapping_number} 段"
                    )
                if mapping_number in ordered:
                    issues.append(
                        f"对照第 {mapping_number} 段被多个章节重复使用"
                    )
                ordered.append(mapping_number)
        if ordered != active_mapping:
            issues.append(
                "章节没有按对照表顺序覆盖全部未弃用段："
                f"章节 {ordered}，应有 {active_mapping}"
            )

    # 页面上的章节字段必须与章节规划一致
    for page in pages:
        script_number = page.get("page_number")
        chapter_number = page.get("chapter_number")
        local_number = page.get("chapter_page_number")
        if chapter_number is None and local_number is None:
            if chapters:
                issues.append(
                    f"章节模式下全局第{script_number}页缺少 "
                    "chapter_number / chapter_page_number"
                )
            continue
        if chapter_number is None or local_number is None:
            issues.append(
                f"全局第{script_number}页的 chapter_number / "
                "chapter_page_number 必须同时存在"
            )
            continue
        chapter = chapter_by_number.get(chapter_number)
        if chapter is None:
            issues.append(
                f"全局第{script_number}页属于不存在的第 {chapter_number} 章"
            )
            continue
        mappings = chapter.get("mapping_page_numbers") or []
        if not (1 <= local_number <= len(mappings)):
            issues.append(
                f"全局第{script_number}页的章内页码 {local_number} 超出范围"
            )
            continue
        expected_source = mappings[local_number - 1]
        if page.get("mapping_page_number") != expected_source:
            issues.append(
                f"第{chapter_number}章第{local_number}页应对应对照第"
                f"{expected_source}段，实际是对照第"
                f"{page.get('mapping_page_number')}段"
            )
        expected_global = chapter_offset(chapters, chapter_number) + local_number
        if script_number != expected_global:
            issues.append(
                f"第{chapter_number}章第{local_number}页的全局页码应为"
                f" {expected_global}，实际是 {script_number}"
            )

    # ---------- 选择本次检查范围 ----------
    selected_mapping: list[int] = []
    selected_script: list[int] = []
    selected_chapter: dict | None = None
    if args.chapter is not None:
        selected_chapter = chapter_by_number.get(args.chapter)
        if selected_chapter is None:
            issues.append(f"第 {args.chapter} 章不存在")
            selected_pages: list[dict] = []
        else:
            selected_pages = [
                page
                for page in pages
                if page.get("chapter_number") == args.chapter
            ]
            mappings = selected_chapter.get("mapping_page_numbers") or []
            expected_locals = list(range(1, len(mappings) + 1))
            found_locals = sorted(
                page.get("chapter_page_number")
                for page in selected_pages
                if page.get("chapter_page_number") is not None
            )
            missing_locals = [
                number
                for number in expected_locals
                if number not in found_locals
            ]
            if missing_locals:
                issues.append(
                    f"第 {args.chapter} 章正文未生成完整，缺少章内页："
                    f"{missing_locals}"
                )
    elif args.mapping_pages:
        selected_mapping = parse_numbers(
            args.mapping_pages, "--mapping-pages", parser
        )
        missing_sources = [
            number for number in selected_mapping if number not in mapping_numbers
        ]
        if missing_sources:
            issues.append(f"选中的对照段在 mapping 中不存在：{missing_sources}")
        selected_set = set(selected_mapping)
        selected_pages = [
            page
            for page in pages
            if page.get("mapping_page_number") in selected_set
        ]
        found_sources = [
            page.get("mapping_page_number") for page in selected_pages
        ]
        missing_pages = [
            number for number in selected_mapping if number not in found_sources
        ]
        if missing_pages:
            issues.append(
                f"选中的对照第 {missing_pages} 段没有对应脚本页："
                "先清空分镜脚本再重新生成"
            )
        expected_order = [
            number for number in selected_mapping if number in found_sources
        ]
        if found_sources != expected_order:
            issues.append(
                f"选中对照段与脚本页顺序不一致："
                f"对照 {found_sources}，预期 {expected_order}"
            )
    elif args.pages:
        selected_script = parse_numbers(args.pages, "--pages", parser)
        selected_set = set(selected_script)
        selected_pages = [
            page for page in pages if page.get("page_number") in selected_set
        ]
        found_pages = [page.get("page_number") for page in selected_pages]
        missing_pages = [
            number for number in selected_script if number not in found_pages
        ]
        if missing_pages:
            issues.append(f"选中的脚本页码不存在：{missing_pages}")
    else:
        selected_pages = pages

    print(f"故事：{breakdown.get('story_id', args.story_id or '未知')}")
    print(f"mapping：{len(mapping)} 段；pages：{len(pages)} 页")
    if chapters:
        print(
            "章节："
            + "；".join(
                f"第{chapter.get('chapter_number')}章"
                f"《{chapter.get('title', '')}》"
                f"{len(chapter.get('mapping_page_numbers') or [])}页"
                for chapter in sorted(
                    chapters, key=lambda item: item.get("chapter_number", 0)
                )
            )
        )
    if selected_chapter is not None:
        mappings = selected_chapter.get("mapping_page_numbers") or []
        print(
            f"本次检查：第{args.chapter}章《"
            f"{selected_chapter.get('title', '')}》，"
            f"正文 {len(selected_pages)}/{len(mappings)} 页"
        )
    elif selected_mapping:
        pairs = "；".join(
            f"对照第{page.get('mapping_page_number')}段 → "
            f"脚本第{page.get('page_number')}页"
            for page in selected_pages
        )
        print(f"本次检查：{len(selected_mapping)} 段（{pairs}）")
        skipped = [
            number
            for number in mapping_numbers
            if number not in set(selected_mapping)
        ]
        skipped_text = f"（{skipped}）" if skipped else ""
        print(f"未选中对照段：{len(skipped)} 段{skipped_text}")
    elif selected_script:
        print(f"本次检查：脚本第 {selected_script} 页")
    else:
        print("本次检查：全部页")

    print(
        "对照段 | 全局页 | 章内页 | 主旁白 | 副旁白 | "
        "主旁白字数 | 副旁白字数"
    )
    for page in selected_pages:
        script_number = page.get("page_number")
        source_number = page.get("mapping_page_number")
        local_number = page.get("chapter_page_number")
        main = page.get("narration_main") or ""
        sub = page.get("narration_sub") or ""
        main_count = count_chars(main)
        sub_count = count_chars(sub)
        source_text = str(source_number) if source_number is not None else "-"
        local_text = str(local_number) if local_number is not None else "-"
        sub_display = sub.replace("\r\n", "\n").replace("\n", " / ")
        print(
            f"{source_text:>6} | {script_number:>6} | {local_text:>6} | "
            f"{main} | {sub_display} | {main_count} | {sub_count}"
        )
        if main_count >= 15:
            issues.append(
                f"全局第{script_number}页主旁白 {main_count} 字，要求 < 15"
            )
        if sub_count >= MAX_SUB_CHARS:
            issues.append(
                f"全局第{script_number}页副旁白 {sub_count} 字，"
                f"要求 < {MAX_SUB_CHARS}"
            )
        sub_lines = [
            line for line in sub.splitlines() if line.strip()
        ]
        if len(sub_lines) > MAX_SUB_LINES:
            issues.append(
                f"全局第{script_number}页副旁白有 {len(sub_lines)} 行，"
                f"最多 {MAX_SUB_LINES} 行"
            )
        empty = [
            field
            for field in REQUIRED_FIELDS
            if not str(page.get(field) or "").strip()
        ]
        if empty:
            issues.append(
                f"全局第{script_number}页字段为空：{', '.join(empty)}"
            )

        label = page_label(page)
        role = (page.get("page_role") or "").strip()
        if not role:
            issues.append(f"{label} page_role 为空")
        elif role not in PAGE_ROLES:
            issues.append(f"{label} page_role「{role}」不在允许值中")
        if not (page.get("camera_angle") or "").strip():
            issues.append(f"{label} camera_angle 为空")

        highlight = (page.get("narration_highlight") or "").strip()
        if highlight and highlight not in main and highlight not in sub:
            issues.append(
                f"{label} narration_highlight 不是主/副旁白的连续片段"
            )

        unknown_characters = [
            name
            for name in (page.get("characters") or [])
            if name not in character_names
        ]
        if unknown_characters:
            issues.append(
                f"{label} 引用了角色卡中不存在的角色："
                f"{'、'.join(unknown_characters)}"
            )

        # 图片里显示的是章内页码；不能把全局页码或对照段号写进 image_prompt
        expected_page = (
            local_number if local_number is not None else script_number
        )
        image_prompt = page.get("image_prompt") or ""

        missing_sections = [
            section for section in IMAGE_SECTIONS if section not in image_prompt
        ]
        if missing_sections:
            issues.append(
                f"{label} image_prompt 缺少分块："
                f"{'、'.join(missing_sections)}"
            )

        # 旁白称谓：禁用第三人称代词，改用角色姓名或「我」
        for label, text in (("主旁白", main), ("副旁白", sub)):
            pronouns = sorted(set(PRONOUN.findall(text)))
            if pronouns:
                issues.append(
                    f"全局第{script_number}页{label}出现代词"
                    f"「{'、'.join(pronouns)}」；应改用「我」或角色姓名"
                )

        # 字段文字必须逐字出现在 image_prompt 的【文字区】
        text_zone = extract_text_zone(image_prompt)
        if text_zone:
            if main.strip() and main.strip() not in text_zone:
                issues.append(
                    f"全局第{script_number}页主旁白未逐字出现在【文字区】"
                )
            missing_sub_lines = [
                line for line in sub_lines if line not in text_zone
            ]
            if missing_sub_lines:
                issues.append(
                    f"全局第{script_number}页副旁白未逐字出现在【文字区】"
                    f"（{len(missing_sub_lines)} 行），例如："
                    f"{missing_sub_lines[0]}"
                )

        page_section = re.search(r"【页码】([^\n]*)", image_prompt)
        if not page_section:
            issues.append(
                f"全局第{script_number}页 image_prompt 缺少【页码】分块"
            )
        else:
            found_numbers = {
                int(number)
                for number in re.findall(
                    r"第\s*(\d+)\s*页", page_section.group(1)
                )
            }
            if found_numbers != {expected_page}:
                found_text = (
                    "、".join(str(number) for number in sorted(found_numbers))
                    if found_numbers
                    else "无数字"
                )
                issues.append(
                    f"全局第{script_number}页 image_prompt 页码错误："
                    f"应写第{expected_page}页（章内页码），实际为 {found_text}"
                )

    # 相邻页机位 + 景别不能完全相同；跨章节不比较
    for previous, current in zip(selected_pages, selected_pages[1:]):
        if previous.get("chapter_number") != current.get("chapter_number"):
            continue
        previous_combo = (
            previous.get("camera_angle"),
            previous.get("shot_type"),
        )
        current_combo = (
            current.get("camera_angle"),
            current.get("shot_type"),
        )
        if previous_combo == current_combo:
            issues.append(
                f"{page_label(previous)} 与 {page_label(current)} 的"
                f"机位+景别完全相同：{previous_combo[0]} / {previous_combo[1]}"
            )

    if issues:
        print("\n问题：")
        for issue in issues:
            print(f"  - {issue}")
        print("\n❌ 未通过：先修脚本，再写回。")
        return 1

    print(
        "\n✅ 通过：脚本页码与章节结构一致，"
        "来源对照段完整且不重复，旁白字数符合要求。"
    )
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
