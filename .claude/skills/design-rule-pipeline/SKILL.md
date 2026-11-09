---
name: design-rule-pipeline
description: 按规则跑封面自动流水线：render → 生图 → cover-director 审片 → 写核验结果；失败可返工重试。只在用户明确要求并同意消耗生图额度时使用。
---

# 封面规则自动流水线

## 前置

用户必须明确说「跑自动流水线」并同意最多生成几张。以指令里的 maxImages 为准（默认最多 2 张，前端上限 3 张）。只支持章节封面；正文页生图接口未接入。

## 输入

规则 ID + 失败核验 ID（可选）+ 故事 / 章节。读取：

- 规则、历史核验、当前封面 prompt；
- `AGENTS.md`、封面质量门、提示词模板、设计建议库蓝图；
- `cover-director.md`、`cover_check.py`、`design-rule-rework` 技能。

## 步骤

1. 若规则未激活，先让用户确认是否激活；不要静默激活。
2. 调 render 生成封面 prompt，检查 `rule_checks`：
   - 有 failed：先用 `design-rule-rework` 改提示词，再 render，最多 2 次；
   - 全部通过后再写回 `chapters[n].cover.image_prompt`。
3. 调用 `POST /api/stories/{id}/breakdown/chapters/{n}/cover/generate` 生成封面；同步等待，最长 600 秒。
4. 用 `cover-director` image 模式审片：读生成图，按规则和评分卡判定。
5. 写核验结果：
   `POST /api/design-rules/{ruleId}/results`，字段：result、story_id、target_type=cover、chapter_number、message、image_url、snapshot_id、reviewer=claude。
6. 通过：调 `POST /api/stories/{id}/image-generations/{generation_id}/use` 使用这张图，结束。
7. 不通过：记录 failed；如果还有额度，用 rework 改 prompt 后重试；没有额度就停止并报告。

## 纪律

- 不自动循环超过用户同意的张数；
- 不修改模板、画风、mapping、characters；
- 每张图都要写核验结果；
- 失败原因要具体到规则和画面，不写“效果不好”。
