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
 * 顶部预留…文字区域：上方大字体主要旁白「…」，中间红色加粗关键词「…」，
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
  if (keyword) lines.push(`中间红色加粗关键词：「${keyword[1]}」`)
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

/** 把提示词解析为分类列表，供详情页分块展示。 */
export function parseImagePrompt(prompt: string): PromptSection[] {
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

  return sections.map((section) =>
    section.label === '文字区'
      ? { ...section, text: formatTextArea(section.text) }
      : section,
  )
}

/** 复制给生图 AI 的文本：按【分类】分段换行。 */
export function formatImagePrompt(prompt: string): string {
  return parseImagePrompt(prompt)
    .map((section) => `【${section.label}】${section.text}`)
    .join('\n\n')
}
