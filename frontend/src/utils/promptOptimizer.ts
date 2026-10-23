import type { PromptOptimizeMessage } from '../types'

export type ChatStatus = 'success' | 'updating' | 'error' | 'abort'

export interface ChatMessage {
  key: string
  role: 'user' | 'ai'
  content: string
  status: ChatStatus
}

/** 启动提示词优化的快捷指令，点击后直接发送。 */
export const PROMPT_QUICK_PROMPTS = [
  {
    key: 'structure',
    label: '让提示词更结构化',
    instruction:
      '请把当前启动提示词优化得更结构化，分点说明角色、画风、分镜、人物一致性和出图要求。',
  },
  {
    key: 'concise',
    label: '精简冗余表述',
    instruction:
      '请在保留所有有效规则和占位符的前提下，精简当前提示词中的冗余表述，让表达更清晰。',
  },
  {
    key: 'visual',
    label: '强化画风与镜头',
    instruction:
      '请强化当前提示词中的画面风格、分镜描述和镜头语言，让豆包生成各镜头时风格更统一。',
  },
  {
    key: 'consistency',
    label: '补充人物一致性',
    instruction:
      '请补充角色外貌、服装、发型等一致性约束，避免分镜之间人物走样。',
  },
  {
    key: 'placeholder',
    label: '保留变量占位符',
    instruction:
      '请检查并保留当前提示词中的所有变量占位符，同时让它们的使用方式更明确。',
  },
] as const

/** 画风描述优化的快捷指令。 */
export const ART_STYLE_QUICK_PROMPTS = [
  {
    key: 'texture',
    label: '强化线条与上色',
    instruction:
      '请强化线条、上色方式与材质质感的描述，让画风更明确、更容易复现。',
  },
  {
    key: 'lighting',
    label: '增加光影与氛围',
    instruction:
      '请补充光影、色调与整体氛围的描述，让画面更有感染力。',
  },
  {
    key: 'concise',
    label: '精简冗余表述',
    instruction:
      '请在保留全部风格特征的前提下精简冗余表述，让描述更紧凑。',
  },
  {
    key: 'doubao',
    label: '适配豆包生图',
    instruction:
      '请按豆包生图的偏好改写，补充构图、镜头语言与常见负面约束（如避免多余文字、肢体畸形）。',
  },
  {
    key: 'consistency',
    label: '强化多镜头一致性',
    instruction:
      '请补充角色与画面一致性的约束，让同一故事的各分镜保持统一画风。',
  },
] as const

/** 角色外形描述优化的快捷指令。 */
export const CHARACTER_QUICK_PROMPTS = [
  {
    key: 'sync',
    label: '同步生图平台的调整',
    instruction:
      '我在外部生图平台微调了这个角色的形象，请根据我接下来描述的变化更新外形描述：',
  },
  {
    key: 'posture',
    label: '补全体态与年龄感',
    instruction: '请补全这个角色的体态与年龄感描述，让跨镜头生图更稳定。',
  },
  {
    key: 'outfit',
    label: '只调整服装与配饰',
    instruction:
      '请在保持五官、发型、体态等其他特征不变的前提下，只调整服装与配饰。',
  },
  {
    key: 'face',
    label: '细化面部特征',
    instruction:
      '请把面部特征描述得更具体（眼型、眉形、唇形、肤色），便于保持跨镜头一致。',
  },
  {
    key: 'female',
    label: '按女性基准校正',
    instruction:
      '该角色为女性，请按工作台的女性基准校正描述：鹅蛋脸、五官柔和、自然女性曲线，避免男性化。',
  },
] as const

export type OptimizerMode = 'prompt' | 'art_style' | 'character'

export interface OptimizerQuickPrompt {
  key: string
  label: string
  instruction: string
}

/** 两种优化模式下的界面文案与快捷指令。 */
export interface OptimizerCopy {
  drawerTitle: string
  welcomeTitle: string
  welcomeDescription: string
  quickPrompts: readonly OptimizerQuickPrompt[]
  instructionPlaceholder: string
  emptyCurrentPlaceholder: string
  emptyCurrentWarning: string
  applySuccess: string
  footerNote: string
  /** AI 回复中代码块的标题 */
  codeBlockLabel: string
}

export const OPTIMIZER_COPY: Record<OptimizerMode, OptimizerCopy> = {
  prompt: {
    drawerTitle: 'AI 优化启动提示词',
    welcomeTitle: '让 AI 帮你打磨启动提示词',
    welcomeDescription:
      'AI 会基于编辑器中的当前内容给出完整新版；点击「对比」查看差异，确认后再应用。',
    quickPrompts: PROMPT_QUICK_PROMPTS,
    instructionPlaceholder:
      '描述你希望如何优化，例如：更结构化、补充人物一致性…',
    emptyCurrentPlaceholder: '请先在编辑器中填写启动提示词',
    emptyCurrentWarning: '启动提示词为空，无法优化',
    applySuccess: '已填入编辑器，请确认后保存',
    footerNote: 'AI 基于编辑器中的当前内容优化；应用后仍需点击「保存提示词」。',
    codeBlockLabel: '优化后的启动提示词',
  },
  art_style: {
    drawerTitle: 'AI 优化画风描述',
    welcomeTitle: '让 AI 帮你打磨画风描述',
    welcomeDescription:
      'AI 会基于当前画风描述给出完整新版；点击「对比」查看差异，确认后再应用。',
    quickPrompts: ART_STYLE_QUICK_PROMPTS,
    instructionPlaceholder:
      '描述你希望如何优化，例如：更突出线条与光影、适配豆包生图…',
    emptyCurrentPlaceholder: '请先填写画风描述',
    emptyCurrentWarning: '画风描述为空，无法优化',
    applySuccess: '已填入画风描述，点击「保存」生效',
    footerNote: 'AI 基于当前画风描述优化；应用后仍需点击「保存」。',
    codeBlockLabel: '优化后的画风描述',
  },
  character: {
    drawerTitle: 'AI 优化角色外形',
    welcomeTitle: '让 AI 帮你打磨角色外形描述',
    welcomeDescription:
      '例如同步你在生图平台里的调整：换发型、换衣服、调整体态。AI 会基于角色卡当前外形描述给出完整新版；点击「对比」查看差异，确认后再应用。',
    quickPrompts: CHARACTER_QUICK_PROMPTS,
    instructionPlaceholder:
      '描述你的修改要求，例如：在生图平台换了双马尾、改成黑色皮衣…',
    emptyCurrentPlaceholder: '该角色还没有外形描述',
    emptyCurrentWarning: '外形描述为空，无法优化',
    applySuccess: '角色卡已更新',
    footerNote:
      'AI 基于角色卡当前外形描述优化；点击「应用」会直接更新角色卡。',
    codeBlockLabel: '优化后的外形描述',
  },
}

let messageSeq = 0

/** 生成消息的唯一 key，避免同一毫秒内产生冲突。 */
export function nextMessageKey(prefix: 'user' | 'ai'): string {
  messageSeq += 1
  return `${prefix}-${Date.now()}-${messageSeq}`
}

/** 消息内容的片段：普通对话文本或代码块。 */
export interface PromptSegment {
  type: 'text' | 'code'
  text: string
}

/**
 * 把 AI 回复拆成普通文本与代码块。
 *
 * 兼容流式输出中尚未闭合的代码块：没有结束围栏时，
 * 围栏后的内容先按代码块展示，避免把 ``` 直接暴露给用户。
 */
export function splitPromptSegments(text: string): PromptSegment[] {
  const segments: PromptSegment[] = []
  const fencePattern = /```[^\n]*\r?\n?([\s\S]*?)(?:```|$)/g
  let cursor = 0
  let matched: RegExpExecArray | null

  while ((matched = fencePattern.exec(text)) !== null) {
    const before = text.slice(cursor, matched.index).trim()
    if (before) {
      segments.push({ type: 'text', text: before })
    }

    const code = matched[1].trim()
    if (code) {
      segments.push({ type: 'code', text: code })
    }

    cursor = fencePattern.lastIndex
  }

  const rest = text.slice(cursor).trim()
  if (rest) {
    segments.push({ type: 'text', text: rest })
  }
  return segments
}

/**
 * 取出 AI 回复中真正可用的提示词。
 *
 * 模型可能先寒暄再给代码块；有代码块时只取最长的那个（通常就是完整新版），
 * 没有代码块时才退回整段文本，保证旧的纯文本回复仍可对比、应用。
 */
export function extractPrompt(text: string): string {
  const codeSegments = splitPromptSegments(text).filter(
    (segment) => segment.type === 'code',
  )
  if (codeSegments.length === 0) {
    return text.trim()
  }
  return codeSegments.reduce((longest, segment) =>
    segment.text.length > longest.text.length ? segment : longest,
  ).text
}

/**
 * 组装发送给后端的对话历史。
 * 只保留成功完成的轮次，并按条数与总字符数双重截断，避免触发后端校验。
 */
export function buildHistory(
  messages: ChatMessage[],
  currentPrompt: string,
  instruction: string,
): PromptOptimizeMessage[] {
  const history: PromptOptimizeMessage[] = []
  let totalChars = currentPrompt.length + instruction.length

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const item = messages[index]
    if (history.length >= 11) break
    if (item.status !== 'success' || !item.content.trim()) continue
    if (totalChars + item.content.length > 29_000) break

    history.unshift({
      role: item.role === 'ai' ? 'assistant' : 'user',
      content: item.content,
    })
    totalChars += item.content.length
  }

  return history
}
