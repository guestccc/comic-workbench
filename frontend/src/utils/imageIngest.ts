/** 生成「把成品图回传到工作台」的可复制指令，给生图 AI 直接执行。 */

export type ImageIngestTarget = 'page' | 'cover' | 'guide' | 'character_asset'

export interface ImageIngestContext {
  storyId: number
  storyName?: string | null
  target: ImageIngestTarget
  chapterNumber?: number | null
  chapterTitle?: string | null
  pageNumber?: number | null
  chapterPageNumber?: number | null
  /** 角色资产图：characters 数组下标，从 0 开始 */
  characterIndex?: number | null
  characterName?: string | null
}

const INGEST_BASE_URL = 'http://127.0.0.1:8123'
/** 与后端 MAX_BATCH_INGEST_ITEMS 保持一致 */
const BATCH_LIMIT = 20

function padded(value: number | null | undefined): string {
  return String(value ?? 0).padStart(4, '0')
}

function targetLabel(context: ImageIngestContext): string {
  const story = context.storyName?.trim() || `故事 ${context.storyId}`
  const chapter = context.chapterNumber
    ? `第${context.chapterNumber}章${
        context.chapterTitle ? `《${context.chapterTitle}》` : ''
      }`
    : ''
  if (context.target === 'page') {
    const local = context.chapterPageNumber
    const global = context.pageNumber
    return [story, chapter, `第${local ?? global}页（全局第${global}页）`]
      .filter(Boolean)
      .join(' · ')
  }
  if (context.target === 'character_asset') {
    const name = context.characterName?.trim()
    return [
      story,
      `角色资产图${name ? `：${name}` : ''}（索引 ${
        context.characterIndex ?? 0
      }）`,
    ].join(' · ')
  }
  return [story, chapter, context.target === 'cover' ? '章节封面' : '章节引导卡']
    .filter(Boolean)
    .join(' · ')
}

type PageIngestContext = ImageIngestContext & {
  target: 'page'
  pageNumber: number
}

function batchPageLabel(context: PageIngestContext): string {
  const chapter = context.chapterNumber
    ? `第${context.chapterNumber}章${
        context.chapterTitle ? `《${context.chapterTitle}》` : ''
      } · `
    : ''
  const local = context.chapterPageNumber ?? context.pageNumber
  return `${chapter}第${local}页（全局第${context.pageNumber}页）`
}

/**
 * 批量回传指令：多选页面时只生成一条批量接口指令。
 *
 * 后端一次最多接收 20 张，这里按 20 张自动分批发，避免生图 AI
 * 继续逐张调用单页接口。
 */
export function buildBatchImageIngestInstruction(
  contexts: ImageIngestContext[],
): string {
  const pages = contexts.filter(
    (context): context is PageIngestContext =>
      context.target === 'page' && typeof context.pageNumber === 'number',
  )
  if (pages.length === 0) return ''

  const storyId = pages[0].storyId
  const endpoint = `${INGEST_BASE_URL}/api/stories/${storyId}/breakdown/pages/images/ingest`
  const total = pages.length
  const batchCount = Math.ceil(total / BATCH_LIMIT)
  const legend = pages.map(
    (context, index) => `${index + 1}. ${batchPageLabel(context)}`,
  )
  const blocks: string[] = []

  for (let start = 0; start < total; start += BATCH_LIMIT) {
    const chunk = pages.slice(start, start + BATCH_LIMIT)
    const items = chunk.map((context) => ({
      page_number: context.pageNumber,
      image_url: `<第${context.pageNumber}页图片URL>`,
      filename: `page-${padded(context.pageNumber)}.png`,
    }))
    blocks.push(
      [
        `=== 第${Math.floor(start / BATCH_LIMIT) + 1}批 / 共${batchCount}批 · ${chunk.length}张 ===`,
        JSON.stringify({ items }, null, 2),
      ].join('\n'),
    )
  }

  return [
    `请把刚生成的 ${total} 张正文页图片回传到工作台。`,
    `接口：POST ${endpoint}`,
    'Content-Type: application/json',
    '',
    `限制：每批最多 ${BATCH_LIMIT} 张；单张 JPG/PNG/WebP，≤15MB；page_number 是全局页码，不是章内页码。`,
    `本次共 ${total} 张，分 ${batchCount} 批发送；每批只发一次 POST，不要逐张调单页接口。`,
    '',
    '生成顺序 → 回传页码：',
    ...legend,
    '',
    ...blocks.flatMap((block) => [block, '']),
    '每张图片生成后，把对应 item 的 image_url 换成真实图片 URL；',
    '如果只能传 base64，把该 item 的 image_url 改名为 image_base64，值为图片 base64（可带 data:image/png;base64, 前缀）。',
    '全部生成完后，对每批各发一次 POST。返回结果里的 items 会逐页标记 ok；',
    '只重试 ok=false 的页面，不要重复上传已经成功的页。',
  ].join('\n')
}

export interface CharacterAssetIngestTarget {
  /** characters 数组下标，从 0 开始 */
  index: number
  name: string
}

/**
 * 批量回传角色资产图：一次请求写入多个角色，逐项返回结果。
 * 角色卡最多 20 张，与后端批量上限一致。
 */
export function buildBatchCharacterAssetIngestInstruction(
  storyId: number,
  characters: CharacterAssetIngestTarget[],
  storyName?: string | null,
): string {
  if (characters.length === 0) return ''
  const endpoint = `${INGEST_BASE_URL}/api/stories/${storyId}/breakdown/characters/asset-images/ingest`
  const story = storyName?.trim() || `故事 ${storyId}`
  const items = characters.map((character) => ({
    character_index: character.index,
    image_url: `<角色「${character.name}」的图片URL>`,
    filename: `character-asset-${character.index}.png`,
  }))

  return [
    `请把刚生成的 ${characters.length} 张角色资产图回传到工作台。`,
    `接口：POST ${endpoint}`,
    'Content-Type: application/json',
    '',
    `限制：一次最多 ${BATCH_LIMIT} 张；单张 JPG/PNG/WebP，≤15MB；character_index 是 characters 数组下标，从 0 开始，不能重复。`,
    `本次共 ${characters.length} 张，发 1 次 POST。`,
    '',
    `目标：${story} · 角色资产图（${characters.length} 个角色）`,
    '角色 → 回传下标：',
    ...characters.map(
      (character, position) =>
        `${position + 1}. ${character.name}（索引 ${character.index}）`,
    ),
    '',
    JSON.stringify({ items }, null, 2),
    '',
    '每张图片生成后，把对应 item 的 image_url 换成真实图片 URL；',
    '如果只能传 base64，把 image_url 改名为 image_base64，值为图片 base64（可带 data:image/png;base64, 前缀）。',
    '返回 items 会逐项标记 ok；只重试 ok=false 的角色，不要重复上传已经成功的角色。',
  ].join('\n')
}

export function buildImageIngestInstruction(
  context: ImageIngestContext,
): string {
  const { storyId, target } = context
  const endpoint =
    target === 'page'
      ? `${INGEST_BASE_URL}/api/stories/${storyId}/breakdown/pages/${context.pageNumber}/image/ingest`
      : target === 'character_asset'
        ? `${INGEST_BASE_URL}/api/stories/${storyId}/breakdown/characters/${
            context.characterIndex ?? 0
          }/asset-image/ingest`
        : `${INGEST_BASE_URL}/api/stories/${storyId}/breakdown/chapters/${context.chapterNumber}/${target}/image/ingest`
  const filename =
    target === 'page'
      ? `page-${padded(context.pageNumber)}.png`
      : target === 'character_asset'
        ? `character-asset-${context.characterIndex ?? 0}.png`
        : `chapter-${context.chapterNumber}-${target}.png`
  const subject =
    target === 'character_asset' ? '角色资产图' : '图片'

  return [
    `请把刚生成的${subject}回传到工作台：`,
    `POST ${endpoint}`,
    'Content-Type: application/json',
    '',
    '二选一：',
    '{"image_url":"<把图片URL填这里>"}',
    `{"image_base64":"<把图片base64填这里>","filename":"${filename}"}`,
    '',
    `目标：${targetLabel(context)}`,
    ...(target === 'character_asset'
      ? [
          'character_index 是 characters 数组下标，从 0 开始；只更新这张角色卡的资产图，不会改角色名、身份或外形。',
        ]
      : []),
    '限制：JPG/PNG/WebP，≤15MB；同一目标重复回传会覆盖旧图。',
    '回传成功会返回图片地址；失败请按返回的错误信息处理，不要假装成功。',
  ].join('\n')
}
