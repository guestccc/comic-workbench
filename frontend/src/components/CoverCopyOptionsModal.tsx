import { useEffect, useState } from 'react'
import { Alert, App, Button, Input, Modal, Space, Tag, Typography } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'
import type { CoverCopyOption } from '../types'

interface CoverCopyOptionsModalProps {
  open: boolean
  storyId: number
  chapterNumber: number
  chapterTitle: string
  coverLabel: string
  coverMain: string
  coverHighlight: string
  coverSub: string
  onClose: () => void
  onApply: (option: CoverCopyOption) => void
}

function countChineseChars(text: string): number {
  return Array.from(text).filter((char) => char >= '一' && char <= '鿿')
    .length
}

function renderHighlighted(text: string, highlight: string) {
  if (!highlight || !text.includes(highlight)) return text
  const parts = text.split(highlight)
  return parts.map((part, index) => (
    <span key={`${part}-${index}`}>
      {part}
      {index < parts.length - 1 && (
        <span className="cover-copy-highlight">{highlight}</span>
      )}
    </span>
  ))
}

/**
 * 章节封面文案方案：从本章最强钩子生成多组主标题/副标题，用户选 1 组回填。
 * 只回填表单，不自动保存，也不直接生成图片。
 */
export default function CoverCopyOptionsModal({
  open,
  storyId,
  chapterNumber,
  chapterTitle,
  coverLabel,
  coverMain,
  coverHighlight,
  coverSub,
  onClose,
  onApply,
}: CoverCopyOptionsModalProps) {
  const { message } = App.useApp()
  const [direction, setDirection] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [options, setOptions] = useState<CoverCopyOption[]>([])
  const [postTitle, setPostTitle] = useState<string | null>(null)
  const [generated, setGenerated] = useState(false)

  useEffect(() => {
    if (!open) return
    setDirection('')
    setLoading(false)
    setError('')
    setOptions([])
    setPostTitle(null)
    setGenerated(false)
  }, [open])

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.generateCoverCopyOptions(
        storyId,
        chapterNumber,
        {
          chapter_title: chapterTitle,
          cover_label: coverLabel,
          cover_main: coverMain,
          cover_highlight: coverHighlight,
          cover_sub: coverSub,
          direction: direction.trim(),
        },
      )
      setOptions(data.options)
      setPostTitle(data.post_title)
      setGenerated(true)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const apply = (option: CoverCopyOption) => {
    onApply(option)
    message.success(
      '已回填主标题、标红词、副标题和画面提示词；保存章节后可直接立即生图，或复制封面生成指令出 3 个变体',
    )
    onClose()
  }

  return (
    <Modal
      title={
        chapterTitle
          ? `AI 生成封面文案：${chapterTitle}`
          : 'AI 生成封面文案'
      }
      open={open}
      onCancel={onClose}
      width={880}
      destroyOnHidden
      footer={
        <Space>
          <Button
            icon={<ThunderboltOutlined />}
            loading={loading}
            onClick={() => void generate()}
          >
            {generated ? '重新生成' : '生成 3 个方案'}
          </Button>
          <Button onClick={onClose}>关闭</Button>
        </Space>
      }
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="先选封面文案，再生成画面"
          description="从本章最强钩子生成 3 组主标题/副标题；选定后只回填表单，不会自动保存。保存章节后，再复制封面生成指令，让画面和这组文字讲同一个钩子。"
        />

        <div className="zhihu-info-row">
          <span className="zhihu-info-label">当前主标题</span>
          <Typography.Text>{coverMain || '未填写'}</Typography.Text>
        </div>
        <div className="zhihu-info-row">
          <span className="zhihu-info-label">当前副标题</span>
          <Typography.Text>{coverSub || '未填写'}</Typography.Text>
        </div>
        {postTitle && (
          <Alert
            type="success"
            showIcon
            message={`本章已有发文标题：${postTitle}`}
            description="封面方案会尽量和这个标题用同一个钩子，不会各写各的。"
          />
        )}

        <div>
          <Typography.Text strong>想要的方向（可选）</Typography.Text>
          <Input.TextArea
            rows={2}
            maxLength={500}
            showCount
            value={direction}
            onChange={(event) => setDirection(event.target.value)}
            placeholder="例如：更强调辞职原因和办公室恋情；主标题更短、更冲。"
            style={{ marginTop: 6 }}
          />
        </div>

        {error && <Alert type="error" showIcon message={error} />}

        {options.length > 0 && (
          <div className="copy-option-list">
            {options.map((option, index) => (
              <div
                key={`${index}-${option.style}-${option.narration_main}`}
                className={[
                  'copy-option-card',
                  option.recommended ? 'is-recommended' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                <div className="copy-option-header">
                  <Space wrap size={4}>
                    <Tag color="geekblue">{option.style}</Tag>
                    {option.hook_source && <Tag>{option.hook_source}</Tag>}
                    {option.recommended && <Tag color="gold">推荐</Tag>}
                  </Space>
                  <Button
                    type="primary"
                    size="small"
                    onClick={() => apply(option)}
                  >
                    采用此方案
                  </Button>
                </div>
                <Typography.Text type="secondary" className="copy-option-feature">
                  特点：{option.feature}
                </Typography.Text>
                {option.recommended && option.recommend_reason && (
                  <Typography.Text className="copy-option-reason">
                    推荐理由：{option.recommend_reason}
                  </Typography.Text>
                )}
                <Typography.Title level={5} className="copy-option-title">
                  {renderHighlighted(
                    option.narration_main,
                    option.narration_highlight,
                  )}
                  <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                    {countChineseChars(option.narration_main)}/12 字
                  </Typography.Text>
                </Typography.Title>
                <Typography.Paragraph className="copy-option-content">
                  {renderHighlighted(
                    option.narration_sub,
                    option.narration_highlight,
                  )}
                  <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                    {countChineseChars(option.narration_sub)}/35 字
                  </Typography.Text>
                </Typography.Paragraph>
                {option.visual_hint && (
                  <Typography.Text type="secondary">
                    建议画面：{option.visual_hint}
                  </Typography.Text>
                )}
                {option.image_prompt && (
                  <Typography.Text type="secondary" style={{ display: 'block' }}>
                    画面提示词已同步生成（{option.image_prompt.length} 字），采用后一并回填。
                  </Typography.Text>
                )}
              </div>
            ))}
          </div>
        )}
      </Space>
    </Modal>
  )
}
