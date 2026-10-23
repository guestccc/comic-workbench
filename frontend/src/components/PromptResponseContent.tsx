import { Button, Typography } from 'antd'
import { CopyOutlined } from '@ant-design/icons'
import { splitPromptSegments } from '../utils/promptOptimizer'
import type { ChatStatus } from '../utils/promptOptimizer'

interface PromptResponseContentProps {
  /** AI 原始回复：可能包含寒暄 + 代码块 */
  content: string
  status: ChatStatus
  /** 代码块标题，如「优化后的启动提示词」 */
  codeLabel: string
  onCopy: (content: string) => void
}

/**
 * AI 优化回复的渲染组件。
 *
 * 代码块单独展示并带复制按钮，寒暄等普通文字按段落显示；
 * 流式生成过程中代码块尚未闭合时也按代码块展示，不把 ``` 暴露给用户。
 */
export default function PromptResponseContent({
  content,
  status,
  codeLabel,
  onCopy,
}: PromptResponseContentProps) {
  const segments = splitPromptSegments(content)
  if (segments.length === 0) {
    return null
  }

  return (
    <div className="optimizer-response">
      {segments.map((segment, index) =>
        segment.type === 'code' ? (
          <div className="optimizer-code-block" key={index}>
            <div className="optimizer-code-header">
              <span>{codeLabel}</span>
              {status !== 'updating' && (
                <Button
                  type="link"
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={() => onCopy(segment.text)}
                >
                  复制
                </Button>
              )}
            </div>
            <pre className="optimizer-code-text">{segment.text}</pre>
          </div>
        ) : (
          <Typography.Paragraph
            className="optimizer-chat-text"
            key={index}
          >
            {segment.text}
          </Typography.Paragraph>
        ),
      )}
    </div>
  )
}
