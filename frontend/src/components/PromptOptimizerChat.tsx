import { Avatar, Button, Space } from 'antd'
import {
  CopyOutlined,
  DiffOutlined,
  RobotOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { BubbleItemType, BubbleListProps } from '@ant-design/x'
import { Bubble, Prompts, Welcome } from '@ant-design/x'
import { extractPrompt, OPTIMIZER_COPY } from '../utils/promptOptimizer'
import type { ChatMessage, OptimizerMode } from '../utils/promptOptimizer'
import PromptResponseContent from './PromptResponseContent'

interface PromptOptimizerChatProps {
  mode: OptimizerMode
  messages: ChatMessage[]
  /** 点击快捷指令或气泡操作时回调 */
  onSend: (instruction: string) => void
  /** 打开原版 / 新版对比，确认后才应用 */
  onCompare: (content: string) => void
  onCopy: (content: string) => void
}

const ROLES: NonNullable<BubbleListProps['role']> = {
  ai: {
    placement: 'start',
    variant: 'filled',
    shape: 'corner',
    avatar: (
      <Avatar icon={<RobotOutlined />} style={{ backgroundColor: '#ff2442' }} />
    ),
  },
  user: {
    placement: 'end',
    variant: 'outlined',
    shape: 'corner',
    avatar: <Avatar icon={<UserOutlined />} />,
  },
}

/** AI 优化抽屉的会话区：空会话引导 + 消息气泡列表。 */
export default function PromptOptimizerChat({
  mode,
  messages,
  onSend,
  onCompare,
  onCopy,
}: PromptOptimizerChatProps) {
  const copy = OPTIMIZER_COPY[mode]

  if (messages.length === 0) {
    return (
      <div className="prompt-chat-welcome">
        <Welcome
          icon={<RobotOutlined style={{ fontSize: 30, color: '#ff2442' }} />}
          title={copy.welcomeTitle}
          description={copy.welcomeDescription}
        />
        <Prompts
          title="可以这样问"
          items={copy.quickPrompts.map(({ key, label }) => ({ key, label }))}
          vertical
          onItemClick={({ data }) => {
            const quick = copy.quickPrompts.find(
              (item) => item.key === data.key,
            )
            if (quick) {
              onSend(quick.instruction)
            }
          }}
        />
      </div>
    )
  }

  const bubbleItems: BubbleItemType[] = messages.map((item) => {
    // AI 可能先寒暄再给代码块；对比 / 复制只针对代码块里的提示词正文
    const promptText =
      item.role === 'ai' ? extractPrompt(item.content) : item.content
    const canApply =
      item.role === 'ai' &&
      item.status === 'success' &&
      promptText.length > 0

    return {
      key: item.key,
      role: item.role,
      content:
        item.role === 'ai' ? (
          <PromptResponseContent
            content={item.content}
            status={item.status}
            codeLabel={copy.codeBlockLabel}
            onCopy={onCopy}
          />
        ) : (
          item.content
        ),
      status: item.status,
      loading:
        item.role === 'ai' && item.status === 'updating' && !item.content,
      footer: canApply ? (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            icon={<DiffOutlined />}
            onClick={() => onCompare(promptText)}
          >
            对比
          </Button>
          <Button
            type="link"
            size="small"
            icon={<CopyOutlined />}
            onClick={() => onCopy(promptText)}
          >
            复制
          </Button>
        </Space>
      ) : undefined,
      footerPlacement: 'outer-start',
    }
  })

  return (
    <Bubble.List
      items={bubbleItems}
      role={ROLES}
      autoScroll
      style={{ height: '100%' }}
    />
  )
}
