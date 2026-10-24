#!/usr/bin/env python3
"""故事级完整性审计：章节覆盖、页码、提示词、角色引用与别名前缀。

用法：
  python .claude/skills/delivery-check/audit.py
  python .claude/skills/delivery-check/audit.py --story-id 3
  python .claude/skills/delivery-check/audit.py --api http://127.0.0.1:8123

退出码：0 = 通过；1 = 发现问题。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote

DEFAULT_API = "http://127.0.0.1:8123"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_UPLOAD_DIR = PROJECT_ROOT / "backend" / "uploads"
PAGE_SECTION = re.compile(r"【页码】([^\n]*)")
PAGE_NUMBER = re.compile(r"第\s*(\d+)\s*页")


def get(api: str, path: str):
    with urllib.request.urlopen(f"{api}{path}") as response:
        return json.loads(response.read().decode("utf-8"))


def image_file_exists(upload_dir: Path, url: str | None) -> bool:
    """把 /uploads/... 访问地址还原成上传目录下的本地文件。"""
    if not url:
        return True
    if not url.startswith("/uploads/"):
        return False
    relative = unquote(url[len("/uploads/") :])
    target = (upload_dir / relative).resolve()
    try:
        target.relative_to(upload_dir.resolve())
    except ValueError:
        return False
    return target.is_file()


def check_image(
    upload_dir: Path,
    url: str | None,
    label: str,
    add,
) -> None:
    if not url:
        return
    if not image_file_exists(upload_dir, url):
        add(f"{label} 的图片文件不存在：{url}")


def prompt_page_numbers(prompt: str) -> set[int] | None:
    section = PAGE_SECTION.search(prompt or "")
    if section is None:
        return None
    return {
        int(number)
        for number in PAGE_NUMBER.findall(section.group(1))
    }


def audit_story(
    api: str, story: dict, upload_dir: Path
) -> tuple[list[str], list[str]]:
    story_id = story["id"]
    issues: list[str] = []
    warnings: list[str] = []

    def add(message: str) -> None:
        issues.append(f"[故事 {story_id}] {message}")

    def warn(message: str) -> None:
        warnings.append(f"[故事 {story_id}] {message}")

    # 故事封面与角色资产图属于参考资源；缺失提示但不阻断发布检查。
    check_image(
        upload_dir, story.get("cover_url"), "故事封面", warn
    )

    breakdown = get(api, f"/api/stories/{story_id}/breakdown")
    if not breakdown:
        return issues, warnings

    mapping = breakdown.get("mapping") or []
    chapters = breakdown.get("chapters") or []
    pages = breakdown.get("pages") or []
    character_cards = breakdown.get("characters") or []
    characters = {card.get("name") for card in character_cards}
    for card in character_cards:
        check_image(
            upload_dir,
            card.get("asset_url"),
            f"角色「{card.get('name')}」资产图",
            warn,
        )
    mapping_by_number = {
        item.get("page_number"): item for item in mapping
    }
    chapter_by_number = {
        chapter.get("chapter_number"): chapter for chapter in chapters
    }
    active_mapping = [
        item.get("page_number")
        for item in mapping
        if not item.get("excluded")
    ]

    allocated: list[int] = []
    for index, chapter in enumerate(chapters, start=1):
        number = chapter.get("chapter_number")
        title = chapter.get("title") or ""
        chapter_mappings = chapter.get("mapping_page_numbers") or []
        if number != index:
            add(f"第 {index} 个章节的 chapter_number 应为 {index}，实际 {number}")
        if not title.strip():
            add(f"第 {number} 章标题为空")
        if len(chapter_mappings) > 16:
            add(f"第 {number} 章正文 {len(chapter_mappings)} 页，超过 16 页")
        if len(chapter_mappings) + 2 > 18:
            add(f"第 {number} 章总图超过 18 张")
        for mapping_number in chapter_mappings:
            if mapping_number not in mapping_by_number:
                add(
                    f"第 {number} 章引用了不存在的对照第 {mapping_number} 段"
                )
            elif mapping_by_number[mapping_number].get("excluded"):
                add(
                    f"第 {number} 章使用了已弃用的对照第 {mapping_number} 段"
                )
        allocated.extend(chapter_mappings)

        for kind, label in (("cover", "封面"), ("guide", "引导卡")):
            asset = chapter.get(kind) or {}
            prompt = asset.get("image_prompt") or ""
            if prompt and "【页码】" in prompt:
                add(f"第 {number} 章{label}提示词不应出现【页码】")
            check_image(
                upload_dir,
                asset.get("image_url"),
                f"第 {number} 章{label}图",
                add,
            )

    if chapters and allocated != active_mapping:
        add("章节未按对照表顺序覆盖全部未弃用段（不重不漏）")

    for page in pages:
        page_number = page.get("page_number")
        check_image(
            upload_dir,
            page.get("image_url"),
            f"全局第 {page_number} 页成品图",
            add,
        )
        chapter_number = page.get("chapter_number")
        chapter_page_number = page.get("chapter_page_number")
        display_number = page.get("display_page_number")
        expected_display = (
            chapter_page_number
            if chapter_page_number is not None
            else page_number
        )
        mapping_number = page.get("mapping_page_number")

        if display_number != expected_display:
            add(
                f"全局第 {page_number} 页 display_page_number 应为 "
                f"{expected_display}，实际 {display_number}"
            )
        # 旧版一次性流程可能没有 mapping；启用章节后则必须有关联来源。
        if mapping_number is None:
            if chapters:
                add(f"全局第 {page_number} 页缺少来源对照段")
        elif mapping_number not in mapping_by_number:
            add(
                f"全局第 {page_number} 页引用了不存在的对照第 "
                f"{mapping_number} 段"
            )
        if chapter_number is not None or chapter_page_number is not None:
            if chapter_number is None or chapter_page_number is None:
                add(
                    f"全局第 {page_number} 页的章节号和章内页码必须同时存在"
                )
            else:
                chapter = chapter_by_number.get(chapter_number)
                if chapter is None:
                    add(
                        f"全局第 {page_number} 页属于不存在的第 "
                        f"{chapter_number} 章"
                    )
                else:
                    chapter_mappings = (
                        chapter.get("mapping_page_numbers") or []
                    )
                    if not (
                        1 <= chapter_page_number <= len(chapter_mappings)
                    ):
                        add(
                            f"第 {chapter_number} 章没有第 "
                            f"{chapter_page_number} 页"
                        )
                    else:
                        expected_source = chapter_mappings[
                            chapter_page_number - 1
                        ]
                        if mapping_number != expected_source:
                            add(
                                f"第 {chapter_number} 章第 "
                                f"{chapter_page_number} 页应来源对照第 "
                                f"{expected_source} 段，实际 {mapping_number}"
                            )
                        offset = sum(
                            len(item.get("mapping_page_numbers") or [])
                            for item in chapters
                            if item.get("chapter_number", 0)
                            < chapter_number
                        )
                        if page_number != offset + chapter_page_number:
                            add(
                                f"第 {chapter_number} 章第 "
                                f"{chapter_page_number} 页的全局页码应为 "
                                f"{offset + chapter_page_number}，实际 "
                                f"{page_number}"
                            )

        prompt = page.get("image_prompt") or ""
        prompt_numbers = prompt_page_numbers(prompt)
        if prompt_numbers is None:
            add(f"全局第 {page_number} 页提示词缺少【页码】分块")
        elif prompt_numbers != {expected_display}:
            add(
                f"全局第 {page_number} 页提示词页码应为第 "
                f"{expected_display} 页，实际 {sorted(prompt_numbers)}"
            )

        for name in page.get("characters") or []:
            if name not in characters:
                add(
                    f"全局第 {page_number} 页引用了不存在的角色「{name}」"
                )

    alias = (story.get("zhihu_alias") or "").strip()
    aliases = story.get("zhihu_aliases") or []
    if alias:
        if alias not in aliases:
            add(f"最终别名「{alias}」不在候选别名列表中")
        for chapter in chapters:
            number = chapter.get("chapter_number")
            config = get(
                api,
                f"/api/stories/{story_id}/post-config?chapter={number}",
            )
            content = (config or {}).get("content") or ""
            if content and not content.startswith(f"【{alias}】"):
                add(
                    f"第 {number} 章发文正文开头不是【{alias}】"
                )

    return issues, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="故事完整性审计")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--story-id", type=int)
    parser.add_argument(
        "--upload-dir",
        type=Path,
        default=DEFAULT_UPLOAD_DIR,
        help="上传目录，默认 backend/uploads",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    stories = get(args.api, "/api/stories")
    if args.story_id is not None:
        stories = [
            story for story in stories if story["id"] == args.story_id
        ]
        if not stories:
            print(f"故事 {args.story_id} 不存在")
            return 1

    all_issues: list[str] = []
    all_warnings: list[str] = []
    for story in stories:
        issues, warnings = audit_story(
            args.api, story, args.upload_dir
        )
        status = "通过" if not issues else f"{len(issues)} 个问题"
        if warnings and not issues:
            status += f"（{len(warnings)} 条警告）"
        print(f"故事 {story['id']}《{story.get('name') or '未命名'}》：{status}")
        all_issues.extend(issues)
        all_warnings.extend(warnings)

    if all_warnings:
        print("\n警告（不阻断发布检查）：")
        for warning in all_warnings:
            print(f"  - {warning}")

    if all_issues:
        print("\n问题：")
        for issue in all_issues:
            print(f"  - {issue}")
        print("\n❌ 未通过：先修数据或代码，再交付。")
        return 1

    print("\n✅ 通过：章节、页码、提示词、角色引用、别名前缀与发布图片一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
