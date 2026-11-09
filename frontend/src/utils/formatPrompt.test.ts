import { describe, expect, it } from 'vitest'
import {
  formatImagePrompt,
  locateNarrationHighlight,
  type ImagePromptContext,
} from './formatPrompt'

const prompt = [
  '【画风】测试画风',
  '【画面】测试画面',
  '【文字区】旧文字区',
  '【页码】画面左下角放置「第18页」，不遮挡人物。',
  '【负面提示词】测试负面词。',
].join('\n')

const context: ImagePromptContext = {
  pageNumber: 1,
  cameraAngle: '正面平视',
  dialogues: [],
  narration: {
    main: '她摔了杯子',
    highlight: '摔',
    sub: '祝卿当场摔杯，说要分手。',
  },
}

describe('formatImagePrompt', () => {
  it('展示与复制都使用章内页码，不残留全局页码或对照段号', () => {
    const output = formatImagePrompt(prompt, context)
    expect(output).toContain('【第1页】')
    expect(output).toContain('「第1页」')
    expect(output).not.toContain('第17页')
    expect(output).not.toContain('第18页')
  })

  it('用结构化字段重建文字区', () => {
    const output = formatImagePrompt(prompt, context)
    expect(output).toContain('她摔了杯子')
    expect(output).toContain('祝卿当场摔杯，说要分手。')
    expect(output).not.toContain('旧文字区')
  })

  it('任意【标签】都保留为独立分块，不依赖白名单', () => {
    const customPrompt = [
      '【画风】测试画风',
      '【表情层】新增的自定义分块',
      '【页码】画面左下角放置「第4页」，不遮挡人物。',
      '【负面提示词】测试负面词。',
    ].join('\n')
    const output = formatImagePrompt(customPrompt, context)
    expect(output).toContain('【表情层】新增的自定义分块')
  })

  it('冲击层作为独立分块保留，不被并进文字区', () => {
    const impactPrompt = [
      '【画风】测试画风',
      '【画面】测试画面',
      '【文字区】旧文字区',
      '【冲击层】漫画黑色震动短线，只围绕手机屏幕。',
      '【页码】画面左下角放置「第4页」，不遮挡人物。',
      '【负面提示词】测试负面词。',
    ].join('\n')
    const output = formatImagePrompt(impactPrompt, context)
    expect(output).toContain('【冲击层】漫画黑色震动短线')
    expect(output.indexOf('【冲击层】')).toBeGreaterThan(
      output.indexOf('【文字区】'),
    )
    expect(output).not.toContain('旧文字区\n【冲击层】')
  })
})

describe('locateNarrationHighlight', () => {
  it('优先定位主旁白', () => {
    expect(locateNarrationHighlight(context.narration!)).toEqual({
      block: 'main',
      position: '句中',
    })
  })

  it('主旁白找不到时回退副旁白', () => {
    expect(
      locateNarrationHighlight({
        main: '别的句子',
        highlight: '摔杯',
        sub: '祝卿当场摔杯。',
      }),
    ).toEqual({ block: 'sub', position: '句中' })
  })
})
