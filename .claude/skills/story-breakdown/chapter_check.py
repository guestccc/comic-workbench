#!/usr/bin/env python3
"""章节规划自检：检查章节覆盖、每章图片上限与封面/引导卡文字。

规则（按用户约定）：
- 一章 = 1 封面 + 1..16 正文 + 1 引导卡，总图 <= 18；
- 章节按对照表顺序覆盖全部未弃用段，不重不漏；
- 封面主旁白 < 15 个汉字、副旁白 < 35 个汉字（标点不计）；
- 主旁白标红词必须内嵌在主旁白里。

用法：
  python3 chapter_check.py --story-id 3
  python3 chapter_check.py --input breakdown.json

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
MAX_CONTENT_PAGES = 16
MAX_TOTAL_IMAGES = 18


def count_chars(text: str) -> int:
    return len(IGNORED.sub("", text or ""))


def load_breakdown(args: argparse.Namespace) -> dict:
    if args.input:
        return json.loads(Path(args.input).read_text(encoding="utf-8"))
    url = f"{args.api}/api/stories/{args.story_id}/breakdown"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data:
        raise SystemExit(f"{url} 返回空，故事还没有拆解结果")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="章节规划自检")
    parser.add_argument("--story-id", type=int)
    parser.add_argument("--input", help="本地 breakdown JSON 文件")
    parser.add_argument("--api", default=DEFAULT_API)
    args = parser.parse_args()
    if not args.story_id and not args.input:
        parser.error("需要 --story-id 或 --input")

    breakdown = load_breakdown(args)
    mapping = breakdown.get("mapping") or []
    chapters = breakdown.get("chapters") or []
    mapping_numbers = [item.get("page_number") for item in mapping]
    excluded = {
        item.get("page_number") for item in mapping if item.get("excluded")
    }
    active = [number for number in mapping_numbers if number not in excluded]

    issues: list[str] = []
    if not mapping:
        issues.append("mapping 为空：先执行「分镜对照」")
    if not chapters:
        issues.append("chapters 为空：先执行「章节规划」")

    ordered: list[int] = []
    for index, chapter in enumerate(chapters, start=1):
        number = chapter.get("chapter_number")
        title = (chapter.get("title") or "").strip()
        mappings = chapter.get("mapping_page_numbers") or []
        if number != index:
            issues.append(
                f"章节号必须从 1 连续编号：第 {index} 个章节写的是 {number}"
            )
        if not title:
            issues.append(f"第 {number} 章标题为空")
        if not mappings:
            issues.append(f"第 {number} 章没有分配对照段")
        if len(mappings) > MAX_CONTENT_PAGES:
            issues.append(
                f"第 {number} 章正文 {len(mappings)} 页，超过 "
                f"{MAX_CONTENT_PAGES} 页上限"
            )
        total_images = len(mappings) + 2
        if total_images > MAX_TOTAL_IMAGES:
            issues.append(
                f"第 {number} 章总图 {total_images} 张，超过 "
                f"{MAX_TOTAL_IMAGES} 张"
            )

        for mapping_number in mappings:
            if mapping_number in excluded:
                issues.append(
                    f"第 {number} 章使用了已弃用的对照第 {mapping_number} 段"
                )
            if mapping_number not in mapping_numbers:
                issues.append(
                    f"第 {number} 章使用了不存在的对照第 {mapping_number} 段"
                )
            if mapping_number in ordered:
                issues.append(
                    f"对照第 {mapping_number} 段被多个章节重复使用"
                )
            ordered.append(mapping_number)

        cover = chapter.get("cover") or {}
        main = (cover.get("narration_main") or "").strip()
        sub = (cover.get("narration_sub") or "").strip()
        highlight = (cover.get("narration_highlight") or "").strip()
        if not (cover.get("label") or "").strip():
            issues.append(f"第 {number} 章封面顶部小字为空")
        if not main:
            issues.append(f"第 {number} 章封面主旁白为空")
        if not sub:
            issues.append(f"第 {number} 章封面副旁白为空")
        main_count = count_chars(main)
        sub_count = count_chars(sub)
        if main_count >= 15:
            issues.append(
                f"第 {number} 章封面主旁白 {main_count} 字，要求 < 15"
            )
        if sub_count >= 35:
            issues.append(
                f"第 {number} 章封面副旁白 {sub_count} 字，要求 < 35"
            )
        if not highlight:
            issues.append(f"第 {number} 章封面没有标红词")
        elif highlight not in main and highlight not in sub:
            issues.append(
                f"第 {number} 章封面标红词「{highlight}」不在主旁白或副旁白里"
            )

        guide = chapter.get("guide") or {}
        if not (guide.get("text") or "").strip():
            issues.append(f"第 {number} 章引导卡主文案为空")
        if not (guide.get("sub_text") or "").strip():
            issues.append(f"第 {number} 章引导卡副文案为空")

    if chapters and ordered != active:
        issues.append(
            "章节没有按对照表顺序覆盖全部未弃用段："
            f"章节 {ordered}，应有 {active}"
        )

    print(f"故事：{breakdown.get('story_id', args.story_id or '未知')}")
    print(f"mapping：{len(mapping)} 段；弃用：{len(excluded)} 段；章节：{len(chapters)} 章")
    for chapter in chapters:
        mappings = chapter.get("mapping_page_numbers") or []
        cover = chapter.get("cover") or {}
        print(
            f"第{chapter.get('chapter_number')}章"
            f"《{chapter.get('title', '')}》"
            f" | 对照 {mappings[0] if mappings else '-'}–"
            f"{mappings[-1] if mappings else '-'}"
            f" | 正文 {len(mappings)}"
            f" | 总图 {len(mappings) + 2}"
            f" | 主旁白 {count_chars(cover.get('narration_main') or '')} 字"
            f" | 副旁白 {count_chars(cover.get('narration_sub') or '')} 字"
        )

    if issues:
        print("\n问题：")
        for issue in issues:
            print(f"  - {issue}")
        print("\n❌ 未通过：先修章节规划，再写回。")
        return 1

    print("\n✅ 通过：章节顺序与覆盖正确，每章不超过 18 张，封面文字符合要求。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
