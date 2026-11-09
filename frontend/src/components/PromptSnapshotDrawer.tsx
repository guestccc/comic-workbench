import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Drawer,
  Empty,
  Popconfirm,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import { HistoryOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

import { api, getErrorMessage } from '../api/client'
import type { PromptSnapshot } from '../types'

interface PromptSnapshotDrawerProps {
  open: boolean
  storyId: number
  targetType: 'cover' | 'body'
  chapterNumber?: number | null
  pageNumber?: number | null
  onClose: () => void
  onRestored?: () => void
}

/** 渲染历史抽屉：看某张封面 / 某一页用过哪些规则，并可恢复上一版提示词。 */
export default function PromptSnapshotDrawer({
  open,
  storyId,
  targetType,
  chapterNumber,
  pageNumber,
  onClose,
  onRestored,
}: PromptSnapshotDrawerProps) {
  const { message } = App.useApp()
  const [snapshots, setSnapshots] = useState<PromptSnapshot[]>([])
  const [loading, setLoading] = useState(false)
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setExpandedIds(new Set())
    api
      .listPromptSnapshots(storyId, {
        target_type: targetType,
        chapter_number: chapterNumber ?? undefined,
        page_number: pageNumber ?? undefined,
        limit: 30,
      })
      .then((items) => {
        if (!cancelled) setSnapshots(items)
      })
      .catch((error) => {
        if (!cancelled) message.error(getErrorMessage(error))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, storyId, targetType, chapterNumber, pageNumber])

  const restore = async (snapshot: PromptSnapshot) => {
    try {
      await api.restorePromptSnapshot(snapshot.id)
      message.success('已恢复这版提示词')
      onRestored?.()
      onClose()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const toggleExpanded = (snapshotId: number) => {
    setExpandedIds((previous) => {
      const next = new Set(previous)
      if (next.has(snapshotId)) {
        next.delete(snapshotId)
      } else {
        next.add(snapshotId)
      }
      return next
    })
  }

  const targetParts = [
    chapterNumber != null ? `第 ${chapterNumber} 章` : null,
    targetType === 'cover'
      ? '封面'
      : pageNumber != null
        ? `第 ${pageNumber} 页正文`
        : '正文页',
  ].filter(Boolean)

  return (
    <Drawer
      title={`提示词历史 · ${targetParts.join(' · ')}`}
      open={open}
      onClose={onClose}
      width={820}
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        每次通过模板渲染都会留一条快照；恢复只改提示词，不会自动重生成图片。
      </Typography.Paragraph>
      {loading ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : snapshots.length === 0 ? (
        <Empty description="还没有渲染快照；用模板渲染一次后就会出现" />
      ) : (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {snapshots.map((snapshot) => {
            const appliedRules = snapshot.applied_rules ?? []
            const ruleChecks = snapshot.rule_checks ?? []
            const isExpanded = expandedIds.has(snapshot.id)
            return (
              <Card
                key={snapshot.id}
                size="small"
                className="prompt-snapshot-card"
                style={{ width: '100%' }}
              >
                <div className="prompt-snapshot-head">
                  <Space wrap size={6}>
                    <Typography.Text strong>
                      {dayjs(snapshot.created_at).format(
                        'YYYY-MM-DD HH:mm:ss',
                      )}
                    </Typography.Text>
                    <Tag>
                      {snapshot.target_type === 'cover' ? '封面' : '正文'}
                    </Tag>
                    {snapshot.chapter_number != null && (
                      <Tag>第{snapshot.chapter_number}章</Tag>
                    )}
                    {snapshot.page_number != null && (
                      <Tag>第{snapshot.page_number}页</Tag>
                    )}
                    {snapshot.restored_from_id != null && (
                      <Tag color="orange">
                        恢复自 #{snapshot.restored_from_id}
                      </Tag>
                    )}
                  </Space>
                  <Popconfirm
                    title="恢复这版提示词？"
                    description="会覆盖当前提示词；图片不会自动重生成。"
                    onConfirm={() => void restore(snapshot)}
                    okText="恢复"
                    cancelText="取消"
                  >
                    <Button size="small" icon={<HistoryOutlined />}>
                      恢复此版
                    </Button>
                  </Popconfirm>
                </div>

                <div className="prompt-snapshot-section">
                  <Typography.Text
                    type="secondary"
                    className="prompt-snapshot-label"
                  >
                    命中规则
                  </Typography.Text>
                  {appliedRules.length > 0 ? (
                    <Space wrap size={4}>
                      {appliedRules.map((rule) => (
                        <Tag key={rule.id} color="purple">
                          {rule.title}
                        </Tag>
                      ))}
                    </Space>
                  ) : (
                    <Typography.Text type="secondary">无</Typography.Text>
                  )}
                </div>

                {ruleChecks.length > 0 && (
                  <div className="prompt-snapshot-section">
                    <Typography.Text
                      type="secondary"
                      className="prompt-snapshot-label"
                    >
                      规则检查
                    </Typography.Text>
                    <Space wrap size={4}>
                      {ruleChecks.map((check) => (
                        <Tag
                          key={check.rule_id}
                          color={check.passed ? 'green' : 'red'}
                        >
                          {check.title}：
                          {check.passed ? '通过' : check.message || '失败'}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                )}

                <div className="prompt-snapshot-prompt-head">
                  <Typography.Text type="secondary">提示词</Typography.Text>
                  <Button
                    type="link"
                    size="small"
                    onClick={() => toggleExpanded(snapshot.id)}
                  >
                    {isExpanded ? '收起' : '展开全部'}
                  </Button>
                </div>
                <pre
                  className={
                    isExpanded
                      ? 'prompt-snapshot-prompt is-expanded'
                      : 'prompt-snapshot-prompt'
                  }
                >
                  {snapshot.prompt}
                </pre>
              </Card>
            )
          })}
        </Space>
      )}
    </Drawer>
  )
}
