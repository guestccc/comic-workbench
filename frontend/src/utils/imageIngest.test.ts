import { describe, expect, it } from 'vitest'

import {
  buildBatchCharacterAssetIngestInstruction,
  buildBatchImageIngestInstruction,
  buildImageIngestInstruction,
} from './imageIngest'

function contexts(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    storyId: 6,
    storyName: '测试故事',
    target: 'page' as const,
    chapterNumber: 1,
    chapterTitle: '第一章',
    pageNumber: index + 1,
    chapterPageNumber: index + 1,
  }))
}

describe('buildBatchImageIngestInstruction', () => {
  it('uses one batch endpoint instead of per-page endpoints', () => {
    const text = buildBatchImageIngestInstruction(contexts(2))
    expect(text).toContain('/breakdown/pages/images/ingest')
    expect(text).not.toContain('/pages/1/image/ingest')
    expect(text).toContain('"page_number": 1')
    expect(text).toContain('"page_number": 2')
  })

  it('splits more than 20 pages into multiple batches', () => {
    const text = buildBatchImageIngestInstruction(contexts(25))
    expect(text).toContain('第1批 / 共2批 · 20张')
    expect(text).toContain('第2批 / 共2批 · 5张')
    expect(text).toContain('"page_number": 25')
  })

  it('builds a character asset ingest instruction with character index', () => {
    const text = buildImageIngestInstruction({
      storyId: 9,
      storyName: '西游怪谈',
      target: 'character_asset',
      characterIndex: 2,
      characterName: '蒙水',
    })
    expect(text).toContain(
      '/api/stories/9/breakdown/characters/2/asset-image/ingest',
    )
    expect(text).toContain('角色资产图：蒙水（索引 2）')
    expect(text).toContain('character_index 是 characters 数组下标')
    expect(text).toContain('"filename":"character-asset-2.png"')
  })

  it('builds one batch character asset ingest instruction', () => {
    const text = buildBatchCharacterAssetIngestInstruction(
      9,
      [
        { index: 0, name: '我' },
        { index: 1, name: '师父' },
      ],
      '西游怪谈',
    )
    expect(text).toContain(
      '/api/stories/9/breakdown/characters/asset-images/ingest',
    )
    expect(text).toContain('"character_index": 0')
    expect(text).toContain('"character_index": 1')
    expect(text).toContain('我（索引 0）')
    expect(text).toContain('师父（索引 1）')
    expect(text).toContain('本次共 2 张，发 1 次 POST')
  })

  it('returns empty text when no page context is given', () => {
    expect(
      buildBatchImageIngestInstruction([
        {
          storyId: 6,
          target: 'cover',
          chapterNumber: 1,
        },
      ]),
    ).toBe('')
  })
})
