import type { StoryboardPage } from '../types'

/**
 * 把分镜页对齐到优化文。
 *
 * 分镜的副旁白是优化文的逐页拆分，但可能有少量改写、标点差异或
 * 「（回忆）」前缀。这里用 12/8/6 字滑动窗口在优化文中找最靠前的
 * 命中片段，把每页映射回原文位置，供「分镜对照」视图按原文顺序展示。
 */

export interface PageTextBlock {
  /** 这段原文对应的页码；同一 offset 的多页会合并 */
  pageNumbers: number[]
  pageRoles: string[]
  mains: string[]
  text: string
}

export interface PageAlignment {
  blocks: PageTextBlock[]
  /** 没能在优化文中找到对应片段的分镜页 */
  unmapped: StoryboardPage[]
}

/** 标点、空白不参与匹配，避免「，」和「。」差异导致对不上。 */
const IGNORED_CHAR =
  /[\s，。！？；：、「」『』“”‘’（）()…—·,.!?;:]/

const IGNORED_CHARS =
  /[\s，。！？；：、「」『』“”‘’（）()…—·,.!?;:]/g

function normalizeWithMap(text: string): {
  normalized: string
  map: number[]
} {
  let normalized = ''
  const map: number[] = []

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (IGNORED_CHAR.test(char)) continue
    normalized += char
    map.push(index)
  }

  return { normalized, map }
}

function normalizeText(text: string): string {
  return text.replace(/（回忆）/g, '').replace(/（闪前）/g, '').replace(IGNORED_CHARS, '')
}

function buildGramIndex(
  normalized: string,
  size: number,
): Map<string, number[]> {
  const index = new Map<string, number[]>()

  for (let start = 0; start + size <= normalized.length; start += 1) {
    const gram = normalized.slice(start, start + size)
    const positions = index.get(gram)
    if (positions) {
      positions.push(start)
    } else {
      index.set(gram, [start])
    }
  }

  return index
}

/** 在页面文本里找第一个能在优化文中命中的 12/8/6 字窗口。 */
function findOffset(
  pageText: string,
  map: number[],
  indexes: Map<string, number[]>[],
  sizes: number[],
): number | null {
  const needle = normalizeText(pageText)

  for (let level = 0; level < sizes.length; level += 1) {
    const size = sizes[level]
    const index = indexes[level]
    if (needle.length < size) continue

    for (let start = 0; start + size <= needle.length; start += 1) {
      const positions = index.get(needle.slice(start, start + size))
      if (positions && positions.length > 0) {
        return map[positions[0]] ?? null
      }
    }
  }

  return null
}

export function alignPagesToText(
  text: string,
  pages: StoryboardPage[],
): PageAlignment {
  if (!text.trim() || pages.length === 0) {
    return { blocks: [], unmapped: [] }
  }

  const { normalized, map } = normalizeWithMap(text)
  const sizes = [12, 8, 6]
  const indexes = sizes.map((size) => buildGramIndex(normalized, size))

  const markers: { page: StoryboardPage; offset: number }[] = []
  const unmapped: StoryboardPage[] = []

  for (const page of pages) {
    const offset = findOffset(page.narration_sub, map, indexes, sizes)
    if (offset === null) {
      unmapped.push(page)
    } else {
      markers.push({ page, offset })
    }
  }

  markers.sort((left, right) => left.offset - right.offset)

  const groups: { offset: number; pages: StoryboardPage[] }[] = []
  for (const marker of markers) {
    const last = groups[groups.length - 1]
    if (last && last.offset === marker.offset) {
      last.pages.push(marker.page)
    } else {
      groups.push({ offset: marker.offset, pages: [marker.page] })
    }
  }

  const blocks: PageTextBlock[] = []
  let cursor = 0

  // 第一页之前若有原文，单独作为「开头」块展示
  if (groups.length > 0 && groups[0].offset > 0) {
    blocks.push({
      pageNumbers: [],
      pageRoles: [],
      mains: [],
      text: text.slice(0, groups[0].offset).trim(),
    })
    cursor = groups[0].offset
  }

  groups.forEach((group, index) => {
    const nextOffset =
      index + 1 < groups.length ? groups[index + 1].offset : text.length
    const start = Math.max(cursor, group.offset)
    const end = Math.max(start, nextOffset)
    cursor = end

    blocks.push({
      pageNumbers: group.pages.map((page) => page.page_number),
      pageRoles: group.pages.map((page) => page.page_role).filter(Boolean),
      mains: group.pages
        .map((page) => page.narration_main)
        .filter(Boolean),
      text: text.slice(start, end).trim(),
    })
  })

  return { blocks: blocks.filter((block) => block.text), unmapped }
}
