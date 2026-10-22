/**
 * 复制文本到剪贴板。
 * 优先使用 Clipboard API；在非安全上下文或权限受限时，
 * 回退到隐藏 textarea + execCommand，保证本地 http 访问也能复制。
 */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // 继续走兜底方案
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.top = '-9999px'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  try {
    textarea.select()
    const copied = document.execCommand('copy')
    if (!copied) {
      throw new Error('execCommand copy returned false')
    }
  } finally {
    document.body.removeChild(textarea)
  }
}
