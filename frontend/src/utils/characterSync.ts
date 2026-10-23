import type { CharacterSyncItem } from '../types'

/**
 * 用户在生图平台确认形象后，发送给平台的更新指令。
 * 平台会回复全部角色的 {{角色名}}：外形描述 文本块。
 */
export const CHARACTER_SYNC_INSTRUCTION =
  '更新角色卡，整合本次修改点，输出新版完整角色卡，用代码块发给我。'

/** 单个角色块：{{角色名}}：外形描述（外形可跨行，直到空行为止）。 */
const CARD_BLOCK_PATTERN = /^\s*\{\{([^{}]+)\}\}\s*[：:]\s*([\s\S]+)$/

/**
 * 解析生图平台回复的角色卡文本。
 *
 * 支持平台常用的代码围栏包裹；角色块之间用空行分隔。
 * 无法识别的块会被跳过，由调用方决定如何提示。
 */
export function parseCharacterCardsText(raw: string): {
  cards: CharacterSyncItem[]
  skippedBlocks: number
} {
  // 去掉 Markdown 代码围栏行（``` 或 ```text 等）
  const text = raw
    .split('\n')
    .filter((line) => !line.trim().startsWith('```'))
    .join('\n')

  const cards: CharacterSyncItem[] = []
  let skippedBlocks = 0

  for (const block of text.split(/\n\s*\n/)) {
    const trimmed = block.trim()
    if (!trimmed) continue

    const matched = CARD_BLOCK_PATTERN.exec(trimmed)
    if (!matched) {
      skippedBlocks += 1
      continue
    }

    const name = matched[1].trim()
    const appearance = matched[2].trim()
    if (!name || !appearance) {
      skippedBlocks += 1
      continue
    }
    cards.push({ name, appearance })
  }

  return { cards, skippedBlocks }
}
