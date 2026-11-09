#!/usr/bin/env python3
"""章节封面硬检查：标题/副标题字数、标红、提示词分块与页码。

用法：
  python cover_check.py --story-id 4 --chapter 1
  python cover_check.py --input breakdown.json --chapter 1

退出码：0 = 通过（可带警告）；1 = 硬规则失败。
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
COVER_SECTIONS = (
    "【画风】",
    "【画面】",
    "【角色一致性】",
    "【画面形式】",
    "【文字区】",
    "【负面提示词】",
)
HOOK_WORDS = (
    "特写",
    "近景",
    "前景",
    "高对比",
    "强对比",
    "压暗",
    "红光",
    "冷光",
    "眼神",
    "表情",
    "道具",
    "按钮",
    "屏幕",
    "车票",
    "协议",
    "治疗单",
)
PREMISE_PATTERNS = (
    "重生回到",
    "在车站做",
    "三个月前",
    "上一章",
    "故事讲述",
)
IMPACT_MARKERS = (
    "漫画黑色震动短线",
    "震动短线",
    "放射集中冲击线",
    "放射状集中冲击线",
    "锯齿情绪漫符",
    "手绘涂鸦",
    "【冲击层】",
)
IMPACT_NEGATIVE_TERMS = (
    "冲击线铺满全图",
    "冲击线糊成脏线",
    "冲击线像贴图",
    "美式超级英雄粗线",
    "涂鸦遮挡脸或文字",
    "文字被线条压住",
    "线条穿过眼睛",
)
CHOREOGRAPHY_TERMS = (
    "冲击线起点",
    "从关键道具",
    "从动作",
    "从视线",
    "线的方向",
    "密度",
    "保护区",
    "围绕",
)


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
    parser = argparse.ArgumentParser(description="章节封面硬检查")
    parser.add_argument("--story-id", type=int)
    parser.add_argument("--input", help="本地 breakdown JSON 文件")
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--api", default=DEFAULT_API)
    args = parser.parse_args()

    if not args.story_id and not args.input:
        parser.error("需要 --story-id 或 --input")

    breakdown = load_breakdown(args)
    chapters = breakdown.get("chapters") or []
    chapter = next(
        (
            item
            for item in chapters
            if item.get("chapter_number") == args.chapter
        ),
        None,
    )
    if chapter is None:
        raise SystemExit(f"第 {args.chapter} 章不存在")

    cover = chapter.get("cover") or {}
    main = (cover.get("narration_main") or "").strip()
    sub = (cover.get("narration_sub") or "").strip()
    highlight = (cover.get("narration_highlight") or "").strip()
    label = (cover.get("label") or "").strip()
    prompt = (cover.get("image_prompt") or "").strip()

    issues: list[str] = []
    warnings: list[str] = []

    if not label:
        issues.append("封面 label 为空")
    if not main:
        issues.append("封面主旁白为空")
    if not sub:
        issues.append("封面副旁白为空")
    if not prompt:
        issues.append("封面 image_prompt 为空")

    main_count = count_chars(main)
    sub_count = count_chars(sub)
    if main and main_count > 12:
        issues.append(f"封面主旁白 {main_count} 字，要求 ≤12")
    if sub and sub_count >= 35:
        issues.append(f"封面副旁白 {sub_count} 字，要求 <35")

    if highlight and highlight not in main and highlight not in sub:
        issues.append("封面标红词不在主/副旁白中")
    if not highlight:
        warnings.append("封面没有标红词")

    if prompt:
        missing = [section for section in COVER_SECTIONS if section not in prompt]
        if missing:
            issues.append(f"封面 image_prompt 缺少分块：{'、'.join(missing)}")
        if "【页码】" in prompt or re.search(r"第\s*\d+\s*页", prompt):
            issues.append("封面 image_prompt 出现页码")
        style_content = (breakdown.get("art_style_content") or "").strip()
        if style_content and style_content not in prompt:
            warnings.append(
                "【画风】没有逐字使用故事画风原文（CV-08）；"
                "新封面应把 art_style_content 原文放在【画风】开头"
            )
        has_impact = any(marker in prompt for marker in IMPACT_MARKERS)
        positive_prompt = prompt.split("【负面提示词】")[0]
        # 冲击层最低力度（CV-13）：模板已固定写入，缺失说明是旧提示词或手写漏项
        if not re.search(r"至少\s*3\s*条", positive_prompt):
            warnings.append(
                "冲击层缺少最低力度：至少 3 条粗黑集中手绘射线（CV-13）"
            )
        if "手绘抖动" not in positive_prompt:
            warnings.append(
                "冲击层缺少「手绘抖动」，线条容易变成均匀速度线（CV-13）"
            )
        if not (
            re.search(r"至少\s*2\s*处", positive_prompt)
            and "锯齿" in positive_prompt
        ):
            warnings.append(
                "冲击层缺少至少 2 处尺寸可辨的锯齿情绪漫符（CV-13）"
            )
        if (
            "细线" in positive_prompt
            and "不是细线" not in positive_prompt
            and "不要细线" not in positive_prompt
        ):
            warnings.append("正句出现「细线」且未否定，冲击线容易偏细")
        # 背景简化（CV-14）：浅米纸底 + 1–3 个淡线元素
        if "浅米色" not in positive_prompt or "素描纸" not in positive_prompt:
            warnings.append(
                "背景缺少「浅米色素描纸」说明，应改为纸底简化背景（CV-14）"
            )
        if "氛围人群" in positive_prompt:
            warnings.append(
                "背景仍写「氛围人群」，应改为 1–3 个淡线元素（CV-14）"
            )
        # 「不整体提高对比度」「不压暗背景」是禁止项，不能当成使用了高对比/压暗
        high_contrast = (
            (
                "提高对比度" in prompt
                and "不整体提高对比度" not in prompt
                and "不提高对比度" not in prompt
            )
            or (
                "高对比" in prompt
                and "不做全局高对比" not in prompt
                and "不整体提高对比度" not in prompt
            )
        )
        if "封面模式" not in prompt and "封面加成" not in prompt and not has_impact and not high_contrast:
            warnings.append("提示词没有显式声明封面模式/封面加成（默认应为原画风 + 封面专用冲击层）")
        if high_contrast:
            warnings.append(
                "封面出现「提高对比度/高对比」；统一路径应为原画风 + 封面专用冲击层，"
                "不做全局高对比（CV-04）"
            )
        if (
            not has_impact
            and "原画风 + 冲击层" not in prompt
            and "原画风 + 封面专用冲击层" not in prompt
            and "故事 4 封面加成" not in prompt
        ):
            warnings.append(
                "没有检测到默认的「原画风 + 封面专用冲击层」元素；"
                "封面需要局部冲击层"
            )
        if has_impact:
            if not any(term in positive_prompt for term in CHOREOGRAPHY_TERMS):
                warnings.append(
                    "冲击线缺少起点/方向/密度/保护区说明，容易随机贴边"
                )
            if not all(term in prompt for term in IMPACT_NEGATIVE_TERMS):
                warnings.append(
                    "负面提示词缺少冲击线失败模式（铺满全图/糊成脏线/像贴图/"
                    "涂鸦遮脸或文字/线条穿过眼睛）"
                )
            if "硬边黑轮廓" in positive_prompt and (
                "较粗的黑色手绘线" in positive_prompt
                or "冲击线" in positive_prompt
            ):
                warnings.append(
                    "画风「避免硬边黑轮廓」与冲击线粗黑线冲突；"
                    "应改为「避免全图硬边黑描边」"
                )
        if not any(word in prompt for word in HOOK_WORDS):
            warnings.append(
                "提示词缺少视觉钩子词（特写/前景/高对比/红光/眼神/道具等）"
            )
        if not any(
            word in prompt for word in ("关键道具", "按钮", "屏幕", "车票", "协议", "治疗单")
        ):
            warnings.append("提示词没有明确的关键道具")
        # 压暗背景是最容易把封面做成纯黑底的指令，必须显式兜底；
        # 「不压暗背景」是禁止项，不算压暗。
        if "压暗" in prompt and "不压暗" not in prompt and "不得压成纯黑" not in prompt:
            issues.append(
                "封面出现「压暗」但没有写「不得压成纯黑」，容易生成纯黑背景"
            )
        if "纯黑背景" not in prompt:
            warnings.append("负面提示词缺少「纯黑背景」，建议补上")
        if "警报" in prompt:
            warnings.append(
                "封面使用了「警报」光，确认剧情确有警报；"
                "非警报场景改用夕阳/路灯/彩灯"
            )

    if any(pattern in sub for pattern in PREMISE_PATTERNS):
        warnings.append("副旁白疑似前情说明，建议改成代价/悬念句")

    print(
        f"故事：{breakdown.get('story_id', args.story_id or '未知')}；"
        f"第 {args.chapter} 章《{chapter.get('title', '')}》"
    )
    print(
        f"封面主旁白：{main_count} 字；副旁白：{sub_count} 字；"
        f"标红：{highlight or '无'}"
    )
    if issues:
        print("\n问题：")
        for issue in issues:
            print(f"  - {issue}")
        if warnings:
            print("\n警告：")
            for warning in warnings:
                print(f"  - {warning}")
        print("\n❌ 未通过：先修封面，再定稿。")
        return 1

    if warnings:
        print("\n警告（不阻断，请人工判断）：")
        for warning in warnings:
            print(f"  - {warning}")

    print("\n✅ 通过：封面文字与提示词结构符合要求。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
