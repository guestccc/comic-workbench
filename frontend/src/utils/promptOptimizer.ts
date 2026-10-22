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

export type OptimizerMode = 'prompt' | 'art_style'

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
  },
}

let messageSeq = 0

/** 生成消息的唯一 key，避免同一毫秒内产生冲突。 */
export function nextMessageKey(prefix: 'user' | 'ai'): string {
  messageSeq += 1
  return `${prefix}-${Date.now()}-${messageSeq}`
}

/** 去掉模型可能输出的 Markdown 代码围栏，得到可直接使用的提示词。 */
export function stripCodeFence(text: string): string {
  const trimmed = text.trim()
  const matched = trimmed.match(/^```[^\n]*\n([\s\S]*?)\n?```$/)
  return (matched ? matched[1] : trimmed).trim()
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
