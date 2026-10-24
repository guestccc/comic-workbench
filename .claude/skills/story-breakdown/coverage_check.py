#!/usr/bin/env python3
"""分镜覆盖自检：检查优化文是否有信息漏页、分镜页是否重复。

用法：
  python3 coverage_check.py --story-id 3
  python3 coverage_check.py --input pages.json

输入可以是工作台接口返回的 breakdown，也可以是包含
optimized_content 与 pages 的 JSON；pages 里每页至少要有
story_content / narration_main / narration_sub / dialogues 字段。

检查项：
1. 优化文逐句检查：至少有一段 8 字连续文本出现在分镜里，否则列为疑似漏页；
2. 分镜页两两比较，字符二元组重叠度过高时列为疑似重复页；
3. 按优化文顺序检查每句首次出现的页码，发现大段倒序/跳跃时列为疑似页序错误；
4. 页码是否连续、必填字段是否为空。

退出码：0 = 通过；1 = 发现疑似问题。
注意：第 1 条是字面匹配，改写较多时会有误报，需要人工复核。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from itertools import combinations
from pathlib import Path

DEFAULT_API = "http://127.0.0.1:8123"
REQUIRED_FIELDS = (
    "story_content",
    "narration_main",
    "narration_sub",
    "image_prompt",
)
# 只检查真正承载剧情的字段；场景/动作/人物回顾属于画面描述，
# 同一句话可能只是擦边出现，混进来会掩盖真正的漏页。
PAGE_TEXT_FIELDS = (
    "story_content",
    "narration_main",
    "narration_sub",
)


def load_breakdown(args: argparse.Namespace) -> dict:
    if args.input:
        return json.loads(Path(args.input).read_text(encoding="utf-8"))

    url = f"{args.api}/api/stories/{args.story_id}/breakdown"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data:
        raise SystemExit(f"{url} 返回空，故事还没有拆解结果")
    return data


def page_text(page: dict) -> str:
    parts = [str(page.get(field) or "") for field in PAGE_TEXT_FIELDS]
    parts.extend(str(line) for line in page.get("dialogues") or [])
    return "".join(parts)


def split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"[\n。！？]+", text)
        if sentence.strip()
    ]


def has_window(sentence: str, blob: str, window: int) -> bool:
    return any(
        sentence[index : index + window] in blob
        for index in range(0, max(0, len(sentence) - window) + 1)
    )


def bigrams(text: str) -> set[str]:
    return {text[index : index + 2] for index in range(max(0, len(text) - 1))}


def containment(left: str, right: str) -> float:
    """重叠度 = 交集 / 较小集合；用于发现「一页是另一页的翻版」。"""
    left_set, right_set = bigrams(left), bigrams(right)
    smaller = min(len(left_set), len(right_set))
    return len(left_set & right_set) / smaller if smaller else 0.0


def page_beat_text(page: dict) -> str:
    parts = [
        str(page.get("story_content") or ""),
        str(page.get("narration_main") or ""),
        str(page.get("narration_sub") or ""),
    ]
    parts.extend(str(line) for line in page.get("dialogues") or [])
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="分镜覆盖自检")
    parser.add_argument("--story-id", type=int, help="工作台故事 ID")
    parser.add_argument("--input", help="本地 breakdown JSON 文件")
    parser.add_argument("--api", default=DEFAULT_API, help="后端地址")
    parser.add_argument("--window", type=int, default=8, help="漏页判断的字数窗口")
    parser.add_argument(
        "--duplicate-threshold",
        type=float,
        default=0.7,
        help="重复页判断的重叠度阈值（0-1）",
    )
    args = parser.parse_args()

    if not args.story_id and not args.input:
        parser.error("需要 --story-id 或 --input")

    breakdown = load_breakdown(args)
    content = str(breakdown.get("optimized_content") or "")
    pages = breakdown.get("pages") or []
    if not content.strip() or not pages:
        print("优化文或分镜页为空，无法检查")
        return 1

    issues: list[str] = []

    # 1. 页码与必填字段
    numbers = [int(page.get("page_number") or 0) for page in pages]
    if numbers != list(range(1, len(pages) + 1)):
        issues.append(f"页码不连续：{numbers}")
    for page in pages:
        empty = [
            field
            for field in REQUIRED_FIELDS
            if not str(page.get(field) or "").strip()
        ]
        if empty:
            issues.append(f"第{page.get('page_number')}页字段为空：{', '.join(empty)}")

    # 2. 优化文逐句覆盖
    blob = "".join(page_text(page) for page in pages)
    sentences = split_sentences(content)
    uncovered = [
        sentence
        for sentence in sentences
        if len(sentence) >= args.window
        and not has_window(sentence, blob, args.window)
    ]

    # 3. 重复页
    duplicates = []
    for left, right in combinations(pages, 2):
        score = containment(page_beat_text(left), page_beat_text(right))
        if score >= args.duplicate_threshold:
            duplicates.append(
                (left.get("page_number"), right.get("page_number"), round(score, 2))
            )

    # 4. 阅读顺序：优化文逐句第一次出现的页码，应当基本随页码前进
    first_pages: list[tuple[str, int]] = []
    for sentence in sentences:
        if len(sentence) < args.window:
            continue
        for page in pages:
            if has_window(sentence, page_text(page), args.window):
                first_pages.append((sentence, int(page.get("page_number") or 0)))
                break

    backward_jumps = []
    for (previous_text, previous_page), (text, page_number) in zip(
        first_pages, first_pages[1:]
    ):
        if page_number < previous_page - 1:
            backward_jumps.append((previous_page, page_number, text))

    print(f"故事：{breakdown.get('story_id', args.story_id or '未知')}")
    print(f"分镜页数：{len(pages)}；优化文句数：{len(sentences)}")
    print(f"疑似漏页句子：{len(uncovered)}")
    for sentence in uncovered:
        print(f"  - {sentence}（可能是改写，请复核）")

    print(f"疑似重复页对：{len(duplicates)}")
    for left, right, score in duplicates:
        print(f"  - 第{left}页 ↔ 第{right}页，相似度 {score}")

    print(f"疑似倒序跳跃：{len(backward_jumps)}")
    for previous_page, page_number, text in backward_jumps:
        print(f"  - 第{previous_page}页 → 第{page_number}页：{text}")

    if issues:
        print("结构问题：")
        for issue in issues:
            print(f"  - {issue}")

    if uncovered or duplicates or backward_jumps or issues:
        print(
            "\n❌ 未通过：先补页 / 删重复页 / 调整页序 / 补字段，再写回分镜。"
        )
        return 1

    print("\n✅ 通过：未发现漏页、重复页、倒序跳跃或字段缺失。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
