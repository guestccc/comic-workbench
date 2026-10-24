#!/usr/bin/env python3
"""分镜对照表自检：mapping 是否按原文顺序完整覆盖优化文。

用法：
  python3 mapping_check.py --story-id 3
  python3 mapping_check.py --input mapping.json

去掉标点和空白后，把 mapping 的 source_text 按页码顺序拼接，
应当与 optimized_content 完全一致。不一致时打印第一个差异位置。

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
IGNORED = re.compile(r"[\s，。！？；：、「」『』“”‘’（）()…—·,.!?;:\"'-]")


def normalize(text: str) -> str:
    return IGNORED.sub("", text or "")


def load_breakdown(args: argparse.Namespace) -> dict:
    if args.input:
        return json.loads(Path(args.input).read_text(encoding="utf-8"))
    url = f"{args.api}/api/stories/{args.story_id}/breakdown"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data:
        raise SystemExit(f"{url} 返回空，故事还没有拆解结果")
    return data


def context(text: str, index: int, radius: int = 24) -> str:
    start = max(0, index - radius)
    end = min(len(text), index + radius)
    return text[start:end]


def main() -> int:
    parser = argparse.ArgumentParser(description="分镜对照表自检")
    parser.add_argument("--story-id", type=int)
    parser.add_argument("--input", help="本地 breakdown JSON 文件")
    parser.add_argument("--api", default=DEFAULT_API)
    args = parser.parse_args()

    if not args.story_id and not args.input:
        parser.error("需要 --story-id 或 --input")

    breakdown = load_breakdown(args)
    optimized = normalize(breakdown.get("optimized_content", ""))
    mapping = sorted(
        breakdown.get("mapping") or [], key=lambda item: item.get("page_number", 0)
    )

    issues: list[str] = []
    numbers = [item.get("page_number") for item in mapping]
    if numbers != list(range(1, len(mapping) + 1)):
        issues.append(f"页码不连续：{numbers}")

    for item in mapping:
        source = normalize(item.get("source_text", ""))
        if source.isdigit():
            issues.append(
                f"第{item.get('page_number')}页 source_text 只有章节编号，"
                "应并入相邻页，不要单独成页"
            )

    mapped = "".join(normalize(item.get("source_text", "")) for item in mapping)

    print(f"故事：{breakdown.get('story_id', args.story_id or '未知')}")
    print(f"对照表页数：{len(mapping)}；优化文字符数：{len(optimized)}")
    print(f"mapping 拼接字符数：{len(mapped)}")

    if not mapping:
        issues.append("mapping 为空")
    elif mapped == optimized:
        print("✅ mapping 与优化文逐字一致（忽略标点和空白）")
    else:
        index = 0
        while (
            index < len(mapped)
            and index < len(optimized)
            and mapped[index] == optimized[index]
        ):
            index += 1
        issues.append(
            "mapping 与优化文不一致："
            f"第 {index + 1} 个字开始不同\n"
            f"  mapping：{context(mapped, index)}\n"
            f"  优化文：{context(optimized, index)}"
        )

    if issues:
        print("\n问题：")
        for issue in issues:
            print(f"  - {issue}")
        print("\n❌ 未通过：先修 mapping，再进入分镜头脚本。")
        return 1

    print("\n✅ 通过：对照表按原文顺序完整覆盖优化文。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
