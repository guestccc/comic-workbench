/**
 * 生图前置提示词拼接。
 *
 * 前置提示词是全局规则（所有故事共用），复制角色卡变量时拼在最前面，
 * 用于在生图 AI 的新会话里一次性交代角色与画面规则；分镜单页提示词
 * 复用会话上下文，不再重复拼接。规则里的 {art_style_name} 按当前
 * 故事的画风名称替换，与启动提示词的变量语义保持一致。
 */
export function withImagePrefix(
  prefix: string,
  artStyleName: string | null | undefined,
  text: string,
): string {
  const rules = prefix.trim()
  if (!rules) return text

  const resolved = artStyleName
    ? rules.split('{art_style_name}').join(artStyleName)
    : rules
  return `${resolved}\n\n${text}`
}
