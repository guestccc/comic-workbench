import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Button, Empty, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import PageHeader from '../components/PageHeader'
import PublishJobDetailModal from '../components/PublishJobDetailModal'
import PlatformLabel, { PLATFORM_OPTIONS } from '../components/PlatformIcon'
import { api, getErrorMessage } from '../api/client'
import {
  formatPublishTime,
  PUBLISH_MODE_META,
  PUBLISH_STATUS_META,
  resolvePublishMode,
} from '../utils/publishing'
import type {
  PublishJob,
  PublishJobStatus,
  PublishPlatform,
  Story,
} from '../types'

const STATUS_OPTIONS = (
  Object.keys(PUBLISH_STATUS_META) as PublishJobStatus[]
).map((status) => ({
  value: status,
  label: PUBLISH_STATUS_META[status].text,
}))

/**
 * 全局发布任务页：跨故事查看、筛选任务，并复用共享详情弹窗做人工修正。
 *
 * 这里不创建任务、不重发；重发仍回到章节发布面板，必须重新预览。
 */
export default function PublishJobsPage() {
  const { message } = App.useApp()
  const [jobs, setJobs] = useState<PublishJob[]>([])
  const [stories, setStories] = useState<Story[]>([])
  const [storyId, setStoryId] = useState<number | undefined>(undefined)
  const [status, setStatus] = useState<PublishJobStatus | undefined>(undefined)
  const [platform, setPlatform] = useState<PublishPlatform | undefined>(
    undefined,
  )
  const [loading, setLoading] = useState(false)
  const [detailJob, setDetailJob] = useState<PublishJob | null>(null)

  const storyNames = useMemo(
    () =>
      new Map(
        stories.map((story) => [
          story.id,
          story.name.trim() || `未命名故事 #${story.id}`,
        ]),
      ),
    [stories],
  )

  useEffect(() => {
    api
      .listStories()
      .then(setStories)
      .catch((error) => message.error(getErrorMessage(error)))
  }, [message])

  const loadJobs = useCallback(async () => {
    setLoading(true)
    try {
      const items = await api.listPublishJobs({
        storyId,
        status,
        platform,
        limit: 100,
      })
      setJobs(items)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [storyId, status, platform, message])

  useEffect(() => {
    void loadJobs()
  }, [loadJobs])

  const hasActiveJob = jobs.some(
    (job) => job.status === 'queued' || job.status === 'running',
  )

  useEffect(() => {
    if (!hasActiveJob) return
    const timer = window.setInterval(() => {
      void loadJobs()
    }, 5000)
    return () => window.clearInterval(timer)
  }, [hasActiveJob, loadJobs])

  const columns: ColumnsType<PublishJob> = [
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 150,
      render: (value: string) => formatPublishTime(value),
    },
    {
      title: '故事 / 章节',
      key: 'story',
      width: 180,
      render: (_, job) => {
        const name = storyNames.get(job.story_id)
        return (
          <Space direction="vertical" size={0}>
            <Typography.Text ellipsis style={{ maxWidth: 180 }}>
              {name ?? `故事 #${job.story_id}`}
            </Typography.Text>
            <Typography.Text type="secondary">
              第 {job.chapter_number} 章
            </Typography.Text>
          </Space>
        )
      },
    },
    {
      title: '平台',
      dataIndex: 'platform',
      width: 110,
      render: (value: PublishPlatform) => (
        <Tag>
          <PlatformLabel platform={value} size={14} />
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: PublishJobStatus) => (
        <Tag color={PUBLISH_STATUS_META[value].color}>
          {PUBLISH_STATUS_META[value].text}
        </Tag>
      ),
    },
    {
      title: '发布方式',
      key: 'mode',
      width: 110,
      render: (_, job) => {
        const mode = resolvePublishMode(job.payload.mode)
        return (
          <Space direction="vertical" size={0}>
            <Tag>{PUBLISH_MODE_META[mode].text}</Tag>
            <Typography.Text type="secondary">
              {mode === 'scheduled'
                ? formatPublishTime(job.scheduled_at)
                : '创建后立即'}
            </Typography.Text>
          </Space>
        )
      },
    },
    {
      title: '内容',
      key: 'payload',
      render: (_, job) => (
        <Space direction="vertical" size={0}>
          <span>{job.payload.title}</span>
          <Typography.Text type="secondary">
            {job.payload.images.length} 张图 ·{' '}
            {job.payload.tags.map((tag) => `#${tag}`).join(' ') || '无标签'}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '结果',
      key: 'result',
      render: (_, job) =>
        job.error_message ? (
          <Typography.Text type="danger" className="publish-job-result">
            {job.error_message}
          </Typography.Text>
        ) : job.external_url ? (
          <a href={job.external_url} target="_blank" rel="noreferrer">
            作品链接
          </a>
        ) : (
          '—'
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_, job) => (
        <Button size="small" onClick={() => setDetailJob(job)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="发布任务"
        description="跨故事查看抖音 / 小红书发布任务（定时 / 立即）；「待核对」必须到对应平台创作中心确认后再手动修正，不会自动重发。"
        extra={
          <Button
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => void loadJobs()}
          >
            刷新任务
          </Button>
        }
      />

      <Space wrap size={12} style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="全部故事"
          style={{ minWidth: 220 }}
          value={storyId}
          options={stories.map((story) => ({
            value: story.id,
            label: story.name.trim() || `未命名故事 #${story.id}`,
          }))}
          onChange={(value) => setStoryId(value)}
        />
        <Select
          allowClear
          placeholder="全部状态"
          style={{ minWidth: 140 }}
          value={status}
          options={STATUS_OPTIONS}
          onChange={(value) => setStatus(value)}
        />
        <Select
          allowClear
          placeholder="全部平台"
          style={{ minWidth: 140 }}
          value={platform}
          options={PLATFORM_OPTIONS}
          onChange={(value) => setPlatform(value)}
        />
        <Typography.Text type="secondary">
          共 {jobs.length} 条，最多显示最近 100 条
        </Typography.Text>
      </Space>

      <Table<PublishJob>
        size="small"
        rowKey="id"
        dataSource={jobs}
        columns={columns}
        loading={loading}
        pagination={false}
        scroll={{ x: 1100 }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="还没有发布任务"
            />
          ),
        }}
      />

      <PublishJobDetailModal
        job={detailJob}
        onClose={() => setDetailJob(null)}
        onUpdated={(updated) => {
          setDetailJob(updated)
          setJobs((items) =>
            items.map((item) => (item.id === updated.id ? updated : item)),
          )
        }}
      />
    </div>
  )
}
