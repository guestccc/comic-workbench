#!/usr/bin/env python3
"""把 mapping-director 的完整候选 mapping 转成分镜审阅变更列表。

用法：
  python proposal_to_changes.py --story-id 5 --proposal proposal.json --output changes.json

输出：
  {"changes": [...]}，可直接 PUT 到
  /api/stories/<ID>/breakdown/mapping-review

退出码：0 = 成功；1 = 失败。
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


def load_breakdown(
    api: str, story_id: int, local_path: str | None = None
) -> dict:
    if local_path:
        data = json.loads(
            Path(local_path).read_text(encoding="utf-8")
        )
        if not data:
            raise SystemExit(f"{local_path} 为空")
        return data
    url = f"{api}/api/stories/{story_id}/breakdown"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data:
        raise SystemExit(f"{url} 返回空，故事还没有拆解结果")
    return data


def split_raw_by_lengths(text: str, lengths: list[int]) -> list[str]:
    """按归一化字符数切分原始文本，保证切片拼接等于 text。"""
    positions = [
        index
        for index, char in enumerate(text)
        if not IGNORED.match(char)
    ]
    if sum(lengths) != len(positions):
        raise SystemExit(
            "分段长度与原文不匹配："
            f"期望 {len(positions)}，实际 {sum(lengths)}"
        )
    result: list[str] = []
    previous_raw = 0
    cursor = 0
    for length in lengths:
        if length <= 0:
            raise SystemExit("候选 mapping 里存在空段")
        cursor += length
        # 把边界后的标点/换行留给上一段，让下一段从正常文字开始
        raw_end = (
            len(text) if cursor >= len(positions) else positions[cursor]
        )
        result.append(text[previous_raw:raw_end])
        previous_raw = raw_end
    return result


def segment_lengths(items: list[dict]) -> list[int]:
    return [len(normalize(item.get("source_text") or "")) for item in items]


def boundaries(lengths: list[int]) -> list[int]:
    total = 0
    result: list[int] = []
    for length in lengths:
        total += length
        result.append(total)
    return result[:-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="候选 mapping 转审阅变更")
    parser.add_argument("--story-id", type=int, required=True)
    parser.add_argument("--proposal", required=True, help="候选 mapping JSON")
    parser.add_argument("--output", required=True, help="输出 changes JSON")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument(
        "--breakdown", help="本地 breakdown JSON；不传时调用 API"
    )
    args = parser.parse_args()

    breakdown = load_breakdown(args.api, args.story_id, args.breakdown)
    base = sorted(
        breakdown.get("mapping") or [],
        key=lambda item: item.get("page_number", 0),
    )
    proposal = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
    proposed = sorted(
        proposal.get("mapping") or [],
        key=lambda item: item.get("page_number", 0),
    )
    if not base or not proposed:
        raise SystemExit("base mapping 或候选 mapping 为空")
    if any(item.get("excluded") for item in base):
        raise SystemExit("base mapping 含 excluded 段，暂不支持自动转换")

    optimized = breakdown.get("optimized_content") or ""
    base_text = "".join(item.get("source_text") or "" for item in base)
    proposed_text = "".join(
        item.get("source_text") or "" for item in proposed
    )
    if normalize(base_text) != normalize(optimized):
        raise SystemExit("base mapping 与优化文不一致，先修 mapping")
    if normalize(proposed_text) != normalize(optimized):
        raise SystemExit("候选 mapping 与优化文不一致，先修提案")

    base_lengths = segment_lengths(base)
    proposed_lengths = segment_lengths(proposed)
    base_bounds = boundaries(base_lengths)
    proposed_bounds = boundaries(proposed_lengths)
    common = sorted(set(base_bounds) & set(proposed_bounds))

    base_starts: list[int] = []
    cursor = 0
    for length in base_lengths:
        base_starts.append(cursor)
        cursor += length
    proposed_starts: list[int] = []
    cursor = 0
    for length in proposed_lengths:
        proposed_starts.append(cursor)
        cursor += length

    total = sum(base_lengths)
    changes: list[dict] = []
    region_start = 0
    for boundary in common + [total]:
        region_end = boundary
        base_indices = [
            index
            for index, (start, length) in enumerate(
                zip(base_starts, base_lengths)
            )
            if start >= region_start and start + length <= region_end
        ]
        proposed_indices = [
            index
            for index, (start, length) in enumerate(
                zip(proposed_starts, proposed_lengths)
            )
            if start >= region_start and start + length <= region_end
        ]
        base_ends = [
            base_starts[index] + base_lengths[index]
            for index in base_indices
        ]
        proposed_ends = [
            proposed_starts[index] + proposed_lengths[index]
            for index in proposed_indices
        ]
        if base_ends != proposed_ends:
            old_text = "".join(
                base[index].get("source_text") or ""
                for index in base_indices
            )
            slices = split_raw_by_lengths(
                old_text,
                [proposed_lengths[index] for index in proposed_indices],
            )
            fallback_paragraphs = [
                base[index].get("paragraph") or ""
                for index in base_indices
            ]
            fallback_parts = [
                base[index].get("part") or ""
                for index in base_indices
            ]
            fallback_paragraph = "、".join(
                dict.fromkeys(
                    value for value in fallback_paragraphs if value
                )
            )
            fallback_part = "、".join(
                dict.fromkeys(value for value in fallback_parts if value)
            )
            segments = []
            for proposed_index, source_text in zip(
                proposed_indices, slices
            ):
                item = proposed[proposed_index]
                segments.append(
                    {
                        "source_text": source_text,
                        "summary": item.get("summary") or "",
                        "paragraph": item.get("paragraph")
                        or fallback_paragraph,
                        "part": item.get("part") or fallback_part,
                        "beat_type": item.get("beat_type") or "",
                        "time_place": item.get("time_place") or "",
                        "characters": item.get("characters") or [],
                        "visual_load": item.get("visual_load"),
                    }
                )
            kind = (
                "split"
                if len(segments) > len(base_indices)
                else "merge"
                if len(segments) < len(base_indices)
                else "split"
            )
            changes.append(
                {
                    "id": f"change-{len(changes) + 1}",
                    "kind": kind,
                    "risk": "low",
                    "old_page_numbers": [
                        base[index].get("page_number")
                        for index in base_indices
                    ],
                    "proposed_segments": segments,
                    "reason": (
                        "mapping-director 提案："
                        f"原 {len(base_indices)} 段改为 {len(segments)} 段"
                    ),
                }
            )
        region_start = region_end

    if not changes:
        raise SystemExit("候选 mapping 与 base mapping 分段相同，没有变更")
    Path(args.output).write_text(
        json.dumps({"changes": changes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"故事 {args.story_id}：生成 {len(changes)} 条变更")
    print(f"输出：{args.output}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
