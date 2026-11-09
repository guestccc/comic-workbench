import type { CharacterCard } from '../types'

/** 生图提示词中的角色变量写法，例如 {{我}}。 */
export function characterVariable(name: string): string {
  return `{{${name}}}`
}

/** 把后端返回的相对 asset_url 解析成当前页面下的绝对地址。 */
export function absoluteAssetUrl(assetUrl: string, origin: string): string {
  try {
    return new URL(assetUrl, origin).toString()
  } catch {
    return assetUrl
  }
}

/**
 * 可选的角色垫图分块。
 *
 * 只列已有 asset_url 的角色；没有资产图时返回空字符串，
 * 调用方据此保持原来的纯变量复制行为。
 */
export function buildCharacterReferenceBlock(
  characters: CharacterCard[],
  origin: string,
): string {
  const lines = characters
    .filter((card) => Boolean(card.asset_url))
    .map(
      (card) =>
        `${characterVariable(card.name)}：${absoluteAssetUrl(
          card.asset_url as string,
          origin,
        )}`,
    )
  return lines.length > 0 ? `【角色垫图】\n${lines.join('\n')}` : ''
}
