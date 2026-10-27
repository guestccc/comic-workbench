#!/usr/bin/env python3
"""分镜对照表自检：mapping 是否按原文顺序完整覆盖优化文。

用法：
  python3 mapping_check.py --story-id 3
  python3 mapping_check.py --input mapping.json

去掉标点和空白后，把 mapping 的 source_text 按页码顺序拼接，
应当与 optimized_content 完全一致。不一致时打印第一个差异位置。
另外输出视觉单元过载 / 过碎警告（不阻断），以及严格连续提示。

退出码：0 = 通过（可能带警告）；1 = 发现问题。
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

# 视觉单元过载警告阈值：只提示，不阻断
# 与 backend/app/services/mapping_reviews.py 的风险分级保持一致
CJK_WARN = 60
CJK_STRONG_WARN = 90
MAX_QUOTE_PAIRS = 2
MAX_SENTENCE_ENDS = 5
TRANSITION_MARKERS = (
    "后来",
    "第二天",
    "当晚",
    "那晚",
    "与此同时",
    "几年后",
    "十年后",
    "十五年前",
    "上一世",
    "重生后",
    "回到",
    "那天",
    "次日",
    "从此",
    "不久后",
    "半个月后",
    "一个月后",
    "一年后",
)


def normalize(text: str) -> str:
    return IGNORED.sub("", text or "")


def cjk_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text or ""))


def quote_pair_count(text: str) -> int:
    """统计引号台词和【】消息气泡，两者都按气泡计算。"""
    text = text or ""
    quoted = len(re.findall(r"[「“][^」”]{1,300}[」”]", text))
    messages = len(re.findall(r"【[^】]{1,300}】", text))
    return quoted + messages


def sentence_end_count(text: str) -> int:
    return len(re.findall(r"[。！？!?]", text or ""))


def transition_markers(text: str) -> list[str]:
    return [marker for marker in TRANSITION_MARKERS if marker in (text or "")]


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
    raw_optimized = breakdown.get("optimized_content", "")
    optimized = normalize(raw_optimized)
    mapping = sorted(
        breakdown.get("mapping") or [], key=lambda item: item.get("page_number", 0)
    )

    issues: list[str] = []
    warnings: list[str] = []
    numbers = [item.get("page_number") for item in mapping]
    if numbers != list(range(1, len(mapping) + 1)):
        issues.append(f"页码不连续：{numbers}")

    for item in mapping:
        number = item.get("page_number")
        raw_source = item.get("source_text") or ""
        source = normalize(raw_source)
        if source.isdigit():
            issues.append(
                f"第{number}页 source_text 只有章节编号，"
                "应并入相邻页，不要单独成页"
            )

        page_warnings: list[str] = []
        high_risk = False

        cjk = cjk_count(raw_source)
        if cjk > CJK_STRONG_WARN:
            page_warnings.append(f"{cjk} 个汉字（>{CJK_STRONG_WARN}）")
            high_risk = True
        elif cjk > CJK_WARN:
            page_warnings.append(f"{cjk} 个汉字（>{CJK_WARN}）")

        quotes = quote_pair_count(raw_source)
        if quotes > MAX_QUOTE_PAIRS:
            page_warnings.append(
                f"{quotes} 组台词/消息（>{MAX_QUOTE_PAIRS}）"
            )
            high_risk = True

        ends = sentence_end_count(raw_source)
        if ends > MAX_SENTENCE_ENDS:
            page_warnings.append(
                f"{ends} 个句末标点（>{MAX_SENTENCE_ENDS}）"
            )

        markers = transition_markers(raw_source)
        if len(markers) >= 2:
            page_warnings.append(
                "多个时间/地点转换词"
                f"（{'、'.join(markers)}）"
            )
            high_risk = True

        if page_warnings:
            level = "高" if high_risk else "中"
            warnings.append(
                f"[{level}] 第{number}段：" + "；".join(page_warnings)
            )

    mapped = "".join(normalize(item.get("source_text", "")) for item in mapping)
    exact_mapped = "".join(item.get("source_text") or "" for item in mapping)
    if exact_mapped != raw_optimized and mapped == optimized:
        delta = len(raw_optimized) - len(exact_mapped)
        detail = f"少 {delta} 个字符" if delta > 0 else "字符数与优化文不同"
        warnings.append(
            "严格连续：mapping 拼接比优化文"
            f"{detail}（标点/换行）；归一化检查通过，"
            "但 source_text 不是逐字连续"
        )

    print(f"故事：{breakdown.get('story_id', args.story_id or '未知')}")
    print(
        f"对照表页数：{len(mapping)}；"
        f"优化文字符数：{len(raw_optimized)}（归一化 {len(optimized)}）"
    )
    print(f"mapping 拼接字符数：{len(mapped)}（严格 {len(exact_mapped)}）")

    if not mapping:
        issues.append("mapping 为空")
    elif mapped == optimized:
        print("✅ mapping 与优化文归一化后一致（忽略标点和空白）")
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
        if warnings:
            print("\n警告（不阻断，请人工判断）：")
            for warning in warnings:
                print(f"  - {warning}")
        print("\n❌ 未通过：先修 mapping，再进入分镜头脚本。")
        return 1

    if warnings:
        print("\n警告（不阻断，请人工判断）：")
        for warning in warnings:
            print(f"  - {warning}")

    if warnings:
        high_count = sum(
            1 for warning in warnings if warning.startswith("[高]")
        )
        print(
            "\n✅ 通过：对照表按原文顺序完整覆盖优化文。"
            f"（{len(warnings)} 条警告，其中高风险 {high_count} 条）"
        )
    else:
        print("\n✅ 通过：对照表按原文顺序完整覆盖优化文。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
