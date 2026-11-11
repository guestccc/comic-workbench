import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Descriptions,
  Divider,
  Input,
  Modal,
  Space,
  Typography,
} from 'antd'
import { api, getErrorMessage } from '../api/client'
import PlatformLabel from './PlatformIcon'
import {
  formatPublishTime,
  PUBLISH_MODE_META,
  PUBLISH_PLATFORM_META,
  PUBLISH_STATUS_META,
  resolvePublishMode,
} from '../utils/publishing'
import type { PublishJob } from '../types'

interface PublishJobDetailModalProps {
  /** 为 null 时关闭弹窗 */
  job: PublishJob | null
  onClose: () => void
  /** 状态或链接变化后同步给调用方，避免两处各存一份 */
  onUpdated?: (job: PublishJob) => void
}

/**
 * 发布任务详情：状态、错误、作品链接回填、人工修正与日志。
 *
 * 章节发布面板和全局发布任务页共用这一个组件；改动只在这里发生。
 */
export default function PublishJobDetailModal({
  job,
  onClose,
  onUpdated,
}: PublishJobDetailModalProps) {
  const { message } = App.useApp()
  const [current, setCurrent] = useState<PublishJob | null>(job)
  const [externalUrl, setExternalUrl] = useState(job?.external_url ?? '')
  const [logText, setLogText] = useState('')
  const [logLoading, setLogLoading] = useState(false)
  const [patching, setPatching] = useState(false)
  const [fetchingLink, setFetchingLink] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const jobId = job?.id ?? null
  const platformLabel = job ? PUBLISH_PLATFORM_META[job.platform].text : '平台'
  const currentMode = current
    ? resolvePublishMode(current.payload.mode)
    : 'scheduled'

  useEffect(() => {
    setCurrent(job)
    setExternalUrl(job?.external_url ?? '')
    if (job == null) {
      setLogText('')
      return
    }
    let cancelled = false
    setLogLoading(true)
    api
      .getPublishJobLog(job.id)
      .then((log) => {
        if (!cancelled) setLogText(log.text)
      })
      .catch((error) => {
        if (!cancelled) message.error(getErrorMessage(error))
      })
      .finally(() => {
        if (!cancelled) setLogLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [jobId, message])

  const applyUpdated = (updated: PublishJob) => {
    setCurrent(updated)
    setExternalUrl(updated.external_url ?? '')
    onUpdated?.(updated)
  }

  const handlePatch = async (
    payload: { status?: 'scheduled' | 'failed' | 'published'; external_url?: string },
  ) => {
    if (current == null) return
    setPatching(true)
    try {
      const updated = await api.patchPublishJob(current.id, payload)
      applyUpdated(updated)
      message.success('任务已更新')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setPatching(false)
    }
  }

  const fetchLink = async () => {
    if (current == null) return
    setFetchingLink(true)
    try {
      const updated = await api.fetchPublishJobLink(current.id)
      applyUpdated(updated)
      message.success('已抓取作品链接')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setFetchingLink(false)
    }
  }

  const refresh = async () => {
    if (current == null) return
    setRefreshing(true)
    try {
      // 状态和日志分别拉取：日志读失败时，已拿到的状态仍然生效
      try {
        const updated = await api.getPublishJob(current.id)
        applyUpdated(updated)
        message.success(`已刷新：${PUBLISH_STATUS_META[updated.status].text}`)
      } catch (error) {
        message.error(getErrorMessage(error))
      }
      try {
        const log = await api.getPublishJobLog(current.id)
        setLogText(log.text)
      } catch (error) {
        message.error(getErrorMessage(error))
      }
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <Modal
      open={job != null}
      title="发布任务详情"
      width={760}
      footer={null}
      onCancel={onClose}
    >
      {current && (
        <div className="publish-job-detail">
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="任务号">
              {current.id.slice(0, 12)}
            </Descriptions.Item>
            <Descriptions.Item label="平台">
              <PlatformLabel platform={current.platform} />
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {PUBLISH_STATUS_META[current.status].text}
            </Descriptions.Item>
            <Descriptions.Item label="发布方式">
              {PUBLISH_MODE_META[currentMode].text}
            </Descriptions.Item>
            {currentMode === 'scheduled' && (
              <Descriptions.Item label="定时" span={2}>
                {formatPublishTime(current.payload.schedule_at)}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="退出码">
              {current.exit_code ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label="标题" span={2}>
              {current.payload.title}
            </Descriptions.Item>
            <Descriptions.Item label="标签" span={2}>
              {current.payload.tags.map((tag) => `#${tag}`).join(' ') || '无'}
            </Descriptions.Item>
          </Descriptions>

          {current.error_message && (
            <Alert
              type={
                current.status === 'failed'
                  ? 'error'
                  : current.status === 'unknown'
                    ? 'warning'
                    : 'info'
              }
              showIcon
              style={{ marginTop: 12 }}
              message={current.error_message}
            />
          )}

          <Space.Compact style={{ width: '100%', marginTop: 12 }}>
            <Input
              value={externalUrl}
              placeholder={`发布后可回填${platformLabel}作品链接`}
              onChange={(event) => setExternalUrl(event.target.value)}
            />
            <Button
              loading={patching}
              onClick={() => void handlePatch({ external_url: externalUrl })}
            >
              保存链接
            </Button>
            {['scheduled', 'unknown', 'published'].includes(current.status) && (
              <Button
                loading={fetchingLink}
                title={`用${platformLabel}账号的登录态读取创作中心作品列表，按标题匹配`}
                onClick={() => void fetchLink()}
              >
                抓取作品链接
              </Button>
            )}
          </Space.Compact>
          {current.status === 'scheduled' && (
            <Typography.Text
              type="secondary"
              style={{ display: 'block', marginTop: 4 }}
            >
              定时任务要等平台实际发布后再抓取，未发布前只会提示未找到作品。
            </Typography.Text>
          )}

          {current.status === 'unknown' && (
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 12 }}
              message={`状态未知，请先到${platformLabel}创作中心核对，再手动修正`}
              description="超时或未观察到成功标记时不会自动重试，避免重复发布。"
              action={
                <Space direction="vertical">
                  <Button
                    size="small"
                    loading={patching}
                    onClick={() =>
                      void handlePatch({
                        status:
                          currentMode === 'immediate'
                            ? 'published'
                            : 'scheduled',
                      })
                    }
                  >
                    {currentMode === 'immediate' ? '确认已发布' : '确认已定时'}
                  </Button>
                  <Button
                    size="small"
                    danger
                    loading={patching}
                    onClick={() => void handlePatch({ status: 'failed' })}
                  >
                    确认未发出
                  </Button>
                </Space>
              }
            />
          )}

          {['scheduled', 'published'].includes(current.status) && (
            <Button
              style={{ marginTop: 12 }}
              loading={patching}
              onClick={() => void handlePatch({ status: 'published' })}
              disabled={current.status === 'published'}
            >
              标记为已发布
            </Button>
          )}

          <Divider titlePlacement="start" plain>
            发布日志
          </Divider>
          {logLoading ? (
            <Typography.Text type="secondary">读取中…</Typography.Text>
          ) : logText ? (
            <pre className="publish-log">{logText}</pre>
          ) : (
            <Typography.Text type="secondary">暂无日志</Typography.Text>
          )}

          <div style={{ marginTop: 12, textAlign: 'right' }}>
            <Button loading={refreshing} onClick={() => void refresh()}>
              刷新状态与日志
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
