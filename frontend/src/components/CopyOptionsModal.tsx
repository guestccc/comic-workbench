import { useEffect, useState } from 'react'
import { Button, Checkbox, Modal, Space, Tag, Typography } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import type { GeneratedCopyOption } from '../types'

interface CopyOptionsModalProps {
  open: boolean
  options: GeneratedCopyOption[]
  generating: boolean
  /**
   * true 时可勾选多个方案（一个故事拆成多次发作品）；
   * false 时每个方案单独提供「采用此方案」按钮（单选）。
   */
  multiple?: boolean
  /** 用户确认采用：传入选中的方案数组；单选模式下长度为 1 */
  onApply: (options: GeneratedCopyOption[]) => void
  /** 重新调用 AI，生成一组新方案 */
  onRegenerate: () => void
  onClose: () => void
}

/**
 * AI 文案方案选择弹窗。
 *
 * 一次展示 AI 返回的多个方案，标出各自特点与推荐项；
 * 只负责展示与选择，填入表单、批量建稿、保存等动作由调用方决定。
 */
export default function CopyOptionsModal({
  open,
  options,
  generating,
  multiple = false,
  onApply,
  onRegenerate,
  onClose,
}: CopyOptionsModalProps) {
  // 多选模式下的勾选状态（按下标记录）；弹窗打开或换了一批方案时重置为推荐项
  const [selected, setSelected] = useState<Set<number>>(new Set())

  useEffect(() => {
    if (!open) return
    const recommendedIndex = options.findIndex((option) => option.recommended)
    setSelected(new Set([recommendedIndex >= 0 ? recommendedIndex : 0]))
  }, [open, options])

  const toggle = (index: number) => {
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  const selectedOptions = options.filter((_, index) => selected.has(index))

  return (
    <Modal
      title={multiple ? '选择要采用的文案方案（可多选）' : '选择一个文案方案'}
      open={open}
      width={820}
      onCancel={onClose}
      footer={[
        <Button
          key="regenerate"
          icon={<ThunderboltOutlined />}
          loading={generating}
          onClick={onRegenerate}
        >
          重新生成
        </Button>,
        ...(multiple
          ? [
              <Button
                key="apply"
                type="primary"
                disabled={selectedOptions.length === 0}
                onClick={() => onApply(selectedOptions)}
              >
                采用选中方案（{selectedOptions.length}）
              </Button>,
            ]
          : []),
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
      ]}
    >
      <Typography.Paragraph type="secondary">
        {multiple
          ? '一个故事可以拆成多次发作品：勾选多个方案，一次各建一条草稿；只勾选一个时会填入当前表单，可继续编辑。'
          : 'AI 给出了不同切入角度；点击「采用此方案」只会填入文案，确认后仍需手动保存。'}
      </Typography.Paragraph>
      <div className="copy-option-list">
        {options.map((option, index) => (
          <div
            key={`${index}-${option.style}`}
            className={[
              'copy-option-card',
              option.recommended ? 'is-recommended' : '',
              multiple && selected.has(index) ? 'is-selected' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <div
              className="copy-option-header"
              onClick={multiple ? () => toggle(index) : undefined}
              style={multiple ? { cursor: 'pointer' } : undefined}
            >
              {/* 勾选框自己处理切换，阻止冒泡避免重复触发 */}
              <Space wrap size={4} onClick={(event) => event.stopPropagation()}>
                {multiple && (
                  <Checkbox
                    checked={selected.has(index)}
                    onChange={() => toggle(index)}
                  />
                )}
                <Tag color="geekblue">{option.style}</Tag>
                {option.recommended && <Tag color="gold">推荐</Tag>}
              </Space>
              {!multiple && (
                <Button
                  type="primary"
                  size="small"
                  onClick={() => onApply([option])}
                >
                  采用此方案
                </Button>
              )}
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
              {option.title}
            </Typography.Title>
            <Typography.Paragraph className="copy-option-content">
              {option.content}
            </Typography.Paragraph>
          </div>
        ))}
      </div>
    </Modal>
  )
}
