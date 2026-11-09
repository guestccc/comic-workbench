import { describe, expect, it } from 'vitest'
import type { StoryboardChapterRead } from '../types'
import {
  buildChapterCoverInstructionPrompt,
  buildChapterPlanPrompt,
} from './storyBreakdown'

describe('buildChapterPlanPrompt', () => {
  const prompt = buildChapterPlanPrompt(7)

  it('does not hardcode a genre-specific guide CTA', () => {
    expect(prompt).not.toContain('重生爽文')
    expect(prompt).not.toContain('看更多重生')
  })

  it('asks the guide CTA to follow the chapter hook', () => {
    expect(prompt).toContain('由本章结尾钩子撰写')
    expect(prompt).toContain('必须包含「关注我」')
    expect(prompt).toContain('不得写死题材词')
  })
})

describe('buildChapterCoverInstructionPrompt', () => {
  const chapter = {
    chapter_number: 1,
    title: '测试章节',
    mapping_page_numbers: [1],
    cover: {
      label: '第1章 · 测试章节',
      narration_main: '测试主标题',
      narration_highlight: '主标题',
      narration_sub: '测试副标题',
      image_prompt: '',
      image_url: null,
    },
    guide: { text: '', sub_text: '', image_prompt: '', image_url: null },
  } as unknown as StoryboardChapterRead
  const prompt = buildChapterCoverInstructionPrompt(7, 1, chapter)

  it('restores the story 4 cover block and material hierarchy', () => {
    expect(prompt).toContain('封面专用冲击层')
    expect(prompt).toContain('冲击线和关键轮廓用较粗的黑色手绘线')
    expect(prompt).toContain('人物面部与皮肤仍保持淡色铅笔的柔和质感')
    expect(prompt).toContain('不做全图粗黑描边')
  })

  it('requires line choreography and an impact fit gate', () => {
    expect(prompt).toContain('线条 choreography')
    expect(prompt).toContain('冲击线从哪个关键道具/动作/视线出发')
    expect(prompt).toContain('冲击层贴合度')
  })

  it('requires the minimum impact strength and paper background', () => {
    expect(prompt).toContain('至少 3 条粗黑集中的手绘射线')
    expect(prompt).toContain('手绘抖动')
    expect(prompt).toContain('至少 2 处尺寸清晰可辨的锯齿情绪漫符')
    expect(prompt).toContain('浅米色素描纸底')
    expect(prompt).toContain('背景元素名与排除清单')
  })
})
