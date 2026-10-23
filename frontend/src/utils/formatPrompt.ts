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

/**
 * 把旧格式「文字区」的一长句拆成多行小标题。
 *
 * 旧数据形如：
 * 顶部预留…文字区域：上方大字体主要旁白「…」，旁白字体加红加粗「…」，
 * 下方小号字体副旁白「…」；文字留白区纯净无杂色底纹…
 *
 * 新数据本身已经按小标题分行，匹配不到「」引文时原样返回。
 */
function formatTextArea(text: string): string {
  const main = text.match(/主要旁白「([^」]*)」/)
  const keyword = text.match(/关键词「([^」]*)」/)
  const sub = text.match(/副旁白「([^」]*)」/)
  if (!main || !sub) return text

  const headerEnd = text.search(/上方大字体主要旁白|主要旁白「/)
  const header =
    headerEnd > 0 ? text.slice(0, headerEnd).trim().replace(/[：:]\s*$/, '') : ''
  const subEnd = (sub.index ?? 0) + sub[0].length
  const tail = text
    .slice(subEnd)
    .replace(/^[；;，,。\s]+/, '')
    .trim()

  const lines: string[] = []
  const intro = [header, tail].filter(Boolean).join('；')
  if (intro) lines.push(intro)
  lines.push(`主要旁白：「${main[1]}」`)
  if (keyword) lines.push(`旁白字体加红加粗：「${keyword[1]}」`)
  lines.push(`副旁白：「${sub[1]}」`)
  return lines.join('\n')
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
  const chunks = text.slice(start).split(/对话气泡[：:]/).slice(1)
  const fromPrompt = chunks
    .map(parsePromptDialogue)
    .filter((entry): entry is DialogueEntry => entry !== null)
  const fromScript = dialogues
    .map(parseDialogueLine)
    .filter((entry): entry is DialogueEntry => entry !== null)

  // 以提示词里的条目为准（保留手写的气泡位置），再用脚本 dialogues 补齐缺漏
  const entries = fromPrompt.length > 0 ? [...fromPrompt] : []
  for (let index = entries.length; index < fromScript.length; index += 1) {
    entries.push(fromScript[index])
  }
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
 * 把提示词解析为分类列表，供详情页分块展示。
 *
 * dialogues 传入脚本的对话气泡数组：旧拆解把说话人写进气泡时统一改写，
 * 提示词缺失对话气泡时自动补上；cameraAngle 缺失时同样自动补上。
 */
export function parseImagePrompt(
  prompt: string,
  dialogues: string[] = [],
  cameraAngle: string = '',
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

  const formatted = sections.map((section) =>
    section.label === '文字区'
      ? { ...section, text: formatTextArea(section.text) }
      : section,
  )
  return normalizeDialogues(
    appendCameraAngle(formatted, prompt, cameraAngle),
    dialogues,
  )
}

/**
 * 复制给生图 AI 的文本：按【分类】分段换行。
 *
 * 首行固定为【第x页】，末行固定为「麻烦帮我生图」，
 * 生图 AI 据此识别页码并确认这是生图请求。
 * dialogues / cameraAngle 同 parseImagePrompt，用于补齐旧拆解缺失的对话气泡与机位。
 */
export function formatImagePrompt(
  prompt: string,
  pageNumber: number,
  dialogues: string[] = [],
  cameraAngle: string = '',
): string {
  const body = parseImagePrompt(prompt, dialogues, cameraAngle)
    .map((section) => `【${section.label}】${section.text}`)
    .join('\n\n')
  return `【第${pageNumber}页】\n\n${body}\n\n麻烦帮我生图`
}
