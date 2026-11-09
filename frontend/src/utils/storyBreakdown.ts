import type {
  Story,
  StoryboardChapterRead,
  StoryboardPage,
} from '../types'

/**
 * 故事拆解指令生成。
 *
 * 拆解规则维护在项目技能 `.claude/skills/story-breakdown/SKILL.md`。
 * 新流程分两步：
 * 1. 分镜对照：只把优化文按原文顺序切成镜头段落，写回 mapping，供人工确认；
 * 2. 分镜头脚本：读取已确认的 mapping，逐页生成分镜并写回。
 *
 * 两步指令都只携带故事 ID，故事名、原文、画风与 mapping 由 Claude
 * 在项目内查询后端接口获取，避免复制大段文本或读到旧版本。
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

const COMMON_DATA_RULES = (apiBase: string, storyId: number) => `【数据获取】
1. 先调用本项目后端接口：\`curl -s ${apiBase}/api/stories/${storyId}\`，从返回的 JSON 中读取 name（故事名）、content（故事原文）、art_style_name（画风名称）与 art_style_content（画风描述）。
2. 调用 \`${apiBase}/api/stories/${storyId}/breakdown\` 读取现有 optimized_content、characters、mapping、pages。
3. 若后端未启动导致请求失败，改为直接读取项目根目录下的 SQLite：\`sqlite3 data/workbench.db "SELECT name, content, art_style_id FROM stories WHERE id = ${storyId};"\`；画风见 \`app_settings\` 表中 key 为 \`art_styles\` 的 JSON。
4. 两种方式都读不到时，直接告诉我读取失败的原因，不要向我索要原文，也不要自行编造故事。
5. 故事记录中的 art_style_name 与 art_style_content 即该故事选用的画风；若为空（未选择画风或画风已被删除），先告诉我并让我重新选择，不要自行编造，也不要改用其他画风。
6. 原文结尾若是我说明过的刻意付费卡点、悬念留白或未完结章节，保留原结尾，不补写、不扩写；若没有说明且句子戛然而止，先告知我并停止。

【提示词模板】
正文页和章节封面的最终 image_prompt 必须调用 \`POST ${apiBase}/api/settings/prompt-templates/render\` 生成（正文 template_type=body，封面 template_type=cover）；不要手写【画风】【文字区】【页码】【封面模式】【负面提示词】。封面统一走「原画风 + 封面专用冲击层」：冲击线和关键轮廓用较粗黑色手绘线，脸和皮肤保持淡色铅笔柔和质感；冲击层至少 3 条粗黑集中手绘射线（有抖动感）+ 至少 2 处可辨锯齿漫符；content 必须写清冲击线的起点/方向/密度/保护区，以及本页 1–3 个背景元素名和排除清单。背景统一走浅米纸底简化标准。不整体提高对比度/压暗背景。引导卡暂不走模板。`

/**
 * 角色卡模式：在正文、封面、引导卡之前，一次性拆出整篇故事的全部角色卡。
 *
 * 角色卡是生图变量 {{角色名}} 的唯一事实源；已有角色卡默认保留，
 * 只补缺失角色，避免覆盖用户在生图平台同步回来的外形调整。
 */
export function buildCharacterCardsPrompt(storyId: number): string {
  const apiBase = resolveApiBase()
  return `请使用 ${STORY_BREAKDOWN_SKILL} 技能的「角色卡」模式（.claude/skills/${STORY_BREAKDOWN_SKILL}/SKILL.md），为故事 ID ${storyId} 一次性拆出整篇故事的全部角色卡，并写回 characters。不要生成正文、分镜页、章节封面或引导卡，不要修改 optimized_content、mapping、chapters、pages。

${COMMON_DATA_RULES(apiBase, storyId)}

【硬规则】
1. 只按 optimized_content 拆角色。optimized_content 为空时停止，告诉我先执行「分镜对照」生成优化文；不要从原始故事直接编角色。
2. 默认补齐，不覆盖：已有角色卡原样保留，只补缺失角色。只有我明确说「全部重拆角色卡」时，才允许替换整份 characters，并在写回前列出将被替换的卡片等我确认。
3. 按整篇 optimized_content 识别，并结合 mapping 的 summary 检查后段才出场的角色，不要只拆前几章出现的人。第一人称主角统一命名为「我」。有台词、有独立动作或反复出场的具名角色都要建卡；只被提及、不会在画面中出场的角色不建卡。
4. 没有名字但会反复出场的群演（男模、同事、保镖等）用稳定称呼建一张群像卡，避免每页临时编外形。
5. 同一角色跨年龄、跨时代且外形差异大时拆成两张卡，在 role 里标明时期（如「十九岁」「婚后」）；正文页按时间线引用对应变量，不要用一张卡硬覆盖两个年龄。
6. 角色卡最多 20 张，name 唯一且全程一致。
7. appearance 第一句必须显式写「性别：男」或「性别：女」，群像卡写「性别：男女混合」并说明固定成员构成；再覆盖发型、长相、年龄感、服装、配饰、体态六项。不得只靠姓名、称谓或「成年女性」基准暗示性别。女性角色按技能【角色设定与变量】的女性基准写；不写剧情、心理、镜头；不写「同上」「见前文」。
8. 角色卡是唯一事实源：正文和封面的生图提示词只引用 {{角色名}} 变量，不重复展开外形。

【写回】
PATCH \`${apiBase}/api/stories/${storyId}/breakdown\`，只写 characters：
{
  "characters": [
    {"name": "我", "role": "主角", "appearance": "性别：男/女；发型、长相、年龄感、服装、配饰、体态……"}
  ]
}
不要写 pages / mapping / chapters / optimized_content；已有角色卡不要覆盖。

【自检】
1. name 唯一、非空，1–20 张；
2. 优化文中有台词或独立动作的具名角色都有卡；
3. 没有把只提名字、不出场的角色建成卡；
4. 每张卡的 appearance 开头都有显式性别（群像卡为男女混合），且六项齐全；
5. 没有未登记的角色变量。

【输出要求】
1. 先输出角色表：角色名 / 性别 / 身份 / 一句话外形 / 出场范围（哪几章或哪个时间线）。
2. 说明是新增还是补齐。
3. 写回成功后输出：\`角色卡已写回工作台，请确认后再生成正文、封面和引导卡。\`
4. 停下来等我确认。`
}

/**
 * 第一步：只生成分镜对照表，不生成分镜头脚本。
 *
 * 输出并写回 mapping：每页对应优化文的一段连续原文，按原文顺序切开；
 * 不重排、不去重、不合并跨段事件。写回后停下来等待用户确认。
 */
export function buildStoryMappingPrompt(storyId: number): string {
  const apiBase = resolveApiBase()
  return `请使用 ${STORY_BREAKDOWN_SKILL} 技能的「分镜对照」模式（.claude/skills/${STORY_BREAKDOWN_SKILL}/SKILL.md），对故事 ID 为 ${storyId} 的故事先输出分镜对照表。这一步只做对照，不要生成分镜头脚本，不要写回分镜页。

【先走 mapping-director】
拆分或复核先交给 \`.claude/agents/mapping-director.md\`（propose 或 review 模式），主会话只负责 mapping_check 与写回。无法调用子代理时明确说明，不要静默自己拆。

【流程回执（必须输出）】
1. 开始拆分前说明：已启动 mapping-director propose；如果无法启动，立即停止，不要自己拆。
2. 写回前必须再开一个**全新的** mapping-director review 上下文（或 storyboard-director）审最终方案；同一个提案上下文不能给自己盖章。
3. 写回前运行 mapping_check，贴出通过/警告结果。
4. 写回后输出回执：
   - 提案：mapping-director
   - 独立审阅：<agent 名称 / 未审>
   - mapping_check：通过 / 几条警告
   - 对照表页数
   - 状态：待用户确认（不要自动确认，也不要把 mapping 标成已确认）
5. 没有 agent 提案、或没有独立审阅时，不得写回 mapping。

【歧义边界 → 审阅草稿】
1. mapping-director 拆分时要额外列出“拿不准”的边界：拆/合两可、跨场景、台词超过 2 组、动作链切断等。每处给出当前方案和备选方案。
2. 写回 mapping 后，立刻把这些歧义写成审阅草稿，调用 PUT \`${apiBase}/api/stories/${storyId}/breakdown/mapping-review\`，请求体 {"changes":[...]}，不要只在聊天里逐条问用户。
3. **每条歧义必须是真实的 split 或 merge 变更，并带 proposed_segments**；禁止只用 keep 占位，也禁止把“当前/备选/理由”塞进 reason 就算一条变更。keep 只用于混合草稿里明确“不改”的少数项，不能单独构成草稿。
   reason 里禁止出现 L1、L85、atom、line 这类内部编号；只能用用户能看到的「第X段」和原文短句来说明。
4. 变更示例：
   {"id":"split-30","kind":"split","risk":"high","old_page_numbers":[30],
    "proposed_segments":[{"source_text":"前半段原文","summary":"…","paragraph":"第47段","part":"1/2"},
                         {"source_text":"后半段原文","summary":"…","paragraph":"第47段","part":"2/2"}],
    "reason":"一个镜头放不下三个时间点。"}
5. 没有歧义时不用建草稿，但回执要写“无歧义边界”。
6. 用户处理完审阅并应用后，才允许进入「分镜头脚本」。

${COMMON_DATA_RULES(apiBase, storyId)}

【优化文】
1. 如果 optimized_content 为空：按技能【故事优化规则】优化原文，默认使用 B. 强节奏悬念，然后 PATCH \`${apiBase}/api/stories/${storyId}/breakdown\` 写回 optimized_content。
2. 如果已有 optimized_content：直接使用，不要重新优化，不要覆盖。
3. 若故事原本没有名称，按技能【名称回写】写回一个简洁名称；已有名称时不要覆盖。

【分镜对照怎么做】
1. 把 optimized_content 按原文顺序切成「镜头段落」。一个镜头能放的内容很少：一个动作、一个情绪、一句关键台词或一个小信息点就是一个镜头段落；一个自然段太长就按句子/动作拆成多个镜头段落，短段落不合并。
2. 每个镜头段落对应一页，页码从 1 开始连续编号。不要钩子页，第 1 页就是原文第一个镜头段落。
3. 严格按原文顺序：不重排、不去重、不跳段、不合并跨段事件。原文开头预叙、后文重复讲同一件事时，两处都按原文位置各出页。单独成行的章节编号（1/2/3…）不是镜头内容，不要单独成页，并入相邻页的 source_text（通常在段首）。
4. 每页的 source_text 必须是该页对应的优化文连续摘录，不要改写；所有页的 source_text 按顺序拼起来应覆盖整篇 optimized_content，不重叠、不遗漏。
5. summary 用一句话写这一页讲什么，供对照表展示，不是最终副旁白。
6. paragraph 写原文段号（如「第3段」），part 写拆分（如「1/2」）；没有拆分可留空。
7. 如果现有 mapping 中已有 excluded=true 的弃用段，重写时尽量保留同一段的弃用标记；无法对应时先问我，不要擅自恢复或删除。

【写回】
PATCH \`${apiBase}/api/stories/${storyId}/breakdown\`，写入：
{
  "mapping": [
    {"page_number": 1, "source_text": "...", "summary": "...", "paragraph": "第1段", "part": "1/1"}
  ]
}
不要写 pages，不要 DELETE pages，不要 PATCH characters。

【自检】
运行 \`.claude/skills/story-breakdown/mapping_check.py --story-id ${storyId}\`：去掉标点和空白后，mapping 按页码拼接必须与 optimized_content 完全一致；不一致先修 mapping，再继续。

【输出要求】
1. 先输出「分镜对照表」：页码 / 原文位置 / 原文摘录 / 本页简述，按页码顺序完整列出。
2. 最后输出一句：\`对照表已写回工作台，请确认顺序；确认后复制「分镜头脚本指令」。\`
3. 停下来等我确认，不要继续生成脚本。
4. 只写 mapping；不要生成主旁白、副旁白、生图提示词。`
}

export interface ScriptPageTarget {
  /** 来源对照段号（mapping.page_number） */
  mappingPageNumber: number
  /** 实际脚本页码（成片顺序） */
  scriptPageNumber: number
}

export interface ScriptPagePlan {
  /** new：从空白生成；regenerate：覆盖已有脚本页；blocked：当前选段不能直接生成 */
  mode: 'new' | 'regenerate' | 'blocked'
  targets: ScriptPageTarget[]
  reason: string | null
}

/**
 * 计算选中的对照段会落到哪些脚本页。
 *
 * - 没有分镜页：按选中顺序连续编号 1..N，跳过的对照段不占号；
 * - 已有分镜页：通过 mapping_page_number 找到对应脚本页，只覆盖这些页，页码不变；
 * - 选中的段在现有脚本里没有对应页：必须清空脚本后重新生成，不能插入后重排。
 */
export function buildScriptPagePlan(
  selectedMappingPages: number[],
  pages: StoryboardPage[],
  mappingPageNumbers: number[] = [],
): ScriptPagePlan {
  const selected = Array.from(
    new Set(
      selectedMappingPages.filter(
        (pageNumber) => Number.isInteger(pageNumber) && pageNumber > 0,
      ),
    ),
  ).sort((left, right) => left - right)

  if (selected.length === 0) {
    return {
      mode: 'blocked',
      targets: [],
      reason: '请先在「分镜对照」里勾选至少一段',
    }
  }

  if (pages.length === 0) {
    return {
      mode: 'new',
      targets: selected.map((mappingPageNumber, index) => ({
        mappingPageNumber,
        scriptPageNumber: index + 1,
      })),
      reason: null,
    }
  }

  const sortedPageNumbers = pages
    .map((page) => page.page_number)
    .sort((left, right) => left - right)
  if (
    sortedPageNumbers.some(
      (pageNumber, index) => pageNumber !== index + 1,
    )
  ) {
    return {
      mode: 'blocked',
      targets: [],
      reason: `现有脚本页码不连续（${sortedPageNumbers.join(
        '、',
      )}），可能删过页。请先清空分镜脚本再重新生成。`,
    }
  }

  if (mappingPageNumbers.length > 0) {
    const validMappingNumbers = new Set(mappingPageNumbers)
    const unknownSelected = selected.filter(
      (mappingPageNumber) => !validMappingNumbers.has(mappingPageNumber),
    )
    if (unknownSelected.length > 0) {
      return {
        mode: 'blocked',
        targets: [],
        reason: `选中的对照第 ${unknownSelected.join(
          '、',
        )} 段已不在当前对照表，请刷新后重新选择。`,
      }
    }
    const stalePages = pages.filter(
      (page) =>
        page.mapping_page_number != null &&
        !validMappingNumbers.has(page.mapping_page_number),
    )
    if (stalePages.length > 0) {
      return {
        mode: 'blocked',
        targets: [],
        reason: `现有脚本引用了已不在当前对照表的段（脚本第 ${stalePages
          .map((page) => page.page_number)
          .join('、')} 页），对照表可能已更新。请先清空分镜脚本再重新生成。`,
      }
    }
  }

  const scriptPageByMapping = new Map<number, number>()
  const pagesWithoutMapping: number[] = []
  for (const page of pages) {
    if (page.mapping_page_number == null) {
      pagesWithoutMapping.push(page.page_number)
      continue
    }
    scriptPageByMapping.set(page.mapping_page_number, page.page_number)
  }

  if (pagesWithoutMapping.length > 0) {
    return {
      mode: 'blocked',
      targets: [],
      reason: `现有分镜页缺少来源对照段（脚本第 ${pagesWithoutMapping.join(
        '、',
      )} 页），请先清空分镜脚本再重新生成。`,
    }
  }

  const missing = selected.filter(
    (mappingPageNumber) => !scriptPageByMapping.has(mappingPageNumber),
  )
  if (missing.length > 0) {
    return {
      mode: 'blocked',
      targets: selected
        .filter((mappingPageNumber) =>
          scriptPageByMapping.has(mappingPageNumber),
        )
        .map((mappingPageNumber) => ({
          mappingPageNumber,
          scriptPageNumber: scriptPageByMapping.get(mappingPageNumber)!,
        })),
      reason: `选中的对照第 ${missing.join(
        '、',
      )} 段在现有脚本中没有对应页。新增段会改变后续页码，请先清空分镜脚本再重新生成。`,
    }
  }

  return {
    mode: 'regenerate',
    targets: selected.map((mappingPageNumber) => ({
      mappingPageNumber,
      scriptPageNumber: scriptPageByMapping.get(mappingPageNumber)!,
    })),
    reason: null,
  }
}

/**
 * 第二步：读取已确认的分镜对照表，按选中的对照段生成分镜头脚本。
 *
 * mapping 页码只表示原文顺序；脚本页码按选中段连续编号（已有脚本时保持不变）。
 */
export function buildStoryScriptPrompt(
  storyId: number,
  pageNumbers: number[] = [],
  pages: StoryboardPage[] = [],
): string {
  const apiBase = resolveApiBase()
  const plan = buildScriptPagePlan(pageNumbers, pages)
  if (plan.mode === 'blocked') {
    return `请使用 ${STORY_BREAKDOWN_SKILL} 技能的「分镜头脚本」模式（.claude/skills/${STORY_BREAKDOWN_SKILL}/SKILL.md），读取故事 ID 为 ${storyId} 的分镜对照表。

【无法开始】
${plan.reason ?? '当前选段无法生成分镜脚本'}

不要写回任何分镜页，不要自行插入、重排或重新编号；先告诉我需要怎么处理。`
  }

  const targets = plan.targets
  const selected = targets.map((target) => target.mappingPageNumber)
  const sourceList = selected.join('、')
  const sourceCsv = selected.join(',')
  const scriptList = targets
    .map((target) => target.scriptPageNumber)
    .join('、')
  const targetText = targets
    .map(
      (target) =>
        `对照第${target.mappingPageNumber}段 → 脚本第${target.scriptPageNumber}页`,
    )
    .join('；')

  const isNew = plan.mode === 'new'
  const scopeRule = isNew
    ? `本次从空白生成：只处理 mapping 中 page_number 为 ${sourceList} 的 ${targets.length} 段，按它们在 mapping 中的先后顺序生成脚本第 ${scriptList} 页。脚本页码必须从 1 连续，不要沿用 mapping 页码；未选中的对照段跳过，不生成、不写回。对应关系：${targetText}。`
    : `现有脚本已有页面。本次只重新生成以下 ${targets.length} 页，脚本页码保持不变，不要重新编号：${targetText}。未列出的脚本页保留原样；未选中的对照段不处理。`

  const selfCheck = `本次目标：${targetText}。全局要求：pages 按 page_number 从 1 连续编号、无空号；每页必须有 mapping_page_number，且不重复、必须存在于 mapping。本次页 narration_main < 15 个汉字、narration_sub < 50 个汉字（标点不计）且最多 2 行；没有空字段。运行 \`.claude/skills/story-breakdown/script_check.py --story-id ${storyId} --mapping-pages ${sourceCsv}\`（分镜尚未写回时用 \`--input\` 传入本地 JSON），未通过不得写回。`

  const writeBack = isNew
    ? `2. DELETE \`${apiBase}/api/stories/${storyId}/breakdown/pages\` 清空旧页（没有旧页也执行一次，避免残留旧页码）。
3. 按对应关系逐页 PUT \`${apiBase}/api/stories/${storyId}/breakdown/pages/{脚本页码}\`，请求体写入全部字段，并包含 \`"mapping_page_number": 来源对照段号\`。`
    : `2. 只对本次目标脚本页码（${scriptList}）逐页 DELETE \`${apiBase}/api/stories/${storyId}/breakdown/pages/{脚本页码}\`；**不要 DELETE 全部 pages**，其他脚本页保持原样。
3. 逐页 PUT 同一个脚本页码，请求体写入全部字段，并包含 \`"mapping_page_number": 来源对照段号\`。`

  const pageStateCheck = isNew
    ? '本次预期 pages 为空。如果实际读取到已有 pages，立即停止，不要 DELETE /pages，先告诉我刷新页面后重试。'
    : `本次预期 pages 非空，目标脚本页为 ${scriptList}。先按每页的 mapping_page_number 核对；如果目标页不存在、或选中的对照段找不到对应脚本页，立即停止，告诉我先清空分镜脚本再重新生成；不要插入、不要重排、不要自行分配新页码。`

  return `请使用 ${STORY_BREAKDOWN_SKILL} 技能的「分镜头脚本」模式（.claude/skills/${STORY_BREAKDOWN_SKILL}/SKILL.md），读取故事 ID 为 ${storyId} 的现有分镜对照表（mapping），按选中的对照段生成分镜头脚本并写回工作台。不要重新拆页、不要重排、不要修改 mapping。

${COMMON_DATA_RULES(apiBase, storyId)}

【本次范围】
${scopeRule}

【前置检查】
1. 读取 breakdown 里的 mapping；如果 mapping 为空，停下来告诉我：先执行「分镜对照」，不要自己拆页。
2. ${pageStateCheck}
3. 读取 optimized_content、characters、art_style_name/content；画风为空或失效时停下来告诉我。
4. 如果 characters 为空，立即停止，告诉我先执行「角色卡」模式拆出全部角色卡；不要在这里临时拆卡，也不要生成分镜页。已有角色卡直接沿用，不要覆盖。

【逐页生成】
只处理本次范围内的 mapping 项，按对应关系逐页生成：
${targetText}
- mapping_page_number：写入本页来源的对照段号，必须与上面的对应关系一致。
- 脚本第 1 页是本次选中段中的第一段，不一定是 mapping 第 1 段；不生成钩子页。
- story_content：先写清楚本页故事内容，必须包含「谁 + 在哪 + 做了什么 + 结果/情绪」，可参考 mapping.summary 但不要只写一句空话；它是副旁白的底稿。
- narration_sub：以 story_content 为底稿写成画面文字，用主角第一人称，**不超过 50 个汉字（标点不计）**，允许 1–2 行（用换行符分行）；每页必须能独立看懂，保留姓名、时间、地点、关键动作和结果/情绪；需要承接上一页时可加半句，但不能只写半句。
- narration_main：本页内容的提炼标题，**不超过 15 个汉字（标点不计）**，要吸引人，不要独立发挥。
- narration_highlight：从主旁白或副旁白中选连续片段；没有就留空。
- 其余字段照旧：characters、character_review、scene、action_state、change_note、dialogues、shot_type、camera_angle、image_prompt。
- image_prompt 必须调用 \`POST ${apiBase}/api/settings/prompt-templates/render\`（template_type=body）生成；context 传 content（本页【画面】描述，含本页 1–3 个背景元素名与排除清单）、character_consistency、narration_main、narration_sub、narration_highlight、dialogues、page_number（章内页码）、chapter_number（本章章号）。角色外形用 {{角色名}} 变量；不要手写【画风】【文字区】【页码】【负面提示词】。

【写回】
1. 写回前自检：${selfCheck}
${writeBack}
4. 不要 PATCH optimized_content / mapping / characters；角色卡必须已在「角色卡」模式中拆好，已有角色卡不要覆盖。
5. 写回失败时重试 1 次；仍失败必须明确告诉我「结果仅在对话中，未能写入详情页」，不要静默忽略。

【输出要求】
1. 逐页完整输出本次范围内每页的全部条目，不要只给摘要。
2. 最后报告实际写入页数、每页「来源对照段 → 脚本页码」、跳过的对照段，以及每页字数自检结果。
3. 只输出文字脚本与生图提示词，不要实际生成图片，不要生成或管理参考垫图。`
}

export interface ChapterPageTarget {
  /** 来源对照段号 */
  mappingPageNumber: number
  /** 章内页码，图片里显示的「第X页」 */
  chapterPageNumber: number
  /** 全局页码，接口和图片文件使用的稳定编号 */
  pageNumber: number
}

/** 章节内每个对照段对应的章内页码 / 全局页码。 */
export function buildChapterPageTargets(
  chapterNumber: number,
  chapters: StoryboardChapterRead[],
): ChapterPageTarget[] {
  const ordered = [...chapters].sort(
    (left, right) => left.chapter_number - right.chapter_number,
  )
  const chapter = ordered.find(
    (item) => item.chapter_number === chapterNumber,
  )
  if (!chapter) return []
  const offset = ordered
    .filter((item) => item.chapter_number < chapterNumber)
    .reduce((sum, item) => sum + item.mapping_page_numbers.length, 0)
  return chapter.mapping_page_numbers.map(
    (mappingPageNumber, index) => ({
      mappingPageNumber,
      chapterPageNumber: index + 1,
      pageNumber: offset + index + 1,
    }),
  )
}

/**
 * 按章节生成正文脚本。
 *
 * 默认只补缺失页，已存在的页保留；force=true 时整章重做。
 * 全局页码由章节顺序唯一确定，章内页码另算，图片里只显示章内页码。
 */
export function buildChapterScriptPrompt(
  storyId: number,
  chapterNumber: number,
  chapters: StoryboardChapterRead[],
  pages: StoryboardPage[],
  force = false,
): string {
  const apiBase = resolveApiBase()
  const ordered = [...chapters].sort(
    (left, right) => left.chapter_number - right.chapter_number,
  )
  const chapter = ordered.find(
    (item) => item.chapter_number === chapterNumber,
  )
  if (!chapter) {
    return `故事 ${storyId} 没有第 ${chapterNumber} 章，请刷新后重新选择。`
  }

  const targets = buildChapterPageTargets(chapterNumber, ordered)
  const previousIncomplete = ordered
    .filter((item) => item.chapter_number < chapterNumber)
    .filter((item) => {
      const sourceSet = new Set(item.mapping_page_numbers)
      const doneSources = new Set(
        pages
          .filter(
            (page) =>
              page.mapping_page_number != null &&
              sourceSet.has(page.mapping_page_number) &&
              (page.chapter_number == null ||
                page.chapter_number === item.chapter_number),
          )
          .map((page) => page.mapping_page_number),
      )
      return item.mapping_page_numbers.some(
        (mappingNumber) => !doneSources.has(mappingNumber),
      )
    })
  if (previousIncomplete.length > 0) {
    return `请先生成第 ${previousIncomplete
      .map((item) => item.chapter_number)
      .join('、')} 章的正文页，再生成第 ${chapterNumber} 章；否则全局页码会出现空号。`
  }

  const mappingSet = new Set(chapter.mapping_page_numbers)
  const chapterPages = pages.filter(
    (page) =>
      page.chapter_number === chapterNumber ||
      (page.chapter_number == null &&
        page.mapping_page_number != null &&
        mappingSet.has(page.mapping_page_number)),
  )
  const invalidPages = chapterPages.filter(
    (page) => page.mapping_page_number == null,
  )
  if (invalidPages.length > 0) {
    return `第 ${chapterNumber} 章有页面缺少来源对照段（全局第 ${invalidPages
      .map((page) => page.page_number)
      .join('、')} 页），请先刷新或重新生成章节。`
  }

  const existingByMapping = new Map(
    chapterPages
      .filter((page) => page.mapping_page_number != null)
      .map((page) => [page.mapping_page_number as number, page]),
  )
  const mismatched = chapterPages.filter((page) => {
    const target = targets.find(
      (item) => item.mappingPageNumber === page.mapping_page_number,
    )
    return (
      !target ||
      page.page_number !== target.pageNumber ||
      (page.chapter_page_number != null &&
        page.chapter_page_number !== target.chapterPageNumber)
    )
  })
  if (mismatched.length > 0) {
    return `第 ${chapterNumber} 章已有页面的全局页码 / 章内页码与章节规划不一致（全局第 ${mismatched
      .map((page) => page.page_number)
      .join('、')} 页），请先刷新页面；仍不一致时清空本章页面后重生成。`
  }

  const pending = force
    ? targets
    : targets.filter(
        (target) => !existingByMapping.has(target.mappingPageNumber),
      )
  if (pending.length === 0) {
    return `第 ${chapterNumber} 章的 ${targets.length} 页正文已经全部生成，无需补页。\n\n如需整章重做，请使用「重新生成本章脚本」。`
  }

  const targetText = pending
    .map(
      (target) =>
        `第${chapter.chapter_number}章第${target.chapterPageNumber}页` +
        `（全局第${target.pageNumber}页）← 对照第${target.mappingPageNumber}段`,
    )
    .join('；')
  const existingText =
    chapterPages.length > 0
      ? chapterPages
          .sort((left, right) => left.page_number - right.page_number)
          .map(
            (page) =>
              `第${chapter.chapter_number}章第${
                page.chapter_page_number ?? '?'
              }页（全局第${page.page_number}页）← 对照第${
                page.mapping_page_number
              }段`,
          )
          .join('；')
      : '无'
  const pendingCsv = pending.map((target) => target.pageNumber).join(',')
  const scope = force
    ? `本次整章重做：覆盖第 ${chapterNumber} 章全部 ${targets.length} 页正文，已存在的页会被重新生成。`
    : `本次只补第 ${chapterNumber} 章缺失的 ${pending.length} 页正文；已存在的 ${chapterPages.length} 页保留，不要覆盖。`

  return `请使用 ${STORY_BREAKDOWN_SKILL} 技能的「章节正文脚本」模式（.claude/skills/${STORY_BREAKDOWN_SKILL}/SKILL.md），为故事 ID ${storyId} 的第 ${chapterNumber} 章生成正文分镜并写回。不要重新拆页、不要重排、不要修改 mapping，也不要动其他章节。

${COMMON_DATA_RULES(apiBase, storyId)}

【本章信息】
- 章节：第${chapter.chapter_number}章《${chapter.title}》
- 正文页数：${targets.length} / 16（另加 1 封面 + 1 引导卡，总计 ${
    targets.length + 2
  } 张，必须 ≤ 18）
- 对照段：${chapter.mapping_page_numbers.join('、')}
- ${scope}

【页码规则】
- 章内页码从 1 开始：图片【页码】写「第${targets[0]?.chapterPageNumber ?? 1}页」这种章内页码，不写全局页码；
- 全局页码只用于接口 URL 和图片文件，读者看不到；
- 封面和引导卡不显示页码，不在本次正文生成范围内。

【本次目标】
${targetText}

【已有页面（保留）】
${existingText}

【前置检查】
1. 读取 breakdown 的 mapping、chapters、pages；如果章节或对照段与上面不一致，立即停止并告诉我刷新。
2. 检查每页的 mapping_page_number / chapter_number / chapter_page_number；不一致时不要写回。
3. 如果 characters 为空，立即停止，告诉我先执行「角色卡」模式拆出全部角色卡；不要在这里临时拆卡，也不要生成正文页。已有角色卡直接沿用，不要覆盖。
4. 画风为空或失效时停止。

【逐页生成】
按目标列表逐页生成，每页的 source_text 取对应 mapping 段：
- 每页 PUT 请求体必须包含 chapter_number=${chapter.chapter_number}、chapter_page_number（章内页码）、mapping_page_number（来源对照段号）。
- 其余字段照旧：story_content、characters、character_review、scene、action_state、change_note、narration_main、narration_highlight、narration_sub、dialogues、shot_type、camera_angle、image_prompt。
- story_content：先写清楚本页故事内容，必须包含「谁 + 在哪 + 做了什么 + 结果/情绪」，它是副旁白的底稿。
- narration_sub：以 story_content 为底稿写成画面文字，用主角第一人称，**< 50 个汉字（标点不计）**，允许 1–2 行（用换行符分行）；每页必须能独立看懂，保留姓名、地点、关键动作和结果/情绪；需要承接上一页时可加半句，但不能只写半句。
- narration_main < 15 个汉字、narration_sub < 50 个汉字（标点不计），且不超过 2 行。
- 旁白禁用第三人称代词「他/她」（「其他」「吉他」除外），一律用角色姓名或「我」；已生图的旧页不改文字，只约束还没生图的新页。
- 冲击层：按 SKILL 的「冲击层」评分卡判断；只在爆点 / 情绪高潮 / 反转且 ≥3 分时，在 image_prompt 增加【冲击层】分块；单章最多 2 页、不得相邻、回忆页优先不用；storyboard-director 会在生成后复核。冲击线只做局部强调，不改变背景环境亮度；冷调、夜景、回忆页可以降亮度，但必须保留可识别场景，不得压成纯黑；夜景用淡灰或浅灰蓝表现，暗部用中灰过渡，室内夜景保留暖光；负面词要包含「纯黑背景」。
- image_prompt 必须调用 \`POST ${apiBase}/api/settings/prompt-templates/render\`（template_type=body）生成；context 传 content（本页【画面】描述，含本页 1–3 个背景元素名与排除清单）、character_consistency、narration_main、narration_sub、narration_highlight、dialogues、page_number（章内页码）、chapter_number（本章章号）。角色外形用 {{角色名}} 变量；不要手写【画风】【文字区】【页码】【负面提示词】。
- 如果该页需要冲击层，在 render 返回的 prompt 末尾追加【冲击层】分块；模板不负责正文冲击层。

【写回】
1. 写回前自检：运行 \`.claude/skills/story-breakdown/script_check.py --story-id ${storyId} --chapter ${chapterNumber}\`（分镜尚未写回时用 \`--input\` 传入本地 JSON，JSON 必须包含本章全部正文页，包括保留的已有页），未通过不得写回。
2. 只对本次目标全局页码逐页 DELETE \`${apiBase}/api/stories/${storyId}/breakdown/pages/{全局页码}\`（目标页码：${pendingCsv}）；**不要 DELETE 全部 pages**，不要动其他章节。
3. 逐页 PUT \`${apiBase}/api/stories/${storyId}/breakdown/pages/{全局页码}\`，写入目标页全部字段与章节字段。
4. 不要 PATCH optimized_content / mapping / chapters / characters；角色卡必须已在「角色卡」模式中拆好，已有角色卡不要覆盖。

【生成后自动审片】
写回完成后不要停，按以下顺序继续：
1. 运行 \`.claude/skills/story-breakdown/script_check.py --story-id ${storyId} --chapter ${chapterNumber}\`，确认通过。
2. 并行调用两个只读 agent：
   - narration-editor：审本章主旁白、副旁白、标红、台词、连读；
   - storyboard-director：审本章节奏、机位、连续性、图文一致。
   如果当前会话没有加载这两个 agent，按 \`.claude/agents/narration-editor.md\` / \`.claude/agents/storyboard-director.md\` 的说明用通用子代理执行。
3. 汇总成问题清单：页码、问题类型、严重程度、证据、修改建议；不要自动修改 pages，等我确认。
4. 最后输出：硬检查结果、旁白问题、分镜问题、建议先修哪几页。

【输出要求】
1. 逐页完整输出本次目标页的全部条目，不要只给摘要。
2. 最后报告写入页数、每页「章节页 → 全局页 → 对照段」、保留的页和字数自检结果。
3. 只输出文字脚本与生图提示词，不要实际生成图片。
4. 附上自动审片汇总。`
}

/** 章节规划：把连续 mapping 切成一篇篇小红书笔记。 */
export function buildChapterPlanPrompt(storyId: number): string {
  const apiBase = resolveApiBase()
  return `请使用 ${STORY_BREAKDOWN_SKILL} 技能的「章节规划」模式（.claude/skills/${STORY_BREAKDOWN_SKILL}/SKILL.md），为故事 ID ${storyId} 规划章节发布分组，并写回 chapters。不要生成正文脚本，不要修改 mapping、pages、characters。

${COMMON_DATA_RULES(apiBase, storyId)}

【硬规则】
1. 一章 = 一篇小红书笔记，最多 18 张图 = 1 张章节封面 + 1..16 张正文 + 1 张引导卡。
2. 按剧情钩子切章，不要按 16 页硬切；每章正文尽量 14–16 页，结尾停在悬念、反转或冲突升级处。超过 16 页必须继续拆；少于 14 页可以接受。
3. 所有未弃用（excluded=false）的 mapping 段必须按对照表顺序分配到章节，不重不漏；excluded=true 的段跳过。
4. chapter_number 从 1 连续编号；title 简洁、有吸引力，<=50 字。
5. cover 文字：
   - label：\`第X章 · 标题\`；
   - narration_main：主旁白，≤12 个汉字，必须是钩子；字多时先缩短文案，不压缩字号；
   - narration_highlight：从主旁白里选连续片段作为标红词；
   - narration_sub：副旁白，<35 个汉字；第 1 章写 premise + 代价/悬念，第 2 章起写上一章未解决的后果，不写平铺直叙的前情提要；
   - image_prompt 先留空，之后单独生成。
6. guide 文字：
   - 非最后一章：text 由本章结尾钩子撰写，≤12 个汉字（标点不计），必须包含「关注我」，例如「关注我，看下一章反转」「关注我，别错过结局」；不得写死题材词，非重生文不得出现「重生」；sub_text=\`下一章：<下一章钩子>\`；
   - 最后一章：text=\`想看后续？来我主页\`，sub_text=\`关注我，不迷路\`；
   - image_prompt 先留空。
7. 正文页码按章内 1..N 计算；封面和引导卡不显示页码。

【写回】
PATCH \`${apiBase}/api/stories/${storyId}/breakdown\`，写入 chapters 数组；每章结构：
{
  "chapter_number": 1,
  "title": "如果一切能重来",
  "mapping_page_numbers": [1, 2, 3],
  "cover": {"label": "...", "narration_main": "...", "narration_highlight": "...", "narration_sub": "...", "image_prompt": ""},
  "guide": {"text": "...", "sub_text": "...", "image_prompt": ""}
}
不要写 pages，不要 PATCH mapping / characters / optimized_content。

【自检】
运行 \`.claude/skills/story-breakdown/chapter_check.py --story-id ${storyId}\`；章节覆盖、每章 18 张上限、封面文字字数、引导卡主文案未通过时先修，再继续。

【输出要求】
1. 先输出章节规划表：章节 / 对照段范围 / 正文页数 / 总图数 / 本章结尾钩子。
2. 写回成功后输出：\`章节规划已写回工作台，请确认后再生成正文、封面和引导卡。\`
3. 如果已有 pages，提醒我：章节划分变化后，旧正文页的章节字段可能失效，需要时先清空正文页再重新生成。
4. 如果 characters 为空，提醒我先执行「角色卡」模式；不要生成正文、封面或引导卡。
5. 停下来等我确认。`
}

/** 生成某一章的封面生图提示词并写回。 */
export function buildChapterCoverInstructionPrompt(
  storyId: number,
  chapterNumber: number,
  chapter: StoryboardChapterRead,
): string {
  const apiBase = resolveApiBase()
  return `请使用 ${STORY_BREAKDOWN_SKILL} 技能，为故事 ID ${storyId} 的第 ${chapterNumber} 章《${chapter.title}》生成「章节封面」的 3 个变体提示词。先不要写回，生成后给我看，等我选定再落库。

${COMMON_DATA_RULES(apiBase, storyId)}

【前置检查】
1. 读取 breakdown.characters；如果为空，立即停止，告诉我先执行「角色卡」模式拆出全部角色卡，不要生成封面提示词。
2. 封面只引用已登记的角色变量；不要写未登记角色，也不要临时拆卡。

【封面文字】
- 顶部小字：${chapter.cover.label}
- 主旁白：${chapter.cover.narration_main}
- 标红词：${chapter.cover.narration_highlight}
- 副旁白：${chapter.cover.narration_sub}

【封面文案前置】
1. 读取本章发文标题：GET \`${apiBase}/api/stories/${storyId}/post-config?chapter=${chapterNumber}\`。
2. 如果当前主标题还是章节规划时的默认值，或与发文标题明显不同钩子（例如发文写辞职/办公室恋情，封面写他记得我），立即停止，提醒我：先回工作台编辑章节，点「AI 生成封面文案（3 选 1）」选定并保存，再重新复制本指令；不要用旧文案直接出图。
3. 如果我明确说“文案已选好/已保存”，或封面主标题与发文标题同钩子，才继续生成 3 个画面变体。

【封面点击钩子】
0. 先读封面主标题和副标题，提炼出这一张的核心冲突（谁和谁、什么禁忌/代价/信息差），再决定关键道具、场景和表情。画面必须和封面文字讲同一个钩子，不能沿用与标题无关的旧场景（例如标题写辞职/办公室恋情，画面却是咖啡/表扬）。
1. 必须生成 3 个不同钩子的变体：
   - A 道具特写：关键道具占前景约 1/3，人物表情在中景。
   - B 真相揭示：X 光屏、手机屏幕、文件等揭示关键信息，人物反应在旁。
   - C 面对面强化：低机位近距离双人，表情张力最大化，关键道具在两人之间。
2. 每个变体必须包含：
   - 1 个关键道具：警报按钮、X 光屏、车票、离婚协议、治疗单等，放在前景或视觉中心。
   - 1 个强表情：眼神锋利、含泪、挑衅、惊恐、下颌绷紧；禁止「神情沉静」「安静而紧绷」「氛围紧张而克制」。
   - 封面模式：统一走「原画风 + 封面专用冲击层」；背景只留淡线提示、不得压成纯黑；人物周围加入漫画黑色震动短线、放射状集中冲击线、锯齿情绪漫符；夸张表情、动态张力、手绘涂鸦感；冲击线和关键轮廓用较粗的黑色手绘线，人物面部与皮肤仍保持淡色铅笔的柔和质感，不做全图粗黑描边；不整体提高对比度、不压暗背景。
   - 冲击层最低力度：至少 3 条粗黑集中的手绘射线，线条有手绘抖动感，不是细线、不是均匀速度线；至少 2 处尺寸清晰可辨的锯齿情绪漫符，不是小点。
   - 线条 choreography：每个变体必须在 \`content\` 里写清冲击线从哪个关键道具/动作/视线出发、朝哪个方向、密度多少（少量/只围绕谁/不铺满）、哪些区域不能进（脸、眼睛、文字、关键道具轮廓）；线要跟构图和动作走，不能随机贴边。
   - 背景：浅米色素描纸底，与顶部文字带同色；只保留 1–3 个点明地点与动作的关键环境元素，用浅棕褐色淡铅笔线轮廓勾出；其余元素逐项写「没有 X、没有 Y」；不压暗、不发黑、无暗部；**人物/道具周围的冲击线不算背景装饰，不得删除或减弱**。\`content\` 只填本页元素名和排除清单，背景通用标准由全局规则注入，不要整段复述背景模板。
   - 副标题：<35 个汉字，写代价/反差/信息差。如果当前副旁白是前情说明，先给 2 个悬念改写选项，不要直接改。
   - 文字区：顶部小字、主旁白 ≤12 字大号红黑、单行尽量占上部 60%–75% 宽度、主副标题至少留半个字高、标红内嵌、副旁白小字且字号不超过主标题 45%；主标题不被人物/道具/背景线遮挡；不显示页码。
3. 禁止：低饱和淡雅、柔和暖光直接套封面；双人全身、脸太小；表情平静克制；没有关键道具；主标题字号偏小、排版拥挤；背景铺满场景、出现氛围人群或压暗；冲击线偏细、均匀得像速度线；锯齿漫符少于 2 处或小到看不清；冲击线随机贴边、铺满全图、糊成脏线或像贴图；涂鸦/冲击线遮挡脸、眼睛、文字或关键道具轮廓。
4. 每个变体生成后，必须调用 \`POST ${apiBase}/api/settings/prompt-templates/render\`：
   - template_type：\`cover\`；
   - story_id：\`${storyId}\`；
   - context：\`content\`（本变体【画面】描述，必须包含冲击线起点/方向/密度/保护区，以及本页 1–3 个背景元素名与排除清单）、\`character_consistency\`、\`narration_main\`、\`narration_sub\`、\`narration_highlight\`、\`label\`、\`chapter_number\`（本章章号）；
   - 用返回的 \`prompt\` 作为该变体完整提示词；把返回的 \`applied_rules\` 和 \`rule_checks\` 一并交给封面导演审片；\`rule_checks\` 有 failed 时先修画面描述再重新 render；不要手写【画风】【文字区】【封面模式】【负面提示词】。
5. 3 个变体只改变 \`content\` 里的构图、机位、道具、表情和线条起点/方向；其他文字字段保持一致。

【生成后自动审片】
1. 运行 \`cover-director\` 的 prompt 模式：读取 \`.claude/agents/cover-director.md\`，按 3 秒抓眼、情绪强度、悬念、色彩对比、关键道具、文字可读性、画风一致性评分。
2. 通过线：3 秒抓眼、情绪强度、悬念均 ≥4，总分 ≥26/35；任一维度 <3 不通过。额外硬门槛：冲击层贴合度 1–5 分，<3 不通过（线是否从关键道具/动作/视线出发、方向是否服务构图、密度是否局部、脸和皮肤是否柔和、是否遮脸/眼睛/文字、是否达到至少 3 条粗黑射线 + 手绘抖动 + 至少 2 处可辨锯齿漫符）。
3. 输出 3 个变体的评分表、冲击层贴合度、推荐变体、每个不通过变体的具体改法。
4. 停下来等我选定，不要写回。

【写回（我选定后）】
1. 读取 breakdown.chapters，只修改第 ${chapterNumber} 章的 cover.image_prompt；其他章节、其他字段原样保留。
2. 如果我同意副标题改写，一并更新 cover.narration_sub。
3. PATCH \`${apiBase}/api/stories/${storyId}/breakdown\`，写入完整 chapters 数组。
4. 运行 \`.claude/skills/story-breakdown/cover_check.py --story-id ${storyId} --chapter ${chapterNumber}\`。
5. 不要修改 mapping、pages、characters、optimized_content；输出最终变体、评分和写回结果。`
}

/** 生成某一章的引导卡生图提示词并写回。 */
export function buildChapterGuideInstructionPrompt(
  storyId: number,
  chapterNumber: number,
  chapter: StoryboardChapterRead,
): string {
  const apiBase = resolveApiBase()
  return `请使用 ${STORY_BREAKDOWN_SKILL} 技能，为故事 ID ${storyId} 的第 ${chapterNumber} 章《${chapter.title}》生成「章节引导卡」生图提示词，并写回 chapters[${chapterNumber - 1}].guide.image_prompt。

${COMMON_DATA_RULES(apiBase, storyId)}

【前置检查】
1. 读取 breakdown.characters；如果为空，立即停止，告诉我先执行「角色卡」模式拆出全部角色卡，不要生成引导卡提示词。
2. 引导卡只引用已登记的角色变量；不要写未登记角色，也不要临时拆卡。

【引导卡文字（必须逐字使用）】
- 主文案：${chapter.guide.text}
- 副文案：${chapter.guide.sub_text}
- 标红规则：主文案中包含「关注我」时，仅「关注我」3 个字必须红色手写加粗，并内嵌在主文案整句中；绝对禁止单独另起一行或做成第三块文字区。主文案不含「关注我」时全部文字保持黑色，不要把副文案中的「关注我」自动标红。

【画面要求】
1. 3:4 竖版，一整幅完整单画面，无边框、无分格、无标题框。
2. 故事主角出现在画面中，沿用该故事画风与角色设定；角色外形用 {{角色名}} 变量引用。
3. 引导卡是章节最后一张：构图简洁、留白充足，文字清晰可读，不要出现对话气泡。
4. 【文字区】主文案写大号手写体「${chapter.guide.text}」；若主文案包含「关注我」，仅这 3 个字红色手写加粗并内嵌在整句中，其余文字保持黑色；副文案写较小手写体「${chapter.guide.sub_text}」；不要显示页码，不要出现其他文字、水印、logo。
5. 按技能规定输出【画风】【画面】【角色一致性】【画面形式】【文字区】【负面提示词】分类，不要写【页码】。

【写回】
1. 先读取 breakdown.chapters，只修改第 ${chapterNumber} 章的 guide.image_prompt，其他章节、其他字段原样保留。
2. PATCH \`${apiBase}/api/stories/${storyId}/breakdown\`，写入完整 chapters 数组。
3. 不要修改 mapping、pages、characters、optimized_content。
4. 输出完整引导卡提示词，并告诉我已写回。`
}

/**
 * 在「优化文 · 分镜对照」弹窗里按用户要求重写优化文，并重新生成对照表。
 *
 * 只改 optimized_content 与 mapping，不动 pages / characters；
 * 改写后必须重新拆 mapping，否则页码会和正文对不上。
 */
export function buildOptimizeArticlePrompt(
  storyId: number,
  requirement: string,
): string {
  const apiBase = resolveApiBase()
  const trimmed = requirement.trim()
  return `请使用 ${STORY_BREAKDOWN_SKILL} 技能的规则，按下面的步骤对故事 ID 为 ${storyId} 的优化文做一次定向优化，并重新生成分镜对照表。不要走一次性拆解流程。

【我的优化要求】
${trimmed}

【数据获取】
1. 调用 \`${apiBase}/api/stories/${storyId}\` 读取 name、content、art_style_name、art_style_content。
2. 调用 \`${apiBase}/api/stories/${storyId}/breakdown\` 读取当前 optimized_content、characters、mapping、pages。
3. 以当前 optimized_content 为基础改写；不要从故事原文重新优化，除非我明确要求重新拆解。

【执行】
1. 按我的要求优化 optimized_content：不得改变故事事实、人物关系、时间线、结局；保留第一人称口吻；不删情节、不合并信息点；优化后仍要能追溯到原文。
2. PATCH \`${apiBase}/api/stories/${storyId}/breakdown\` 写回新的 optimized_content。
3. 按新的 optimized_content 重新生成 mapping：严格按原文顺序切成镜头段落；不重排、不去重、不跳段、不合并跨段事件；一个自然段太长就拆，短段落不合并；单独成行的章节编号（1/2/3…）并入相邻页；每页 source_text 必须是原文连续摘录，不改写。尽量保留原有 excluded 弃用标记；无法对应时先问我。
4. PATCH \`${apiBase}/api/stories/${storyId}/breakdown\` 写回新的 mapping。如果已有 chapters 且新 mapping 无法沿用现有章节（段数/顺序/弃用段变化），**不要强行写回**，先停下来告诉我需要重新规划章节。
5. 运行 \`.claude/skills/story-breakdown/mapping_check.py --story-id ${storyId}\`：去掉标点和空白后，mapping 按页码拼接必须与新的 optimized_content 完全一致；不一致先修。
6. 不要改 chapters、pages、characters、画风；不要生成分镜头脚本；不要 DELETE pages。
7. 输出：改了哪些地方、新优化文字数、新对照表页数；如果已有分镜页或章节，提醒我对照表已变化，需要时先清空分镜脚本并重新规划章节。停下来等我确认，不要继续生成脚本。`
}

/**
 * @deprecated 新流程使用 buildStoryMappingPrompt / buildStoryScriptPrompt。
 * 保留旧导出，避免其他调用方报错。
 */
export function buildStoryBreakdownPrompt(storyId: number): string {
  return buildStoryMappingPrompt(storyId)
}
