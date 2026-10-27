import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Collapse,
  Empty,
  Modal,
  Segmented,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { api, ApiError, getErrorMessage } from '../api/client'
import type {
  MappingDecision,
  MappingReview,
  MappingReviewApplyResult,
  MappingReviewChange,
  StoryBreakdown,
} from '../types'

interface MappingReviewPanelProps {
  storyId: number
  open: boolean
  breakdown: StoryBreakdown | null
  onClose: () => void
  onApplied: (result: MappingReviewApplyResult) => void
  onReviewUpdated?: (review: MappingReview | null) => void
}

const RISK_COLOR: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'green',
}

const KIND_TEXT: Record<string, string> = {
  split: '拆分',
  merge: '合并',
  keep: '保持原样',
}

function decisionOptions() {
  return [
    { label: '同意', value: 'approved' },
    { label: '保留', value: 'rejected' },
    { label: '稍后', value: 'undecided' },
  ]
}

function changeTitle(change: MappingReviewChange): string {
  const pages = change.old_page_numbers.join('、')
  const delta =
    change.page_delta > 0
      ? ` · 页数 +${change.page_delta}`
      : change.page_delta < 0
        ? ` · 页数 ${change.page_delta}`
        : ''
  return `第 ${pages} 段 · ${KIND_TEXT[change.kind] ?? change.kind}${delta}`
}

export default function MappingReviewPanel({
  storyId,
  open,
  breakdown,
  onClose,
  onApplied,
  onReviewUpdated,
}: MappingReviewPanelProps) {
  const { message, modal } = App.useApp()
  const [review, setReview] = useState<MappingReview | null>(null)
  const [decisions, setDecisions] = useState<
    Record<string, MappingDecision>
  >({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [clearChapters, setClearChapters] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getMappingReview(storyId)
      setReview(data)
      setDecisions(data.decisions)
      setClearChapters(false)
      onReviewUpdated?.(data.status === 'draft' ? data : null)
    } catch (loadError) {
      if (loadError instanceof ApiError && loadError.status === 404) {
        setReview(null)
        setDecisions({})
      } else {
        setError(getErrorMessage(loadError))
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, storyId])

  const mappingByNumber = useMemo(
    () =>
      new Map(
        (breakdown?.mapping ?? []).map((item) => [
          item.page_number,
          item,
        ]),
      ),
    [breakdown?.mapping],
  )

  const changes = review?.changes ?? []
  const pending = changes.filter(
    (change) => (decisions[change.id] ?? 'undecided') === 'undecided',
  )
  const approved = changes.filter(
    (change) => decisions[change.id] === 'approved',
  )
  const applicableApproved = approved.filter(
    (change) => change.kind !== 'keep',
  )
  const rejected = changes.filter(
    (change) => decisions[change.id] === 'rejected',
  )
  const totalDelta = applicableApproved.reduce(
    (sum, change) => sum + change.page_delta,
    0,
  )
  const isDraft = review?.status === 'draft'
  const chaptersLocked = review?.summary.chapters_locked ?? false

  const updateDecision = async (
    change: MappingReviewChange,
    decision: MappingDecision,
  ) => {
    if (!review || !isDraft || saving) return
    const previous = decisions
    const next = { ...decisions, [change.id]: decision }
    setDecisions(next)
    setSaving(true)
    try {
      const data = await api.updateMappingReviewDecisions(storyId, {
        [change.id]: decision,
      })
      setReview(data)
      setDecisions(data.decisions)
      onReviewUpdated?.(data)
    } catch (updateError) {
      setDecisions(previous)
      message.error(getErrorMessage(updateError))
    } finally {
      setSaving(false)
    }
  }

  const doApply = async () => {
    if (!review) return
    setApplying(true)
    try {
      await api.updateMappingReviewDecisions(storyId, decisions)
      const result = await api.applyMappingReview(
        storyId,
        chaptersLocked ? clearChapters : false,
      )
      message.success(
        result.chapters_cleared
          ? '已应用对照变更；章节已清空，需要重新规划'
          : '已应用对照变更',
      )
      onApplied(result)
      onReviewUpdated?.(null)
      onClose()
    } catch (applyError) {
      message.error(getErrorMessage(applyError))
    } finally {
      setApplying(false)
    }
  }

  const confirmApply = () => {
    if (!review) return
    if (chaptersLocked && !clearChapters) {
      message.warning('请先勾选确认清空章节')
      return
    }
    modal.confirm({
      title: '应用审阅变更？',
      width: 520,
      content: (
        <div>
          <p>
            当前 {review.summary.current_page_count} 段 → 预计{' '}
            {review.summary.current_page_count + totalDelta} 段。
          </p>
          <p>
            已同意 {applicableApproved.length} 项；未决 {pending.length}{' '}
            项将保留原样。
          </p>
          {chaptersLocked ? (
            <Alert
              type="warning"
              showIcon
              message={`应用后会清空 ${review.summary.chapters_count} 章及章节文案`}
              description="章节封面 / 引导卡提示词会丢失；图片会移到上传目录的 chapters-archive 备份目录。"
            />
          ) : null}
        </div>
      ),
      okText: '应用',
      cancelText: '取消',
      onOk: doApply,
    })
  }

  const renderChange = (change: MappingReviewChange) => {
    const currentItems = change.old_page_numbers.flatMap((number) => {
      const item = mappingByNumber.get(number)
      return item ? [item] : []
    })
    return (
      <Card
        key={change.id}
        size="small"
        className="mapping-review-change"
        title={<span>{changeTitle(change)}</span>}
        extra={
          <Space size={4}>
            <Tag color={RISK_COLOR[change.risk]}>{change.risk}</Tag>
            {change.crosses_chapter ? <Tag color="purple">跨章节</Tag> : null}
          </Space>
        }
      >
        {change.reason ? (
          <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
            {change.reason}
          </Typography.Paragraph>
        ) : null}

        <Typography.Text strong>现状</Typography.Text>
        <div className="mapping-review-source">
          {currentItems.map((item) => (
            <div key={item.page_number}>
              <Typography.Text type="secondary">
                第{item.page_number}段：
              </Typography.Text>
              {item.source_text}
            </div>
          ))}
        </div>

        {change.proposed_segments.length > 0 ? (
          <>
            <Typography.Text strong style={{ display: 'block', marginTop: 8 }}>
              建议拆成 {change.proposed_segments.length} 段
            </Typography.Text>
            <div className="mapping-review-segments">
              {change.proposed_segments.map((segment, index) => (
                <div
                  className="mapping-review-segment"
                  key={`${change.id}-${index}`}
                >
                  <Typography.Text type="secondary">
                    建议段 {index + 1}：
                  </Typography.Text>
                  {segment.source_text}
                  {segment.summary ? (
                    <div>
                      <Typography.Text type="secondary">
                        简述：{segment.summary}
                      </Typography.Text>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </>
        ) : null}

        <div className="mapping-review-decision">
          <Typography.Text type="secondary">你的决定：</Typography.Text>
          <Segmented
            size="small"
            options={decisionOptions()}
            value={decisions[change.id] ?? 'undecided'}
            disabled={!isDraft || saving}
            onChange={(value) =>
              void updateDecision(change, value as MappingDecision)
            }
          />
        </div>
      </Card>
    )
  }

  return (
    <Modal
      title="审阅分镜对照"
      open={open}
      onCancel={onClose}
      width={920}
      destroyOnHidden
      footer={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          <Button
            type="primary"
            loading={applying}
            disabled={
              !isDraft || !review || applicableApproved.length === 0
            }
            onClick={confirmApply}
          >
            应用已同意的 {applicableApproved.length} 项
          </Button>
        </Space>
      }
    >
      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : error ? (
        <Alert
          type="error"
          showIcon
          message="读取审阅草稿失败"
          description={error}
          action={
            <Button size="small" onClick={() => void load()}>
              重试
            </Button>
          }
        />
      ) : !review ? (
        <Empty description="还没有审阅草稿">
          <Typography.Text type="secondary">
            让 Claude Code 用 mapping-director 生成提案并写入
            `/breakdown/mapping-review` 后，点下方刷新。
          </Typography.Text>
          <div style={{ marginTop: 12 }}>
            <Button icon={<ReloadOutlined />} onClick={() => void load()}>
              刷新
            </Button>
          </div>
        </Empty>
      ) : (
        <div>
          <Alert
            className="mapping-review-summary"
            type={review.status === 'draft' ? 'info' : 'success'}
            showIcon
            message={
              review.status === 'draft'
                ? `当前 ${review.summary.current_page_count} 段 → 预计 ${
                    review.summary.current_page_count + totalDelta
                  } 段 · ${pending.length} 处待决定 · ${approved.length} 处已同意`
                : review.status === 'applied'
                  ? '这份审阅草稿已应用'
                  : '这份审阅草稿已丢弃'
            }
            description={
              review.status === 'draft'
                ? '低风险变更默认同意；未决项按保留处理。应用前可以逐项改判。'
                : undefined
            }
            action={
              <Button size="small" onClick={() => void load()}>
                刷新
              </Button>
            }
          />

          {chaptersLocked && isDraft ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message={`应用后会清空 ${review.summary.chapters_count} 章及章节文案`}
              description="章节封面 / 引导卡提示词会丢失；图片会移到 chapters-archive 备份目录。"
              action={
                <Checkbox
                  checked={clearChapters}
                  onChange={(event) =>
                    setClearChapters(event.target.checked)
                  }
                >
                  确认清空
                </Checkbox>
              }
            />
          ) : null}

          {pending.length > 0 ? (
            <>
              <Typography.Title level={5}>
                需要你决定（{pending.length}）
              </Typography.Title>
              {pending.map(renderChange)}
            </>
          ) : (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 12 }}
              message="没有需要你决定的项，可以直接应用"
            />
          )}

          {approved.length > 0 ? (
            <Collapse
              style={{ marginTop: 12 }}
              items={[
                {
                  key: 'approved',
                  label: `已同意 / 自动通过（${approved.length}）`,
                  children: approved.map(renderChange),
                },
              ]}
            />
          ) : null}

          {rejected.length > 0 ? (
            <Collapse
              style={{ marginTop: 8 }}
              items={[
                {
                  key: 'rejected',
                  label: `已保留原样（${rejected.length}）`,
                  children: rejected.map(renderChange),
                },
              ]}
            />
          ) : null}
        </div>
      )}
    </Modal>
  )
}
