import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Input,
  Modal,
  Space,
  Tag,
  Typography,
} from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'
import type { ChapterCoverOptimizeResult } from '../types'

interface ChapterCoverOptimizerModalProps {
  open: boolean
  storyId: number
  chapterNumber: number
  chapterTitle: string
  coverLabel: string
  coverMain: string
  coverSub: string
  coverHighlight: string
  imagePrompt: string
  onClose: () => void
  onApply: (values: ChapterCoverOptimizeResult) => void
}

function countChineseChars(text: string): number {
  return Array.from(text).filter((char) => char >= '一' && char <= '鿿')
    .length
}

/**
 * 章节封面 AI 优化：只允许改主标题、副标题、画面提示词。
 *
 * 顶部小字、标红词、章节标题与引导卡不进入结果，也不会被回填。
 */
export default function ChapterCoverOptimizerModal({
  open,
  storyId,
  chapterNumber,
  chapterTitle,
  coverLabel,
  coverMain,
  coverSub,
  coverHighlight,
  imagePrompt,
  onClose,
  onApply,
}: ChapterCoverOptimizerModalProps) {
  const { message } = App.useApp()
  const [suggestion, setSuggestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ChapterCoverOptimizeResult | null>(
    null,
  )
  const [showCurrentPrompt, setShowCurrentPrompt] = useState(false)

  useEffect(() => {
    if (open) {
      setError('')
      setResult(null)
      setShowCurrentPrompt(false)
    }
  }, [open])

  const generate = async () => {
    const text = suggestion.trim()
    if (!text) {
      message.warning('请先填写你的优化建议')
      return
    }
    setLoading(true)
    setError('')
    try {
      const next = await api.optimizeChapterCover(storyId, chapterNumber, {
        chapter_title: chapterTitle,
        cover_label: coverLabel,
        cover_main: coverMain,
        cover_sub: coverSub,
        cover_highlight: coverHighlight,
        current_prompt: imagePrompt,
        suggestion: text,
      })
      setResult(next)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const updateResult = (
    key: keyof ChapterCoverOptimizeResult,
    value: string,
  ) => {
    setResult((previous) =>
      previous ? { ...previous, [key]: value } : previous,
    )
  }

  const apply = () => {
    if (!result) return
    const main = result.narration_main.trim()
    const sub = result.narration_sub.trim()
    const prompt = result.image_prompt.trim()
    if (!main || !sub || !prompt) {
      message.warning('主标题、副标题和画面提示词都不能为空')
      return
    }
    if (countChineseChars(main) >= 15) {
      message.warning('主标题必须少于 15 个汉字')
      return
    }
    if (countChineseChars(sub) >= 35) {
      message.warning('副标题必须少于 35 个汉字')
      return
    }
    if (
      coverHighlight &&
      !main.includes(coverHighlight) &&
      !sub.includes(coverHighlight)
    ) {
      message.warning(`标红词「${coverHighlight}」必须保留在主标题或副标题中`)
      return
    }
    onApply({ narration_main: main, narration_sub: sub, image_prompt: prompt })
    message.success('已回填主标题、副标题和画面提示词，请确认后保存章节')
    onClose()
  }

  return (
    <Modal
      title={
        chapterTitle
          ? `AI 优化章节封面：${chapterTitle}`
          : 'AI 优化章节封面'
      }
      open={open}
      onCancel={onClose}
      width={760}
      destroyOnHidden
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            disabled={!result || loading}
            onClick={apply}
          >
            应用到章节
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="只允许修改三项：主标题、副标题、画面提示词"
          description="顶部小字、标红词、章节标题、引导卡和其他字段都不会改。标红词必须保留在新主标题或副标题中。"
        />

        <div className="zhihu-info-row">
          <span className="zhihu-info-label">顶部小字</span>
          <Typography.Text>{coverLabel || '未填写'}</Typography.Text>
          <Tag>固定</Tag>
        </div>
        <div className="zhihu-info-row">
          <span className="zhihu-info-label">标红词</span>
          <Typography.Text>{coverHighlight || '无'}</Typography.Text>
          <Tag>固定</Tag>
        </div>
        <div className="zhihu-info-row">
          <span className="zhihu-info-label">当前主标题</span>
          <Typography.Text>{coverMain || '未填写'}</Typography.Text>
        </div>
        <div className="zhihu-info-row">
          <span className="zhihu-info-label">当前副标题</span>
          <Typography.Text>{coverSub || '未填写'}</Typography.Text>
        </div>

        <div>
          <Button
            type="link"
            size="small"
            style={{ paddingInline: 0 }}
            onClick={() => setShowCurrentPrompt((previous) => !previous)}
          >
            {showCurrentPrompt ? '收起当前画面提示词' : '查看当前画面提示词'}
            <Typography.Text type="secondary" style={{ marginLeft: 4 }}>
              （只读，已自动带入{imagePrompt ? `，${imagePrompt.length} 字` : '，当前为空'}）
            </Typography.Text>
          </Button>
          {showCurrentPrompt && (
            <pre
              className="optimizer-code-text"
              style={{
                maxHeight: 180,
                overflow: 'auto',
                marginTop: 6,
                border: '1px solid #f0f0f0',
                borderRadius: 8,
              }}
            >
              {imagePrompt || '未填写，AI 将根据封面文字与画风直接生成'}
            </pre>
          )}
        </div>

        <div>
          <Typography.Text strong>优化建议（在这里输入）</Typography.Text>
          <Input.TextArea
            rows={3}
            maxLength={2000}
            showCount
            value={suggestion}
            onChange={(event) => setSuggestion(event.target.value)}
            placeholder="例如：主标题更有悬念，副标题更口语化；画面突出主角按下警报的瞬间，减少杂物。"
            style={{ marginTop: 6 }}
          />
        </div>

        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={loading}
          onClick={() => void generate()}
        >
          {result ? '重新生成' : '生成优化方案'}
        </Button>

        {error && <Alert type="error" showIcon message={error} />}

        {result && (
          <>
            <Typography.Title level={5} style={{ marginBottom: 0 }}>
              优化结果（可继续修改）
            </Typography.Title>
            <div>
              <Typography.Text strong>
                主标题（{countChineseChars(result.narration_main)}/15 字）
              </Typography.Text>
              <Input
                value={result.narration_main}
                maxLength={200}
                onChange={(event) =>
                  updateResult('narration_main', event.target.value)
                }
                style={{ marginTop: 6 }}
              />
            </div>
            <div>
              <Typography.Text strong>
                副标题（{countChineseChars(result.narration_sub)}/35 字）
              </Typography.Text>
              <Input.TextArea
                rows={2}
                maxLength={4000}
                value={result.narration_sub}
                onChange={(event) =>
                  updateResult('narration_sub', event.target.value)
                }
                style={{ marginTop: 6 }}
              />
            </div>
            <div>
              <Typography.Text strong>画面提示词</Typography.Text>
              <Input.TextArea
                rows={12}
                maxLength={8000}
                value={result.image_prompt}
                onChange={(event) =>
                  updateResult('image_prompt', event.target.value)
                }
                style={{ marginTop: 6 }}
              />
            </div>
          </>
        )}
      </Space>
    </Modal>
  )
}
