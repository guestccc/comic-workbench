import type { Story } from '../types'

/**
 * 故事拆解指令生成。
 *
 * 拆解规则维护在项目技能 `.claude/skills/story-breakdown/SKILL.md`，
 * 这里只生成一条带故事 ID 的短指令：故事名与原文由 Claude 在项目内
 * 自行查询数据库获取，避免复制大段原文，也避免读到编辑前的旧版本。
 */
export const STORY_BREAKDOWN_SKILL = 'story-breakdown'

/**
 * 解析后端地址。
 *
 * 生产模式下前端由后端直接托管（同源，默认 8123）；
 * 开发模式下前端跑在 5173，但 Vite 已把 /api 代理到 8123，两种方式都可用。
 */
function resolveApiBase(): string {
  return typeof window === 'undefined'
    ? 'http://127.0.0.1:8123'
    : window.location.origin
}

/**
 * 判断故事当前是否具备拆解条件。
 *
 * 返回不可拆解的原因；返回 null 表示可以复制拆解指令。
 * 故事列表页与详情页共用这段校验，避免两处规则不一致。
 */
export function getBreakdownBlockedReason(story: Story): string | null {
  if (!story.content.trim()) {
    return '故事原文为空，请先补充原文'
  }
  if (!story.art_style_id) {
    return '请先编辑该故事并选择画风，再复制拆解指令'
  }
  if (!story.art_style_name || !story.art_style_content) {
    return '该故事选用的画风已被删除，请重新选择画风后再复制'
  }
  return null
}

/**
 * 生成一段可直接粘贴到本项目 Claude Code 的拆解指令。
 *
 * 指令只携带故事 ID，Claude 会优先调用后端接口读取数据，
 * 接口不可用时回退为直读项目 SQLite；拆解结果通过详情页接口写回。
 */
export function buildStoryBreakdownPrompt(storyId: number): string {
  const apiBase = resolveApiBase()
  return `请使用 ${STORY_BREAKDOWN_SKILL} 技能（.claude/skills/${STORY_BREAKDOWN_SKILL}/SKILL.md），对故事 ID 为 ${storyId} 的故事一次性完成「原文优化 → 角色设定卡 → 全部分镜拆解」，并把结果写回工作台详情页。

【数据获取】
1. 先调用本项目后端接口：\`curl -s ${apiBase}/api/stories/${storyId}\`，从返回的 JSON 中读取 name（故事名）、content（故事原文）、art_style_name（画风名称）与 art_style_content（画风描述）。
2. 若后端未启动导致请求失败，改为直接读取项目根目录下的 SQLite：\`sqlite3 data/workbench.db "SELECT name, content, art_style_id FROM stories WHERE id = ${storyId};"\`；若 art_style_id 非空，再读取 \`app_settings\` 表中 key 为 \`art_styles\` 的 JSON，按 id 找到该画风的 name 与 content（详见技能【使用方式】）。
3. 两种方式都读不到时，直接告诉我读取失败的原因，不要向我索要原文，也不要自行编造故事。
4. 故事记录中的 art_style_name 与 art_style_content 即该故事选用的画风；若为空（未选择画风或画风已被删除），先告诉我并让我重新选择，不要自行编造，也不要改用其他画风。
5. 原文结尾若是我说明过的刻意付费卡点、悬念留白或未完结章节，保留原结尾，不补写、不扩写；若没有说明且句子戛然而止，先告知我并停止。

【执行方式】
1. 我们做的是短文，不要做故事简化：不删情节、不合并信息点，只在保留原意与第一人称口吻的前提下润色语言、调整段落节奏。
2. 默认按 B. 强节奏悬念优化，直接输出完整优化文，不要停下来等我选择方案；只有我明确要求比较方案时，才给 A/B/C。
3. 一次性拆出全部角色设定卡与全部分镜，不要等待我上传参考垫图，也不要生成人物合影提示词。参考图由我在外部生图 AI 中自行绑定。
4. 角色卡中的 name 就是生图变量名。每页 image_prompt 中涉及人物外形、五官、妆造、服装、配饰、身高体态的内容，统一用 {{角色名}} 变量，例如 {{我}}、{{小八老师}}；不要在提示词里重复粘贴整段外形描述。完整外形写在角色卡和 character_review 中。
5. 生图提示词必须严格使用该故事选用的画风（art_style_name / art_style_content），不得套用技能里出现过的旧画风或固定模板风格；并按【画风】【画面】【角色一致性】【画面形式】【文字区】【页码】【负面提示词】7 类分行书写，每类以【分类】开头；其中【文字区】再细分为「顶部留白 / 主要旁白 / 中间红色加粗关键词 / 副旁白」几行，不要挤成一整段。
6. 第 1 页是钩子封面（即小红书作品第一页），采用「提问互动开场」：主要旁白直接向读者发问，副旁白交代情境，结尾抛出信息差或悬念；画面通常用特写/中景聚焦核心人物或关键道具。第 2 页起按优化文顺序叙事，不要与第 1 页重复同一动作或台词。
7. 每页只表现一个动作或一个情绪点；对话气泡不超过 2 句，单句不超过 15 字。
8. 为每页标注页面作用 page_role，只能取：钩子封面（仅第 1 页）、铺垫、冲突、反转、爆点、情绪高潮、收尾；每页取本页最主要的一个，不要全部笼统写铺垫。

【结果写回】
1. 先 PATCH \`${apiBase}/api/stories/${storyId}/breakdown\`，写入 optimized_content 与 characters；角色卡 name 必须与生图变量名一致。
2. DELETE \`${apiBase}/api/stories/${storyId}/breakdown/pages\` 清空旧分镜页。
3. 逐页 PUT \`${apiBase}/api/stories/${storyId}/breakdown/pages/{页码}\`，写入全部分镜；image_prompt 用 {{角色名}} 变量。
4. 不要再写 group_photo_prompt。
5. 写回失败时重试 1 次；仍失败必须明确告诉我「结果仅在对话中，未能写入详情页」，不要静默忽略。

【输出要求】
1. 若当前会话未加载该技能，请先读取上述 SKILL.md，并严格按其规则执行。
2. 回复第一行先输出：故事名称：XXX。若数据库中的故事名为空，请根据原文自行拟定一个简洁名称，并按技能中的【名称回写】步骤写回数据库；已有名称时不要覆盖。
3. 一次性连续输出，不要停下来等我确认。若单次输出受长度限制，可以分段继续输出，但写回必须完成，不能只给摘要。
4. 每页必须完整输出技能规定的全部条目（本页故事内容、页面作用、是否回忆页、出场人物、人物设定回顾、场景、动作与状态、变化说明、主要旁白、标红关键词、副旁白、对话气泡、景别、生图提示词），严禁缺项、省略或简化。
5. 只输出文字脚本与生图提示词，不要实际生成图片，不要生成或管理参考垫图。`
}
