import type { PromptOptimizeMessage } from '../types'

export type ChatStatus = 'success' | 'updating' | 'error' | 'abort'

export interface ChatMessage {
  key: string
  role: 'user' | 'ai'
  content: string
  status: ChatStatus
}

/** 空会话时的快捷优化指令，点击后直接发送。 */
export const QUICK_PROMPTS = [
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
