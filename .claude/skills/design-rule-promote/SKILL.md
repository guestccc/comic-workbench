---
name: design-rule-promote
description: 把章节试跑验证过的设计规则推广到全局；同步技能、审片、检查脚本与蓝图，规则表作为唯一 owner，不写模板。用户说推广到全局、全局化规则、把这一章的做法用到所有封面时使用。
---

# 章节规则推广到全局

## 输入

- 设计建议 ID
- 要推广的规则 ID 列表
- 来源故事 / 章节

## 前置检查

1. 读 `AGENTS.md`、`.ai/blueprints/INDEX.md`；重点读设计建议库、封面质量门、提示词模板三份蓝图；
2. 读 `.claude/skills/story-breakdown/SKILL.md` 的封面模式、`.claude/agents/cover-director.md`、`cover_check.py`、`chapter_check.py`；
3. `GET /api/design-feedbacks/{id}` 与 `/api/design-feedbacks/{id}/rules`；
4. 确认要推广的规则 `status=active`、`scope_type != global`；
5. 确认来源章节已经试跑并确认效果；没有确认时停止，不要自动推广。

后端默认 `http://127.0.0.1:8123`，以指令中给出的地址为准。

## 推广步骤

1. **通用化规则文本**：如果规则正文里还有具体故事、章节、角色名或某一次标题，先改成通用表述，保留可执行约束。
2. **改范围**：对每条规则 `PATCH /api/design-rules/{id}`：
   - `scope_type=global`
   - `story_id=null`
   - `chapter_numbers=[]`
   - `page_numbers=[]`
   - 不新建重复规则；同一规则保留版本历史。
3. **保持单一 owner**：
   - 规则表是唯一可编辑源；
   - 不写入全局模板；
   - 技能、agent、检查脚本只同步标准，不复制成第二份规则源。
4. **同步标准**：
   - `story-breakdown` 封面模式：主标题 ≤12 字、标题层级、背景焦点；
   - `cover-director`：审片清单加入 3 秒可读性、标题层级、背景焦点；
   - `cover_check.py` / `chapter_check.py`：主标题 >12 字判失败；
   - 封面质量门、提示词契约、README 的对应字数与标准；
   - 蓝图追加变更历史。
5. **验证**：
   - 用 2–3 张不同故事的封面调用 `POST /api/settings/prompt-templates/render`（`preview=true`），确认 `applied_rules` 包含推广规则、`rule_checks` 全部通过；
   - 运行 `uv run pytest`、`npm test`、`npm run build`；
   - 对相关章节运行 `cover_check.py`。
6. **记录**：规则版本、蓝图变更历史、来源建议状态（verified）；输出推广记录。
7. **报告**：推广了哪些规则、影响多少张封面、改了哪些文件、验证结果、回滚方式。

## 禁止

- 不写模板；不改已有图片、具体章节文案、`mapping`、`pages`、`characters`、`optimized_content`；
- 不自动激活或停用无关规则；
- 验证失败时先回退规则范围并报告，不把失败状态留在全局。
