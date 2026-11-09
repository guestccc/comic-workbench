---
name: design-rule-extract
description: 把小红书截图 / 文字建议提炼成结构化设计规则草案；只写 draft，不激活、不改模板。用户说提炼设计建议、设计规则、把建议变成规则时使用。
---

# 设计建议 → 结构化规则

## 输入

用户给出设计建议 ID（例如「处理设计建议 #12」），或直接粘贴截图 + 文字。先读取：

1. `AGENTS.md`、`.ai/blueprints/INDEX.md`；
2. `2026-10-27-cover-quality-gate.md`、`2026-10-31-prompt-templates.md`、`2026-10-31-design-feedback-library.md`；
3. `.claude/agents/cover-director.md`、`.claude/skills/story-breakdown/SKILL.md`、`cover_check.py`；
4. `GET /api/design-feedbacks/{id}`；建议原文为空时以截图为准；如果返回 `screenshot_filename`，读取 `backend/uploads/<filename>` 看截图，先把截图里的文字转写再提炼；
5. `GET /api/design-feedbacks/{id}/rules` 看已有规则；
6. `GET /api/settings/prompt-templates` 与当前画风，确认规则会插到哪一块。

后端默认 `http://127.0.0.1:8123`，以用户给出的地址为准。

## 默认范围

小红书建议通常只针对某个作品的某一章。必须先定位对应的故事与章节，把建议记录和规则都落到 `story_id + chapter_number`，先优化这一章的封面或内容并观察效果。

- 建议记录没有绑定时：`PATCH /api/design-feedbacks/{id}`，回填 `scope=chapter`、`story_id`、`chapter_number`。
- 规则默认写 `scope_type=chapter`；不得默认写 `global`。
- 只有用户明确说这是通用原则，或该章效果确认后要求推广，才写 `global` 草案或考虑写入模板。
- 定位不到故事 / 章节时暂停询问，不要猜，也不要退化成全局。

## 提炼原则

1. **一条建议可以拆成多条规则**，不要只写一段话。
2. 每条规则必须能回答：改哪里、怎么改、什么范围、怎么判断。
3. 只写可执行约束，不写分析、不写故事剧情、不写“建议尝试”这类空话。
4. 不发明原文没有的设计要求；不确定的地方写进 `questions`，不要硬猜。
5. 与现有规则/画风/封面模式冲突时，不要自动覆盖，列在 `conflicts` 里让用户选。

## 规则类型

| kind | 用途 | 必填 |
|---|---|---|
| `prompt` | 正面提示词，插到【画面】/【封面模式】/【文字区】 | `requirement` |
| `negative` | 负面约束，追加到【负面提示词】 | `negative_terms` |
| `text` | 文字区要求 | `requirement` + `slot=text_zone` |
| `review` | 审片标准，不进 prompt，交给 cover-director | `review_check` |
| `check` | 提示词硬检查，渲染后立即执行 | `check_spec`：`forbidden_terms` / `required_terms` / `max_chars` / `regex` |

## 范围

默认用 `chapter`；`global` 只在用户明确要求推广时使用。

- `chapter`：指定故事 + `chapter_numbers`（单篇笔记建议的默认值）；
- `story`：指定故事，必须给 `story_id`；
- `pages`：只适用于 `target=body`，必须给 `story_id` + `chapter_numbers` + `page_numbers`（章内页码）；
- `global`：所有匹配目标；必须等该章效果确认后由用户显式提出。

`target`：`cover` / `body` / `guide` / `all`。

## 写回

对每条规则调用：

```text
POST /api/design-feedbacks/{id}/rules
{
  "title": "短标题",
  "kind": "prompt",
  "target": "cover",
  "slot": "scene",
  "scope_type": "global",
  "story_id": null,
  "chapter_numbers": [],
  "page_numbers": [],
  "priority": "hard",
  "requirement": "可执行要求",
  "negative_terms": [],
  "review_check": "",
  "check_spec": {},
  "created_by": "claude"
}
```

写回后状态是 `draft`。**不要调用 activate，不要改模板、画风、已有提示词。**

硬检查示例：

```json
{"type": "forbidden_terms", "terms": ["神情沉静", "安静克制"]}
{"type": "required_terms", "terms": ["关键道具"]}
{"type": "max_chars", "field": "narration_sub", "value": 35}
```

审片 / 生成图核验结果写回 `POST /api/design-rules/{rule_id}/results`，字段：`result=passed|failed|unknown`、`story_id`、`target_type`、`chapter_number`、`page_number`、`message`、`image_url`、`snapshot_id`、`reviewer=claude`。

再调用 `POST /api/design-rules/preview` 拿影响数量，把「规则 / 范围 / 影响图数 / 冲突 / 问题」列给用户，等用户确认。

## 输出

1. 一句话诊断：这条建议在批评什么；
2. 规则草案表：标题 / 类型 / 目标 / 范围 / 影响数量 / 优先级；
3. 冲突列表；
4. 需要用户确认的问题；
5. 明确说「已写为 draft，未激活」。
