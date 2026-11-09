import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Drawer,
  Progress,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'
import type {
  DesignRule,
  DesignRuleCoverageItem,
  DesignRuleCoverageRun,
} from '../types'

interface DesignRuleCoverageDrawerProps {
  open: boolean
  rule: DesignRule | null
  onClose: () => void
}

const AI_LABELS: Record<string, string> = {
  pending: '待判定',
  covered: '已落实',
  partial: '部分落实',
  missing: '未落实',
  not_applicable: '不适用',
  not_generated: '未生成',
  error: '判定失败',
}

const FINAL_LABELS: Record<string, string> = {
  pending_confirmation: '待人工确认',
  confirmed_covered: '人工确认已落实',
  confirmed_missing: '人工确认未落实',
  not_generated: '未生成',
  error: '判定失败',
}

function aiColor(status: string): string {
  if (status === 'covered') return 'green'
  if (status === 'partial') return 'gold'
  if (status === 'missing') return 'red'
  if (status === 'error') return 'red'
  if (status === 'not_generated') return 'default'
  return 'blue'
}

function assetLabel(item: DesignRuleCoverageItem): string {
  if (item.target_type === 'cover') {
    return `${item.story_name} · 第${item.chapter_number}章封面`
  }
  if (item.target_type === 'guide') {
    return `${item.story_name} · 第${item.chapter_number}章引导卡`
  }
  return `${item.story_name} · 第${item.chapter_number}章第${item.page_number}页`
}

/** 规则落实检测：启动后台任务、轮询进度、逐条人工确认。 */
export default function DesignRuleCoverageDrawer({
  open,
  rule,
  onClose,
}: DesignRuleCoverageDrawerProps) {
  const { message } = App.useApp()
  const [run, setRun] = useState<DesignRuleCoverageRun | null>(null)
  const [loading, setLoading] = useState(false)
  const [starting, setStarting] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])

  useEffect(() => {
    if (!open || !rule) return
    let cancelled = false
    setLoading(true)
    setSelectedKeys([])
    void api
      .getLatestDesignRuleCoverage(rule.id)
      .then((data) => {
        if (!cancelled) setRun(data)
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
  }, [open, rule, message])

  useEffect(() => {
    if (!open || !run || !['queued', 'running'].includes(run.status)) return
    const timer = window.setInterval(() => {
      void api
        .getDesignRuleCoverageRun(run.id)
        .then(setRun)
        .catch((error) => message.error(getErrorMessage(error)))
    }, 1500)
    return () => window.clearInterval(timer)
  }, [open, run, message])

  const handleStart = async () => {
    if (!rule) return
    setStarting(true)
    try {
      const data = await api.startDesignRuleCoverage(rule.id)
      setRun(data)
      setSelectedKeys([])
      message.success('检测任务已开始，后台运行中')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setStarting(false)
    }
  }

  const handleCancel = async () => {
    if (!run) return
    try {
      setRun(await api.cancelDesignRuleCoverage(run.id))
      message.info('已请求取消')
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const handleConfirm = async (keys: string[], status: 'covered' | 'missing') => {
    if (!run || keys.length === 0) return
    setConfirming(true)
    try {
      const data = await api.confirmDesignRuleCoverage(run.id, {
        item_keys: keys,
        status,
      })
      setRun(data)
      setSelectedKeys([])
      message.success(
        status === 'covered'
          ? `已人工确认 ${keys.length} 条为“已落实”`
          : `已人工确认 ${keys.length} 条为“未落实”`,
      )
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setConfirming(false)
    }
  }

  const pendingItems = useMemo(
    () =>
      (run?.items ?? []).filter(
        (item) => item.confirm_status === 'pending' && item.ai_status !== 'not_generated',
      ),
    [run],
  )

  const progress = run?.total
    ? Math.round((run.processed / run.total) * 100)
    : 0

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={980}
      title={`检测落实 · ${rule?.title ?? ''}`}
      extra={
        <Space>
          {run && ['queued', 'running'].includes(run.status) && (
            <Button size="small" icon={<StopOutlined />} onClick={() => void handleCancel()}>
              取消
            </Button>
          )}
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={starting}
            onClick={() => void handleStart()}
          >
            {run ? '重新检测' : '开始检测'}
          </Button>
        </Space>
      }
    >
      {loading ? (
        <Typography.Text type="secondary">正在读取检测记录…</Typography.Text>
      ) : !run ? (
        <Alert
          type="info"
          showIcon
          message="还没有检测记录"
          description="检测范围完全按规则自己的生效范围展开：规则只落在某个封面，就只检测那个封面；规则是全局，就检测全库。"
        />
      ) : (
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="blue">{run.status}</Tag>
            <Tag>范围 {run.total} 条</Tag>
            <Tag color="green">AI 已落实 {run.covered}</Tag>
            <Tag color="gold">部分 {run.partial}</Tag>
            <Tag color="red">未落实 {run.missing}</Tag>
            <Tag>待确认 {run.pending}</Tag>
            {run.error_count > 0 && <Tag color="red">失败 {run.error_count}</Tag>}
            <Typography.Text type="secondary">
              v{run.rule_version} · {run.processed}/{run.total}
            </Typography.Text>
          </Space>
          {['queued', 'running'].includes(run.status) && (
            <Progress percent={progress} status="active" />
          )}
          {run.error_message && (
            <Alert type="error" showIcon message={run.error_message} />
          )}
          <Space wrap>
            <Button
              size="small"
              disabled={selectedKeys.length === 0 || confirming}
              loading={confirming}
              onClick={() => void handleConfirm(selectedKeys, 'covered')}
            >
              批量确认已落实（{selectedKeys.length}）
            </Button>
            <Button
              size="small"
              danger
              disabled={selectedKeys.length === 0 || confirming}
              loading={confirming}
              onClick={() => void handleConfirm(selectedKeys, 'missing')}
            >
              批量确认未落实
            </Button>
            <Typography.Text type="secondary">
              共 {pendingItems.length} 条待人工确认
            </Typography.Text>
          </Space>
          <Table
            size="small"
            rowKey="item_key"
            dataSource={run.items}
            pagination={{ pageSize: 20, hideOnSinglePage: true }}
            rowSelection={{
              selectedRowKeys: selectedKeys,
              onChange: (keys) => setSelectedKeys(keys as string[]),
              getCheckboxProps: (item) => ({
                disabled: item.confirm_status !== 'pending',
              }),
            }}
            columns={[
              {
                title: '资产',
                width: 210,
                render: (_value, item) => assetLabel(item),
              },
              {
                title: '提示词',
                render: (_value, item) => (
                  <Typography.Paragraph
                    type="secondary"
                    ellipsis={{ rows: 2 }}
                    style={{ marginBottom: 0, fontSize: 12 }}
                  >
                    {item.prompt || '（未生成）'}
                  </Typography.Paragraph>
                ),
              },
              {
                title: 'AI 判定',
                width: 110,
                render: (_value, item) => (
                  <Space direction="vertical" size={0}>
                    <Tag color={aiColor(item.ai_status)}>
                      {AI_LABELS[item.ai_status] ?? item.ai_status}
                    </Tag>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      {Math.round((item.ai_confidence || 0) * 100)}%
                    </Typography.Text>
                  </Space>
                ),
              },
              {
                title: '证据 / 缺项',
                width: 260,
                render: (_value, item) => (
                  <Typography.Paragraph
                    ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                    style={{ marginBottom: 0, fontSize: 12 }}
                  >
                    {(item.ai_evidence || []).join('；') ||
                      item.ai_missing?.join('；') ||
                      item.ai_reason ||
                      String(item.deterministic?.message ?? '') ||
                      '—'}
                  </Typography.Paragraph>
                ),
              },
              {
                title: '人工确认',
                width: 150,
                render: (_value, item) =>
                  item.confirm_status === 'confirmed' ? (
                    <Tag color={item.final_status === 'confirmed_covered' ? 'green' : 'red'}>
                      {FINAL_LABELS[item.final_status] ?? item.final_status}
                    </Tag>
                  ) : (
                    <Space size={4}>
                      <Button
                        size="small"
                        disabled={confirming}
                        onClick={() => void handleConfirm([item.item_key], 'covered')}
                      >
                        已落实
                      </Button>
                      <Button
                        size="small"
                        danger
                        disabled={confirming}
                        onClick={() => void handleConfirm([item.item_key], 'missing')}
                      >
                        未落实
                      </Button>
                    </Space>
                  ),
              },
            ]}
          />
        </Space>
      )}
    </Drawer>
  )
}
