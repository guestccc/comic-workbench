---
name: design-rule-rework
description: 根据失败的规则核验返工提示词；先判断是提示词问题还是生成图问题，改完重新 render 验证 rule_checks，通过后再写回，不自动重新生图。用户说规则返工、核验失败、按规则重做时使用。
---

# 设计规则返工

## 输入

规则 ID + 失败核验 ID，例如「规则 #7 的核验 #12 失败，返工」。先读取：

1. `GET /api/design-rules/{ruleId}/results`，找到失败核验；
2. 规则详情与建议原文；
3. 对应故事 / 章节 / 页面当前 prompt、最近一次提示词快照；
4. `AGENTS.md`、相关蓝图、`cover-director`、`cover_check`。

## 判断

- **提示词问题**：prompt 里能直接找到违规词、缺必要词、超字数、结构缺失 → 改提示词。
- **生成图问题**：prompt 已经满足规则，但成品图仍失败 → 不要硬改提示词；告诉用户需要重新生图，或调整画面描述后重试。
- 不确定时列为「需要人工判断」，不要瞎改。

## 返工流程

1. 修改 `content` / `image_prompt` 中对应的部分；
2. 重新调用 `POST /api/settings/prompt-templates/render`；
3. 检查返回的 `rule_checks`：
   - 全部 `passed=true` 才继续；
   - 失败时按 message 修，最多 2 次；
4. 通过后写回：
   - 封面：PATCH `chapters`，只改目标章节 `cover.image_prompt`；
   - 正文：PUT 对应页面，只改 `image_prompt`；
5. 不修改模板、画风、mapping、characters、chapters 结构。

## 核验结果

不要自动重新生图。提示用户：

- 先重新生图；
- 再用 `cover-director` image 模式审片；
- 用 `POST /api/design-rules/{ruleId}/results` 写新结果：
  `result=passed|failed|unknown`、`story_id`、`target_type`、`chapter_number`、`page_number`、`message`、`image_url`、`snapshot_id`、`reviewer=claude`。

## 输出

失败原因、改了哪一段、返工后的 rule_checks、是否写回、是否还需要重新生图。
