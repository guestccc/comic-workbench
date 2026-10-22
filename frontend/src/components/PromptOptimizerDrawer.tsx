import { useRef, useState } from 'react'
import { App, Button, Drawer, Typography } from 'antd'
import { Sender } from '@ant-design/x'
import {
  ApiError,
  getErrorMessage,
  streamArtStyleOptimize,
  streamPromptOptimize,
} from '../api/client'
import PromptOptimizerChat from './PromptOptimizerChat'
import OptimizerCompareModal from './OptimizerCompareModal'
import { OPTIMIZER_COPY, buildHistory, nextMessageKey, stripCodeFence } from '../utils/promptOptimizer'
import type { ChatMessage, OptimizerMode } from '../utils/promptOptimizer'
import { copyText } from '../utils/clipboard'

interface PromptOptimizerDrawerProps {
  open: boolean
  /** 优化对象：启动提示词或画风描述 */
  mode?: OptimizerMode
  /** 当前内容（提示词 / 画风描述，可能尚未保存） */
  currentPrompt: string
  onClose: () => void
  /** 把 AI 结果填入编辑器，由父组件决定是否保存 */
  onApply: (prompt: string) => void
}

export default function PromptOptimizerDrawer({
  open,
  mode = 'prompt',
  currentPrompt,
  onClose,
  onApply,
}: PromptOptimizerDrawerProps) {
  const { message } = App.useApp()
  const copy = OPTIMIZER_COPY[mode]
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  // 待确认的新版内容；非 null 时展示对比弹窗
  const [compareContent, setCompareContent] = useState<string | null>(null)
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
      message.warning(copy.emptyCurrentWarning)
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
      const turn = { role: 'user' as const, content: instruction }
      const stream =
        mode === 'art_style'
          ? streamArtStyleOptimize(
              {
                current_style: currentPrompt,
                messages: [...history, turn],
              },
              controller.signal,
            )
          : streamPromptOptimize(
              {
                current_prompt: currentPrompt,
                messages: [...history, turn],
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

  const handleCompare = (content: string) => {
    const next = stripCodeFence(content)
    if (!next) {
      message.warning('没有可对比的内容')
      return
    }
    setCompareContent(next)
  }

  const handleClose = () => {
    abortRef.current?.abort()
    setCompareContent(null)
    onClose()
  }

  const handleClear = () => {
    abortRef.current?.abort()
    setCompareContent(null)
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
    message.success(copy.applySuccess)
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
    <>
      <Drawer
        title={copy.drawerTitle}
        open={open}
        onClose={handleClose}
        width={520}
        // 画风优化抽屉会叠在编辑弹窗之上，需要更高的层级
        zIndex={1200}
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
              mode={mode}
              messages={messages}
              onSend={(instruction) => void handleSend(instruction)}
              onCompare={handleCompare}
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
                  ? copy.instructionPlaceholder
                  : copy.emptyCurrentPlaceholder
              }
              autoSize={{ minRows: 2, maxRows: 6 }}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {copy.footerNote}
            </Typography.Text>
          </div>
        </div>
      </Drawer>

      <OptimizerCompareModal
        open={compareContent !== null}
        original={currentPrompt}
        optimized={compareContent ?? ''}
        onClose={() => setCompareContent(null)}
        onApply={(value) => {
          setCompareContent(null)
          handleApply(value)
        }}
      />
    </>
  )
}
