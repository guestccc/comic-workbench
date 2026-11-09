/** 生成给 Claude Code 的「设计建议提炼规则」指令；网页本身不调用模型。 */
export function buildDesignRuleExtractionPrompt(
  feedbackId: number,
  apiBase: string,
): string {
  return `请使用 design-rule-extract 技能，处理设计建议 #${feedbackId}。

【输入边界】
用户只提供截图、建议文字或原文分析。结构化字段（kind / target / slot / scope / check_spec）、影响范围和要改哪些提示词都由你判断，不要要求用户填写或选择。

小红书建议通常只针对某个作品的某一章：先定位故事与章节，把建议记录和规则都落到 story_id + chapter_number，先优化这一章的封面或内容；效果确认后，再单独提出是否提升为全局规则或写入模板。定位不到故事 / 章节时暂停询问，不要默认全局。

【数据获取】
1. 先读取 AGENTS.md、.ai/blueprints/INDEX.md，以及封面质量门、提示词模板、设计建议库三份蓝图；
2. 读取 .claude/agents/cover-director.md、.claude/skills/story-breakdown/SKILL.md、.claude/skills/story-breakdown/cover_check.py；
3. GET ${apiBase}/api/design-feedbacks/${feedbackId}，拿到建议原文、截图文件名与已有规则；建议原文为空时以截图为准，截图读 backend/uploads/<screenshot_filename>，先把截图里的文字转写再提炼；
4. GET ${apiBase}/api/design-feedbacks/${feedbackId}/rules 看已有规则，避免重复；
5. GET ${apiBase}/api/settings/prompt-templates 与故事画风，确认规则应该插到哪一块。

【提炼要求】
1. 一条建议可以拆成多条规则：正面提示词 / 负面约束 / 文字要求 / 审片标准 / 硬检查；
2. 每条规则必须写清：改哪里、怎么改、作用范围、怎么判断；
3. 只写可执行约束，不写分析、不写“建议尝试”；
4. 与现有规则、画风、封面模式冲突时，列出来让用户选，不要自动覆盖；
5. 不确定的地方写成问题，不要硬猜。

【写回】
用 POST ${apiBase}/api/design-feedbacks/${feedbackId}/rules 逐条写回 draft：
- kind：prompt / negative / text / review / check；
- target：cover / body / guide / all；
- scope_type：global / story / chapter / pages（pages 只能用于 body）；
- story_id、chapter_numbers、page_numbers 按范围填写；
- priority：hard / soft；
- requirement / negative_terms / review_check / check_spec 按 kind 填写；
- created_by：claude。

再调用 POST ${apiBase}/api/design-rules/preview 获取影响数量。

【纪律】
- 只写 draft，不调用 activate；
- 不改模板、画风、已有页面或封面提示词；
- 输出规则草案表、影响数量、冲突和待确认问题，等用户确认。`
}

/** 生成给 Claude Code 的「规则返工」指令；只改提示词，不自动重新生图。 */
export function buildDesignRuleReworkPrompt(
  ruleId: number,
  resultId: number,
  apiBase: string,
): string {
  return `请使用 design-rule-rework 技能，处理规则 #${ruleId} 的失败核验 #${resultId}。

【数据获取】
1. GET ${apiBase}/api/design-rules/${ruleId}/results，找到核验 #${resultId}；
2. GET ${apiBase}/api/design-feedbacks 及规则详情，读取规则正文、范围、目标；
3. 找到对应故事 / 章节 / 页面当前 prompt，以及最近一次提示词快照；
4. 读取 AGENTS.md、相关蓝图、cover-director、cover_check，确认项目边界。

【返工要求】
1. 先判断失败是提示词问题还是生成图问题：
   - 提示词里能看到违规词 / 缺必要词 / 超字数：改提示词；
   - 提示词已经满足、但生成图仍失败：不要硬改提示词，告诉用户需要重新生图或调整画面描述。
2. 修改后重新调用 render，检查 rule_checks 是否全部通过；最多尝试 2 次。
3. 通过后才写回对应封面 / 正文页的 image_prompt；
4. 不要自动重新生图；提示用户生成后重新审片，并写回新的核验结果。
5. 不修改模板、画风、mapping、characters、chapters 结构。

【写回核验】
用户重新生图并审片后，用 POST ${apiBase}/api/design-rules/${ruleId}/results 记录新结果：
result=passed|failed|unknown、story_id、target_type、chapter_number、page_number、message、image_url、snapshot_id、reviewer=claude。

输出：失败原因、改了哪一段、返工后的 rule_checks、是否写回、是否还需要重新生图。`
}

/** 生成「章节规则推广到全局」指令；网页只复制，不直接改项目文件。 */
export function buildDesignRulePromotionPrompt(
  feedbackId: number,
  ruleIds: number[],
  apiBase: string,
): string {
  return `请使用 design-rule-promote 技能，把设计建议 #${feedbackId} 的章节规则推广到全局。

【规则】
${ruleIds.map((id) => `#${id}`).join('、')}

【目标】
1. 先读取 AGENTS.md、.ai/blueprints/INDEX.md、设计建议库、封面质量门、提示词模板蓝图；
2. GET ${apiBase}/api/design-feedbacks/${feedbackId} 和 ${apiBase}/api/design-feedbacks/${feedbackId}/rules，确认这些规则已激活、仍是章节范围，且这一章的效果已经确认；
3. 如果规则正文里还有具体故事 / 章节的标题或角色名，先改成通用表述，保留可执行约束，再把这几个规则 PATCH 成 scope_type=global（story_id=null、chapter_numbers=[]、page_numbers=[]）；不要新建重复规则；
4. 规则表是唯一 owner：不要写入全局模板，不要改章节封面文字、mapping、pages、characters、optimized_content；
5. 同步更新 story-breakdown 封面模式、cover-director、cover_check.py、chapter_check.py、封面质量门与相关蓝图，统一到主标题 ≤12 字、标题层级、背景焦点这三条标准；
6. 用 2–3 张不同故事的封面做 render 预览，确认 applied_rules / rule_checks，并运行后端测试、前端构建和相关 cover_check；
7. 记录变更历史，输出：推广了哪些规则、影响多少张封面、改了哪些文件、验证结果、回滚方式。

【纪律】
- 不写模板；不碰已有图片和具体章节文案；
- 只有用户明确要求推广时才改全局；
- 推广后验证失败时，先回退规则范围并报告。`
}

/** 生成「规则自动流水线」指令；需要用户明确同意消耗生图额度。 */
export function buildDesignRulePipelinePrompt(
  ruleId: number,
  resultId: number | null,
  storyId: number,
  chapterNumber: number,
  apiBase: string,
  maxImages = 2,
): string {
  const resultText = resultId == null ? '（无历史核验）' : `#${resultId}`
  return `请使用 design-rule-pipeline 技能，为规则 #${ruleId} 跑一次封面自动流水线。

【目标】
故事 ${storyId}，第 ${chapterNumber} 章封面；失败核验 ${resultText}。
本次最多生成 ${maxImages} 张；到达上限必须停止并报告，不要自行加量。

【流程】
1. 读取规则、历史核验、当前封面 prompt、AGENTS.md 和相关蓝图；
2. 调 ${apiBase}/api/settings/prompt-templates/render，检查 rule_checks；失败先按 design-rule-rework 修提示词，最多 2 次；
3. 通过后写回第 ${chapterNumber} 章 cover.image_prompt；
4. 调 ${apiBase}/api/stories/${storyId}/breakdown/chapters/${chapterNumber}/cover/generate 生成封面，等待结果；
5. 用 cover-director image 模式审片；
6. 用 POST ${apiBase}/api/design-rules/${ruleId}/results 写核验结果；
7. 通过则调 use 接口使用该图；失败记录后按额度重试或停止。

【纪律】
- 不自动超过我同意的生图张数；
- 不改模板、画风、mapping、characters；
- 每张图都写核验结果，说明具体违反哪条规则。`
}
