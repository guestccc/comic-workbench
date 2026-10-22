import { Avatar, Button, Space } from 'antd'
import {
  CheckOutlined,
  CopyOutlined,
  RobotOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { BubbleItemType, BubbleListProps } from '@ant-design/x'
import { Bubble, Prompts, Welcome } from '@ant-design/x'
import { QUICK_PROMPTS } from '../utils/promptOptimizer'
import type { ChatMessage } from '../utils/promptOptimizer'

interface PromptOptimizerChatProps {
  messages: ChatMessage[]
  /** 点击快捷指令或气泡操作时回调 */
  onSend: (instruction: string) => void
  onApply: (content: string) => void
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
  messages,
  onSend,
  onApply,
  onCopy,
}: PromptOptimizerChatProps) {
  if (messages.length === 0) {
    return (
      <div className="prompt-chat-welcome">
        <Welcome
          icon={<RobotOutlined style={{ fontSize: 30, color: '#ff2442' }} />}
          title="让 AI 帮你打磨启动提示词"
          description="AI 会基于编辑器中的当前内容给出完整新版，确认后点击「应用到编辑器」即可。"
        />
        <Prompts
          title="可以这样问"
          items={QUICK_PROMPTS.map(({ key, label }) => ({ key, label }))}
          vertical
          onItemClick={({ data }) => {
            const quick = QUICK_PROMPTS.find((item) => item.key === data.key)
            if (quick) {
              onSend(quick.instruction)
            }
          }}
        />
      </div>
    )
  }

  const bubbleItems: BubbleItemType[] = messages.map((item) => {
    const canApply =
      item.role === 'ai' &&
      item.status === 'success' &&
      item.content.trim().length > 0

    return {
      key: item.key,
      role: item.role,
      content: item.content,
      status: item.status,
      loading:
        item.role === 'ai' && item.status === 'updating' && !item.content,
      footer: canApply ? (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            icon={<CheckOutlined />}
            onClick={() => onApply(item.content)}
          >
            应用到编辑器
          </Button>
          <Button
            type="link"
            size="small"
            icon={<CopyOutlined />}
            onClick={() => onCopy(item.content)}
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
