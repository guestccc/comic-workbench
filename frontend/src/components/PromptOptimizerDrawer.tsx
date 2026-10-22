import { useRef, useState } from 'react'
import { App, Button, Drawer, Typography } from 'antd'
import { Sender } from '@ant-design/x'
import { ApiError, getErrorMessage, streamPromptOptimize } from '../api/client'
import PromptOptimizerChat from './PromptOptimizerChat'
import {
  buildHistory,
  nextMessageKey,
  stripCodeFence,
} from '../utils/promptOptimizer'
import type { ChatMessage } from '../utils/promptOptimizer'
import { copyText } from '../utils/clipboard'

interface PromptOptimizerDrawerProps {
  open: boolean
  /** 编辑器中的当前提示词（可能尚未保存） */
  currentPrompt: string
  onClose: () => void
  /** 把 AI 结果填入编辑器，由父组件决定是否保存 */
  onApply: (prompt: string) => void
}

export default function PromptOptimizerDrawer({
  open,
  currentPrompt,
  onClose,
  onApply,
}: PromptOptimizerDrawerProps) {
  const { message } = App.useApp()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const updateAiMessage = (
    key: string,
    updater: (item: ChatMessage) => ChatMessage,
  ) => {
    setMessages((previous) =>
      previous.map((item) => (item.key === key ? updater(item) : item)),
    )
  }

  const handleSend = async (value?: string) => {
    const instruction = (value ?? input).trim()
    if (!instruction || loading) return
    if (!currentPrompt.trim()) {
      message.warning('启动提示词为空，无法优化')
      return
    }

    const history = buildHistory(messages, currentPrompt, instruction)
    const userKey = nextMessageKey('user')
    const aiKey = nextMessageKey('ai')

    setInput('')
    setMessages((previous) => [
      ...previous,
      { key: userKey, role: 'user', content: instruction, status: 'success' },
      { key: aiKey, role: 'ai', content: '', status: 'updating' },
    ])

    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    let received = ''

    try {
      const stream = streamPromptOptimize(
        {
          current_prompt: currentPrompt,
          messages: [...history, { role: 'user', content: instruction }],
        },
        controller.signal,
      )

      for await (const delta of stream) {
        received += delta
        updateAiMessage(aiKey, (item) => ({
          ...item,
          content: received,
          status: 'updating',
        }))
      }

      if (!received.trim()) {
        throw new ApiError('AI 未返回有效内容，请重试', 502, 'EMPTY_AI_RESPONSE')
      }
      updateAiMessage(aiKey, (item) => ({ ...item, status: 'success' }))
    } catch (error) {
      if (controller.signal.aborted) {
        updateAiMessage(aiKey, (item) => ({
          ...item,
          content: received || '（已停止生成）',
          status: 'abort',
        }))
      } else {
        const reason = getErrorMessage(error)
        updateAiMessage(aiKey, (item) => ({
          ...item,
          content: received ? `${received}\n\n⚠️ ${reason}` : reason,
          status: 'error',
        }))
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
      setLoading(false)
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
  }

  const handleClose = () => {
    abortRef.current?.abort()
    onClose()
  }

  const handleClear = () => {
    abortRef.current?.abort()
    setMessages([])
    setInput('')
  }

  const handleApply = (content: string) => {
    const prompt = stripCodeFence(content)
    if (!prompt) {
      message.warning('没有可应用的提示词内容')
      return
    }
    onApply(prompt)
    message.success('已填入编辑器，请确认后保存')
    handleClose()
  }

  const handleCopy = async (content: string) => {
    try {
      await copyText(content)
      message.success('已复制')
    } catch {
      message.error('复制失败，请手动选中文本后复制')
    }
  }

  return (
    <Drawer
      title="AI 优化启动提示词"
      open={open}
      onClose={handleClose}
      width={520}
      extra={
        <Button
          size="small"
          onClick={handleClear}
          disabled={messages.length === 0 && !loading}
        >
          清空对话
        </Button>
      }
      styles={{
        body: {
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        },
      }}
    >
      <div className="prompt-chat">
        <div className="prompt-chat-messages">
          <PromptOptimizerChat
            messages={messages}
            onSend={(instruction) => void handleSend(instruction)}
            onApply={handleApply}
            onCopy={(content) => void handleCopy(content)}
          />
        </div>

        <div className="prompt-chat-input">
          <Sender
            value={input}
            onChange={setInput}
            onSubmit={(value) => void handleSend(value)}
            onCancel={handleStop}
            loading={loading}
            disabled={!currentPrompt.trim()}
            placeholder={
              currentPrompt.trim()
                ? '描述你希望如何优化，例如：更结构化、补充人物一致性…'
                : '请先在编辑器中填写启动提示词'
            }
            autoSize={{ minRows: 2, maxRows: 6 }}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            AI 基于编辑器中的当前内容优化；应用后仍需点击「保存提示词」。
          </Typography.Text>
        </div>
      </div>
    </Drawer>
  )
}
