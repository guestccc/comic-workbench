/**
 * 生图提示词排版。
 *
 * 提示词是给生图 AI 用的，但用户也需要看懂每一段在控制什么。
 * 这里把一整段提示词拆成「画风 / 画面 / 角色一致性 / 文字区 / 负面词」等
 * 分类，详情页按分类分块展示，复制时按分类换行输出。
 *
 * 兼容两种数据：
 * - 新拆解：技能按【分类】逐行写入；
 * - 旧拆解：一整段文本，按固定要素关键词切分。
 */
export interface PromptSection {
  label: string
  text: string
}

/** 旁白三字段：标红词必须内嵌在它所在的那一句里，不能单独成行。 */
export interface NarrationFields {
  main: string
  highlight?: string
  sub: string
}

/** 标红词在旁白中的位置；找不到时为 null。 */
export interface HighlightLocation {
  block: 'main' | 'sub'
  position: '句首' | '句中' | '句尾' | '整句'
}

/** 解析 / 复制提示词时可补充的上下文。 */
export interface ImagePromptContext {
  dialogues?: string[]
  cameraAngle?: string
  narration?: NarrationFields
  /** 当前脚本页码：用于把旧提示词里写死的「第X页」改成重编号后的页码 */
  pageNumber?: number
}

/** 新格式允许的分类名，用于识别「画风：…」这类行首标签。 */
const KNOWN_LABELS = [
  '画风',
  '构图',
  '画面',
  '本页画面',
  '角色一致性',
  '画面形式',
  '文字区',
  '页码',
  '风格禁区',
  '负面提示词',
]

/** 旧格式的分段关键词；keepMarker 表示该关键词本身属于正文。 */
const LEGACY_MARKERS: {
  marker: string
  label: string
  keepMarker: boolean
}[] = [
  { marker: '本页画面：', label: '画面', keepMarker: false },
  { marker: '人物外形、', label: '角色一致性', keepMarker: true },
  { marker: '画面完全无边框', label: '画面形式', keepMarker: true },
  { marker: '顶部预留', label: '文字区', keepMarker: true },
  { marker: '画面左下角', label: '页码', keepMarker: true },
  { marker: '负面提示词：', label: '负面提示词', keepMarker: false },
]

/** 解析【分类】或「分类：」开头的多行提示词。 */
function parseLabeledPrompt(prompt: string): PromptSection[] | null {
  const sections: PromptSection[] = []

  for (const line of prompt.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed) continue

    const bracket = trimmed.match(/^【([^】]{1,10})】\s*(.*)$/)
    const colon = trimmed.match(/^([^：:]{1,10})[：:]\s*(.+)$/)
    const label = bracket?.[1] ?? (colon?.[1] ?? '')
    const isKnown = KNOWN_LABELS.includes(label)

    if (isKnown) {
      sections.push({
        label,
        text: (bracket?.[2] ?? colon?.[2] ?? '').trim(),
      })
    } else if (sections.length > 0) {
      // 没有标签的续行归入上一个分类，避免把长句拆散
      sections[sections.length - 1].text += `\n${trimmed}`
    } else {
      sections.push({ label: '完整提示词', text: trimmed })
    }
  }

  return sections.length > 0 ? sections : null
}

/** 文字区固定顶部说明：标红内嵌在旁白行内，不再单独描述文字块数量。 */
const TEXT_AREA_TOP =
  '顶部留白：画面上方预留大面积纯净白色留白（不铺纸纹、无泛黄底色）。'

/** 旧提示词里文字区的小标题；用于把一个字段截到下一个字段之前。 */
const TEXT_AREA_LABELS =
  '(?:顶部留白|主要旁白|主旁白|旁白字体加红加粗|标红关键词|副旁白|对话气泡|明确禁止|绝对禁止)'

const MAIN_NARRATION_LABEL = '(?:主要旁白|主旁白)'
const SUB_NARRATION_LABEL = '副旁白'
const HIGHLIGHT_LABEL = '(?:旁白字体加红加粗|标红关键词)'

const CHINESE_NUMERALS = [
  '零',
  '一',
  '二',
  '三',
  '四',
  '五',
  '六',
  '七',
  '八',
  '九',
  '十',
]

/** 去掉字段值两侧的引号与分隔符；保留句末标点，避免旁白丢句号。 */
function cleanFieldValue(raw: string): string {
  return raw
    .trim()
    .replace(/^[「『"]\s*/, '')
    .replace(/\s*[」』"]$/, '')
    .replace(/[；;，,\s]+$/, '')
}

/** 从旧文字区里按「标签：内容」截取一个字段。 */
function extractLabeledField(text: string, labelPattern: string): string | null {
  const matched = new RegExp(`${labelPattern}\\s*[：:]\\s*`).exec(text)
  if (!matched) return null

  const rest = text.slice(matched.index + matched[0].length)
  const next = new RegExp(
    `[；;\\n]?\\s*(?:[①②③④⑤⑥⑦⑧⑨⑩]\\s*)?${TEXT_AREA_LABELS}\\s*[：:]`,
  ).exec(rest)
  const raw = (next ? rest.slice(0, next.index) : rest).trim()
  return cleanFieldValue(raw)
}

/** 兼容「主要旁白「…」」这种标签后直接跟引号的旧写法。 */
function extractQuotedField(text: string, labelPattern: string): string | null {
  const matched = new RegExp(
    `${labelPattern}\\s*[：:]?\\s*「([^」]*)」`,
  ).exec(text)
  return matched ? cleanFieldValue(matched[1]) : null
}

/** 从旧提示词的文字区里识别旁白三字段；识别失败返回 null。 */
function extractLegacyNarration(text: string): NarrationFields | null {
  // 已经是新模板时原样保留，避免把主旁白 / 绝对禁止当成旧字段再切一次
  if (text.includes('绝对禁止：')) {
    return null
  }

  const main =
    extractLabeledField(text, MAIN_NARRATION_LABEL) ??
    extractQuotedField(text, MAIN_NARRATION_LABEL)
  const sub =
    extractLabeledField(text, SUB_NARRATION_LABEL) ??
    extractQuotedField(text, SUB_NARRATION_LABEL)
  if (!main || !sub) return null

  const highlight =
    extractLabeledField(text, HIGHLIGHT_LABEL) ??
    extractQuotedField(text, HIGHLIGHT_LABEL) ??
    ''
  return { main, sub, highlight }
}

/** 标红词在句中的位置描述。 */
function describePosition(
  index: number,
  length: number,
  total: number,
): HighlightLocation['position'] {
  if (index === 0 && length >= total) return '整句'
  if (index === 0) return '句首'
  if (index + length >= total) return '句尾'
  return '句中'
}

/** 标红词的字数描述，例如「二字」「3 个字」。 */
function characterCountLabel(count: number): string {
  return count >= 1 && count <= 10
    ? `${CHINESE_NUMERALS[count]}字`
    : `${count} 个字`
}

/** 标红词在同一句里出现的次数，用于提醒模型不要全部标红。 */
function countOccurrences(text: string, word: string): number {
  return word ? text.split(word).length - 1 : 0
}

/**
 * 定位标红关键词：先找主要旁白，再找副旁白。
 * 找不到时返回 null，生图提示词按「本页无红色文字」处理。
 */
export function locateNarrationHighlight(
  narration: NarrationFields,
): HighlightLocation | null {
  const highlight = (narration.highlight ?? '').trim()
  if (!highlight) return null

  const main = narration.main.trim()
  const sub = narration.sub.trim()
  const length = highlight.length

  const mainIndex = main.indexOf(highlight)
  if (mainIndex >= 0) {
    return {
      block: 'main',
      position: describePosition(mainIndex, length, main.length),
    }
  }

  const subIndex = sub.indexOf(highlight)
  if (subIndex >= 0) {
    return {
      block: 'sub',
      position: describePosition(subIndex, length, sub.length),
    }
  }

  return null
}

/**
 * 生成【文字区】正文。
 *
 * 顺序固定为「顶部留白 → 主旁白 →（绝对禁止）→ 副旁白 →（绝对禁止）→ 对话气泡」。
 * 绝对禁止紧跟标红所在的那一行；没有标红时放在副旁白之后。
 * 标红词必须内嵌在它所在的那一行，找不到时整页按全黑处理，
 * 绝不把不存在的词写进提示词。
 */
function buildNarrationTextArea(
  narration: NarrationFields,
  entries: DialogueEntry[],
): string {
  const main = narration.main.trim()
  const sub = narration.sub.trim()
  const highlight = (narration.highlight ?? '').trim()
  const location = locateNarrationHighlight(narration)
  const count = highlight ? characterCountLabel(highlight.length) : ''
  const lines: string[] = [TEXT_AREA_TOP]

  // 副旁白允许 1–2 行：换行符是给生图模型的排版信号，不能丢。
  const subLines = sub
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  const twoLineSub = subLines.length > 1
  const subInstruction = twoLineSub
    ? `写两行较小的黑色手写体：第一行「${subLines[0]}」，第二行「${subLines
        .slice(1)
        .join('')}」`
    : `写一行较小的黑色手写体「${sub}」`
  const subFidelity = twoLineSub
    ? '副旁白文字须按给出的两行逐字呈现、不得改写、不得合并成一行、不得替换姓名。'
    : '副旁白文字须逐字呈现、不得改写、不得按语义自行断行、不得替换姓名。'

  if (location?.block === 'main') {
    const repeat =
      countOccurrences(main, highlight) > 1
        ? '；文中其他位置的同一词同样保持黑色，不得标红'
        : ''
    lines.push(
      `主旁白：只写一行完整的黑色手写体「${main}」，其中仅${location.position}「${highlight}」${count}为红色手写加粗（红色、笔画比其余字粗），其余文字保持黑色不加粗${repeat}。`,
    )
    lines.push(
      `绝对禁止：不得在主旁白下方或任何位置单独另起一行书写「${highlight}」${count}，除主旁白外不得出现任何其他红色文字，这一行之下不再写第二行相同文字。`,
    )
  } else {
    lines.push(
      `主旁白：只写一行完整的黑色手写体「${main}」，全部文字保持黑色不加粗。`,
    )
  }

  if (location?.block === 'sub') {
    const repeat =
      countOccurrences(sub, highlight) > 1
        ? '；文中其他位置的同一词同样保持黑色，不得标红'
        : ''
    const highlightPlace = twoLineSub ? '' : location.position
    lines.push(
      `副旁白：紧接主旁白下方，${subInstruction}，其中仅${highlightPlace}「${highlight}」${count}为红色手写加粗（红色、笔画比其余字粗），其余文字保持黑色不加粗${repeat}；${subFidelity}`,
    )
    lines.push(
      `绝对禁止：不得在副旁白下方或任何位置单独另起一行书写「${highlight}」${count}，除副旁白外不得出现任何其他红色文字，这一行之下不再写第二行相同文字。`,
    )
  } else {
    lines.push(
      `副旁白：紧接主旁白下方，${subInstruction}，${subFidelity}`,
    )
  }

  if (!location) {
    lines.push(
      '绝对禁止：本页旁白文字全部保持黑色不加粗，不得出现任何红色文字，不得另起一行重复书写旁白中的任何文字。',
    )
  }

  if (entries.length > 0) lines.push(formatDialogueBlock(entries))

  return lines.join('\n')
}

/** 新生成的文字区优先，但保留旧文字的旁白字段作为兜底。 */
function resolveNarration(
  narration: NarrationFields | undefined,
  sections: PromptSection[],
): NarrationFields | null {
  if (narration?.main.trim() && narration.sub.trim()) {
    return {
      main: narration.main.trim(),
      sub: narration.sub.trim(),
      highlight: (narration.highlight ?? '').trim(),
    }
  }

  const textArea = sections.find((section) => section.label === '文字区')
  return textArea ? extractLegacyNarration(textArea.text) : null
}

/** 用新生成的文字区替换原分块；没有文字区时插在页码 / 负面词之前。 */
function replaceTextArea(
  sections: PromptSection[],
  text: string,
): PromptSection[] {
  const block: PromptSection = { label: '文字区', text }
  const index = sections.findIndex((section) => section.label === '文字区')
  if (index >= 0) {
    return sections.map((section, position) =>
      position === index ? block : section,
    )
  }

  const insertAt = sections.findIndex(
    (section) => section.label === '页码' || section.label === '负面提示词',
  )
  if (insertAt === -1) return [...sections, block]
  return [...sections.slice(0, insertAt), block, ...sections.slice(insertAt)]
}

/** 解析旧格式的一整段提示词：按固定关键词切成分类。 */
function parseLegacyPrompt(prompt: string): PromptSection[] | null {
  const firstIndex = prompt.indexOf(LEGACY_MARKERS[0].marker)
  if (firstIndex <= 0) return null

  const sections: PromptSection[] = []

  // 第一个关键词之前是画风；其中通常还混着构图与风格禁区
  const style = prompt.slice(0, firstIndex).trim()
  const compositionIndex = style.indexOf('3:4')
  const avoidIndex = style.indexOf('避免')
  const styleEnd = [compositionIndex, avoidIndex].filter(
    (index) => index > 0,
  )
  const styleCut = styleEnd.length > 0 ? Math.min(...styleEnd) : style.length
  if (styleCut > 0) {
    sections.push({ label: '画风', text: style.slice(0, styleCut).trim() })
  }
  if (compositionIndex > 0) {
    const compositionEnd =
      avoidIndex > compositionIndex ? avoidIndex : style.length
    sections.push({
      label: '构图',
      text: style.slice(compositionIndex, compositionEnd).trim(),
    })
  }
  if (avoidIndex > 0) {
    sections.push({ label: '风格禁区', text: style.slice(avoidIndex).trim() })
  }

  const positions = LEGACY_MARKERS.map((item) => ({
    ...item,
    index: prompt.indexOf(item.marker, firstIndex),
  })).filter((item) => item.index >= 0)

  positions.forEach((item, position) => {
    const next = positions[position + 1]
    const end = next ? next.index : prompt.length
    const raw = prompt.slice(item.index, end).trim()
    sections.push({
      label: item.label,
      text: item.keepMarker
        ? raw
        : raw.slice(item.marker.length).trim(),
    })
  })

  return sections.length > 0 ? sections : null
}

/**
 * 对话气泡的固定说明。
 *
 * 旧写法「对话气泡：我「台词」」会让生图 AI 把说话人姓名和「」一起画进气泡，
 * 因此新格式把「气泡文字」与「说话人 / 气泡位置」拆成字段，
 * 并明确告诉 AI：气泡里只出现台词本身。
 */
const DIALOGUE_NOTE =
  '气泡内只画台词文字本身，不画说话人姓名、引号、冒号、序号等任何标注'

/** 默认气泡位置：旧数据缺少位置描述时使用，与技能示例保持一致。 */
const DEFAULT_BUBBLE_POSITION = '其头侧，圆润手绘气泡描边'

interface DialogueEntry {
  /** 说话人，仅用于定位气泡，不写进画面 */
  speaker: string
  /** 气泡内唯一要画的台词文字 */
  text: string
  /** 气泡位置描述，例如「其头侧，圆润手绘气泡描边」 */
  position: string
}

/** 去掉位置描述首尾的连接符与句号。 */
function trimBubblePosition(raw: string): string {
  return raw
    .trim()
    .replace(/^[，,；;。：:\s]+/, '')
    .replace(/[，,；;。\s]+$/, '')
}

/** 解析脚本 dialogues 数组的一行：「说话人：台词」。 */
function parseDialogueLine(line: string): DialogueEntry | null {
  const value = line.trim()
  if (!value) return null

  const matched = value.match(/^([^：:「」]{1,16})[：:]\s*(.+)$/)
  if (matched) {
    return {
      speaker: matched[1].trim(),
      text: matched[2].trim(),
      position: DEFAULT_BUBBLE_POSITION,
    }
  }
  return { speaker: '', text: value, position: DEFAULT_BUBBLE_POSITION }
}

/** 解析旧提示词里的一条对话气泡：「说话人「台词」，位置」或「说话人：台词」。 */
function parsePromptDialogue(raw: string): DialogueEntry | null {
  const quoted = raw.match(/^(.{0,24}?)「([^」]+)」([\s\S]*)$/)
  if (quoted) {
    const position = trimBubblePosition(quoted[3]).replace(
      /^气泡(?:位于|在)?/,
      '',
    )
    return {
      speaker: quoted[1].trim(),
      text: quoted[2].trim(),
      position: position || DEFAULT_BUBBLE_POSITION,
    }
  }
  return parseDialogueLine(raw)
}

/** 把对话条目渲染成新的提示词写法。 */
function formatDialogueBlock(entries: DialogueEntry[]): string {
  const lines = entries.map((entry) => {
    const parts = [`气泡文字：${entry.text}`]
    if (entry.speaker) parts.push(`说话人：${entry.speaker}`)
    parts.push(`气泡位置：${entry.position || DEFAULT_BUBBLE_POSITION}`)
    return `- ${parts.join('｜')}`
  })
  return `对话气泡（${DIALOGUE_NOTE}）：\n${lines.join('\n')}`
}

/** 解析提示词里已有的对话气泡条目（兼容新旧两种写法）。 */
function parseDialogueEntries(text: string): DialogueEntry[] {
  const start = text.indexOf('对话气泡')
  if (start === -1) return []

  const tail = text.slice(start)
  const structured: DialogueEntry[] = []
  for (const matched of tail.matchAll(
    /气泡文字[：:]\s*([^｜|\n]+?)\s*(?:｜|\|)\s*说话人[：:]\s*([^｜|\n]*?)\s*(?:｜|\|)\s*气泡位置[：:]\s*([^\n]+)/g,
  )) {
    structured.push({
      text: matched[1].trim(),
      speaker: matched[2].trim(),
      position:
        trimBubblePosition(matched[3]) || DEFAULT_BUBBLE_POSITION,
    })
  }
  if (structured.length > 0) return structured

  // 旧写法：「对话气泡：说话人「台词」，位置」
  return tail
    .split(/对话气泡(?:（[^）]*）)?[：:]/)
    .slice(1)
    .map(parsePromptDialogue)
    .filter((entry): entry is DialogueEntry => entry !== null)
}

/** 提示词里的气泡位置优先；缺失条目用脚本 dialogues 补齐。 */
function collectDialogueEntries(
  text: string,
  dialogues: string[],
): DialogueEntry[] {
  const fromPrompt = parseDialogueEntries(text)
  const fromScript = dialogues
    .map(parseDialogueLine)
    .filter((entry): entry is DialogueEntry => entry !== null)

  if (fromPrompt.length === 0) return fromScript
  const entries = [...fromPrompt]
  for (let index = entries.length; index < fromScript.length; index += 1) {
    entries.push(fromScript[index])
  }
  return entries
}

/**
 * 把分块里旧的对话气泡改写成新格式，保留原有气泡位置。
 *
 * 返回 null 表示该分块没有对话气泡，无需处理；
 * 已含「气泡文字：」的说明是新格式，原样返回。
 */
function rewriteDialoguesInText(
  text: string,
  dialogues: string[],
): string | null {
  const start = text.indexOf('对话气泡')
  if (start === -1) return null
  if (text.includes('气泡文字：')) return text

  const prefix = text
    .slice(0, start)
    .trim()
    .replace(/[；;，,\s]+$/, '')
  const entries = collectDialogueEntries(text, dialogues)
  if (entries.length === 0) return prefix || null

  const block = formatDialogueBlock(entries)
  return prefix ? `${prefix}\n${block}` : block
}

/**
 * 把对话气泡规范化为新格式并注入解析结果。
 *
 * 兼容三类数据：
 * - 新拆解：已经是「气泡文字 / 说话人 / 气泡位置」格式，原样保留；
 * - 旧拆解：提示词里是「说话人「台词」，位置」，改写为新格式；
 * - 更旧的拆解：提示词完全没有对话气泡，用脚本 dialogues 补一段。
 */
function normalizeDialogues(
  sections: PromptSection[],
  dialogues: string[],
): PromptSection[] {
  let touched = false
  const updated = sections.map((section) => {
    const text = rewriteDialoguesInText(section.text, dialogues)
    if (text === null) return section
    touched = true
    return text === section.text ? section : { ...section, text }
  })
  if (touched) return updated

  const entries = dialogues
    .map(parseDialogueLine)
    .filter((entry): entry is DialogueEntry => entry !== null)
  if (entries.length === 0) return updated
  const block = formatDialogueBlock(entries)

  const textArea = updated.find((section) => section.label === '文字区')
  if (textArea) {
    return updated.map((section) =>
      section === textArea
        ? { ...section, text: `${section.text}\n${block}` }
        : section,
    )
  }

  const blockSection: PromptSection = { label: '对话气泡', text: block }
  const insertAt = updated.findIndex(
    (section) => section.label === '页码' || section.label === '负面提示词',
  )
  if (insertAt === -1) return [...updated, blockSection]
  return [
    ...updated.slice(0, insertAt),
    blockSection,
    ...updated.slice(insertAt),
  ]
}

/**
 * 把机位方位注入解析结果。
 *
 * camera_angle 是独立字段；旧拆解的 image_prompt 没有写机位（该字段是后加的），
 * 展示与复制前统一把机位补进提示词：优先并入【画面】分块，没有画面块时独立成块，
 * 插在【角色一致性】/【画面形式】之前。提示词已包含该机位文字（新拆解）时原样返回。
 */
function appendCameraAngle(
  sections: PromptSection[],
  prompt: string,
  cameraAngle: string,
): PromptSection[] {
  const angle = cameraAngle.trim()
  if (!angle || prompt.includes(angle)) return sections

  const line = `机位：${angle}`
  const scene = sections.find((section) => section.label === '画面')
  if (scene) {
    return sections.map((section) =>
      section === scene
        ? { ...section, text: `${section.text}\n${line}` }
        : section,
    )
  }

  const block: PromptSection = { label: '画面', text: line }
  const insertAt = sections.findIndex(
    (section) =>
      section.label === '角色一致性' || section.label === '画面形式',
  )
  if (insertAt === -1) return [...sections, block]
  return [...sections.slice(0, insertAt), block, ...sections.slice(insertAt)]
}

/**
 * 用当前脚本页码重写【页码】分块。
 *
 * 重新编号后，旧提示词里可能还写着「第8页」；展示和复制都以当前页码为准。
 * 没有页码分块时补一个标准分块，避免生图时漏页码。
 */
function rewritePageNumber(
  sections: PromptSection[],
  pageNumber: number | undefined,
): PromptSection[] {
  if (!pageNumber || pageNumber <= 0) return sections

  const index = sections.findIndex((section) => section.label === '页码')
  if (index >= 0) {
    const text = sections[index].text.replace(
      /第\s*\d+\s*页/g,
      `第${pageNumber}页`,
    )
    return sections.map((section, position) =>
      position === index ? { ...section, text } : section,
    )
  }

  const block: PromptSection = {
    label: '页码',
    text: `画面左下角放置小巧浅灰手写页码「第${pageNumber}页」，不遮挡人物与场景。`,
  }
  const insertAt = sections.findIndex(
    (section) => section.label === '负面提示词',
  )
  if (insertAt === -1) return [...sections, block]
  return [...sections.slice(0, insertAt), block, ...sections.slice(insertAt)]
}

/**
 * 把提示词解析为分类列表，供详情页分块展示。
 *
 * 只要拿到旁白三字段，就用它们整体重建【文字区】：
 * 标红词内嵌在所在的那一句里，旧提示词里的「旁白字体加红加粗」单独行会被丢弃。
 * 没有旁白字段时退回从旧文字区里识别；再失败则原样展示。
 * dialogues 用于补齐 / 规范对话气泡，cameraAngle 缺失时自动补上。
 */
export function parseImagePrompt(
  prompt: string,
  context: ImagePromptContext = {},
): PromptSection[] {
  if (!prompt.trim()) return []

  let sections: PromptSection[]
  if (prompt.includes('\n')) {
    sections = parseLabeledPrompt(prompt) ?? [
      { label: '完整提示词', text: prompt },
    ]
  } else {
    sections = parseLegacyPrompt(prompt) ?? [
      { label: '完整提示词', text: prompt },
    ]
  }

  const narration = resolveNarration(context.narration, sections)
  if (narration) {
    const existingText =
      sections.find((section) => section.label === '文字区')?.text ?? ''
    const entries = collectDialogueEntries(
      existingText,
      context.dialogues ?? [],
    )
    sections = replaceTextArea(
      sections,
      buildNarrationTextArea(narration, entries),
    )
  }

  return rewritePageNumber(
    normalizeDialogues(
      appendCameraAngle(sections, prompt, context.cameraAngle ?? ''),
      context.dialogues ?? [],
    ),
    context.pageNumber,
  )
}

/**
 * 复制给生图 AI 的文本：按【分类】分段换行。
 *
 * 首行固定为【第x页】，末行固定为「麻烦帮我生图」，
 * 生图 AI 据此识别页码并确认这是生图请求。
 *
 * 页码只从 context.pageNumber 读取，不再单独接收一个页码参数，
 * 避免展示用的是章内页码、复制时却传成全局页码。
 */
export function formatImagePrompt(
  prompt: string,
  context: ImagePromptContext = {},
): string {
  const body = parseImagePrompt(prompt, context)
    .map((section) => `【${section.label}】${section.text}`)
    .join('\n\n')
  const pageNumber = context.pageNumber
  const header = pageNumber ? `【第${pageNumber}页】\n\n` : ''
  return `${header}${body}\n\n麻烦帮我生图`
}
