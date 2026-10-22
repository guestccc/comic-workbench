import type { ArtStyle } from '../types'

/** 启动提示词中的画风描述占位符 */
export const ART_STYLE_PLACEHOLDER = '{art_style}'

/** 启动提示词中的画风名称占位符 */
export const ART_STYLE_NAME_PLACEHOLDER = '{art_style_name}'

export interface PreparedPrompt {
  /** 替换变量后的文本 */
  text: string
  /** 提示词包含画风变量，但没有可替换的画风 */
  missingArtStyle: boolean
}

/**
 * 复制前处理启动提示词：把 {art_style} / {art_style_name} 分别替换为
 * 当前选用画风的描述 / 名称。未选用画风时保持原文并标记缺失，
 * 由调用方提示用户。
 */
export function preparePromptForCopy(
  prompt: string,
  styles: ArtStyle[],
  activeId: string | null,
): PreparedPrompt {
  const needsArtStyle =
    prompt.includes(ART_STYLE_PLACEHOLDER) ||
    prompt.includes(ART_STYLE_NAME_PLACEHOLDER)
  if (!needsArtStyle) {
    return { text: prompt, missingArtStyle: false }
  }

  const activeStyle = styles.find((style) => style.id === activeId)
  if (!activeStyle) {
    return { text: prompt, missingArtStyle: true }
  }

  return {
    text: prompt
      .split(ART_STYLE_PLACEHOLDER)
      .join(activeStyle.content)
      .split(ART_STYLE_NAME_PLACEHOLDER)
      .join(activeStyle.name),
    missingArtStyle: false,
  }
}
