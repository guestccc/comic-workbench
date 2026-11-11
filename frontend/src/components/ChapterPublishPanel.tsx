import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  App,
  Button,
  DatePicker,
  Descriptions,
  Divider,
  Empty,
  Image,
  Input,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd'
import {
  CloudUploadOutlined,
  LoginOutlined,
  RedoOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  SendOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { api, ApiError, getErrorMessage } from '../api/client'
import PublishJobDetailModal from './PublishJobDetailModal'
import PublishPreflightModal from './PublishPreflightModal'
import PlatformLabel, { PLATFORM_OPTIONS } from './PlatformIcon'
import {
  formatPublishTime,
  formatXhsDeclaration,
  PUBLISH_MODE_META,
  PUBLISH_PLATFORM_META,
  PUBLISH_SCHEDULE_MAX_DAYS,
  PUBLISH_SCHEDULE_MIN_LEAD_HOURS,
  PUBLISH_STATUS_META,
  resolvePublishMode,
} from '../utils/publishing'
import type {
  PreflightAction,
  PublishAccount,
  PublishJob,
  PublishMode,
  PublishPlatform,
  PublishPreview,
  Story,
  StoryChapterPostConfig,
  XhsDeclarationOptions,
} from '../types'

interface ChapterPublishPanelProps {
  storyId: number
  chapterNumber: number
  chapterTitle: string
  /** 故事级小红书发布设置（合集 / AI 声明）从这里读取与保存 */
  story: Story
  savedConfig: StoryChapterPostConfig | null
  /** 表单有未保存修改时不允许预览，避免发布内容与界面不一致 */
  dirty: boolean
  /** 检查弹窗里「去上传 / 去设置别名」切换到对应 tab */
  onNavigateTab?: (tab: string) => void
  /** 保存故事级小红书设置后把最新的故事回写详情页 */
  onStoryUpdated: (story: Story) => void
}

const ACCOUNT_STATUS_META: Record<
  PublishAccount['status'],
  { text: string; color: string }
> = {
  unknown: { text: '未检测', color: 'default' },
  valid: { text: '已登录', color: 'success' },
  invalid: { text: '登录失效', color: 'error' },
}

function defaultSchedule(): Dayjs {
  return dayjs().add(3, 'hour').second(0).millisecond(0)
}

/**
 * 章节发布面板：抖音 / 小红书图文定时发布。
 *
 * 载荷只由后端预览接口返回；发布时必须带上预览哈希，确保发出去的
 * 就是用户刚刚确认的那一版标题、正文、标签和图片顺序。
 */
export default function ChapterPublishPanel({
  storyId,
  chapterNumber,
  chapterTitle,
  story,
  savedConfig,
  dirty,
  onNavigateTab,
  onStoryUpdated,
}: ChapterPublishPanelProps) {
  const { message } = App.useApp()
  const [platform, setPlatform] = useState<PublishPlatform>('douyin')
  const [mode, setMode] = useState<PublishMode>('scheduled')
  const [accounts, setAccounts] = useState<PublishAccount[]>([])
  const [accountId, setAccountId] = useState<number | null>(null)
  const [scheduleAt, setScheduleAt] = useState<Dayjs>(defaultSchedule)
  const [preview, setPreview] = useState<PublishPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [preflightOpen, setPreflightOpen] = useState(false)
  const [preflightAction, setPreflightAction] =
    useState<PreflightAction | null>(null)
  const [checking, setChecking] = useState(false)
  const [loggingIn, setLoggingIn] = useState(false)
  const [jobs, setJobs] = useState<PublishJob[]>([])
  const [jobsLoading, setJobsLoading] = useState(false)
  const [detailJob, setDetailJob] = useState<PublishJob | null>(null)
  // 故事级小红书设置：编辑态与已保存值分开，保存前不允许预览
  const [xhsDeclaration, setXhsDeclaration] = useState(story.xhs_declaration)
  const [xhsRepostSource, setXhsRepostSource] = useState(
    story.xhs_repost_source,
  )
  // 声明可选项由后端给出，前端不自行维护平台文案
  const [declarationOptions, setDeclarationOptions] =
    useState<XhsDeclarationOptions | null>(null)
  const [savingXhsSettings, setSavingXhsSettings] = useState(false)
  const jobsRequestRef = useRef(0)
  const platformRef = useRef(platform)
  platformRef.current = platform
  const modeRef = useRef(mode)
  modeRef.current = mode

  const account = accounts.find((item) => item.id === accountId) ?? null
  const platformLabel = PUBLISH_PLATFORM_META[platform].text
  const locked = dirty || savedConfig == null
  const xhsSettingsDirty =
    xhsDeclaration !== story.xhs_declaration ||
    xhsRepostSource.trim() !== story.xhs_repost_source
  // 只有小红书发布才读取这几项设置，切到抖音时未保存的编辑不阻塞预览
  const xhsSettingsBlocked = platform === 'xiaohongshu' && xhsSettingsDirty
  // 「来源转载」必须带媒体名，缺了就保存不了（后端同规则拒绝）
  const xhsRepostMissing =
    declarationOptions != null &&
    xhsDeclaration === declarationOptions.repost_value &&
    xhsRepostSource.trim() === ''

  const loadJobs = useCallback(async () => {
    const token = ++jobsRequestRef.current
    setJobsLoading(true)
    try {
      const items = await api.listPublishJobs({
        storyId,
        chapterNumber,
        platform,
        limit: 20,
      })
      // 切换平台后旧请求可能后到，不能覆盖当前平台的任务列表
      if (token !== jobsRequestRef.current) return
      setJobs(items)
    } catch (error) {
      if (token === jobsRequestRef.current) {
        message.error(getErrorMessage(error))
      }
    } finally {
      if (token === jobsRequestRef.current) {
        setJobsLoading(false)
      }
    }
  }, [storyId, chapterNumber, platform, message])

  // 账号按平台隔离：切换平台时重新拉取，旧请求返回后直接丢弃
  useEffect(() => {
    let cancelled = false
    api
      .listPublishAccounts(platform)
      .then((items) => {
        if (cancelled) return
        setAccounts(items)
        setAccountId(items[0]?.id ?? null)
      })
      .catch((error) => {
        if (!cancelled) message.error(getErrorMessage(error))
      })
    return () => {
      cancelled = true
    }
  }, [platform, message])

  useEffect(() => {
    void loadJobs()
  }, [loadJobs])

  // 来源、平台、发布方式变化或重新保存后，旧预览不再可信
  useEffect(() => {
    setPreview(null)
    setPreflightOpen(false)
  }, [
    chapterNumber,
    platform,
    mode,
    savedConfig?.updated_at,
    dirty,
    story.xhs_declaration,
    story.xhs_repost_source,
  ])

  // 故事级小红书设置以外层故事为准，保存成功后回填编辑态
  useEffect(() => {
    setXhsDeclaration(story.xhs_declaration)
    setXhsRepostSource(story.xhs_repost_source)
  }, [story.xhs_declaration, story.xhs_repost_source])

  // 声明选项属于平台契约，只从后端取一次
  useEffect(() => {
    let cancelled = false
    api
      .getXhsDeclarationOptions()
      .then((result) => {
        if (!cancelled) setDeclarationOptions(result)
      })
      .catch((error) => {
        if (!cancelled) message.error(getErrorMessage(error))
      })
    return () => {
      cancelled = true
    }
  }, [message])

  const hasActiveJob = useMemo(
    () => jobs.some((job) => job.status === 'queued' || job.status === 'running'),
    [jobs],
  )

  useEffect(() => {
    if (!hasActiveJob) return
    const timer = window.setInterval(() => {
      void loadJobs()
    }, 5000)
    return () => window.clearInterval(timer)
  }, [hasActiveJob, loadJobs])

  const handleCheck = async () => {
    if (account == null) return
    setChecking(true)
    try {
      const updated = await api.checkPublishAccount(account.id)
      setAccounts((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      )
      if (updated.status === 'valid') {
        message.success('账号登录有效')
      } else {
        message.warning(`账号未登录或 Cookie 已失效，请先点「登录${platformLabel}」`)
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setChecking(false)
    }
  }

  const handleLogin = async () => {
    if (account == null) return
    setLoggingIn(true)
    try {
      const result = await api.loginPublishAccount(account.id)
      message.info(result.message, 8)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoggingIn(false)
    }
  }

  const requestPreview = async (
    targetAccountId: number,
    targetSchedule: Dayjs,
    targetMode: PublishMode,
  ) => {
    const targetPlatform = platformRef.current
    setPreviewing(true)
    try {
      const result = await api.previewPublish({
        story_id: storyId,
        chapter_number: chapterNumber,
        platform: targetPlatform,
        account_id: targetAccountId,
        publish_mode: targetMode,
        schedule_at:
          targetMode === 'scheduled' ? targetSchedule.toISOString() : null,
      })
      if (
        targetPlatform !== platformRef.current ||
        targetMode !== modeRef.current
      ) {
        return
      }
      setPreview(result)
      if (result.errors.length === 0) {
        message.success('预览已生成，确认无误后再发布')
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setPreviewing(false)
    }
  }

  const handlePreview = async () => {
    if (accountId == null) {
      message.warning('还没有可用的发布账号')
      return
    }
    if (xhsSettingsBlocked) {
      message.warning('小红书发布设置还没保存，请先保存设置再预览')
      return
    }
    await requestPreview(accountId, scheduleAt, mode)
  }

  /** 保存故事级小红书设置；保存后预览哈希会变化，需重新预览。 */
  const handleSaveXhsSettings = async () => {
    if (xhsRepostMissing) {
      message.warning('选择「来源转载」时必须填写来源媒体名')
      return
    }
    setSavingXhsSettings(true)
    try {
      const updated = await api.updateStoryXiaohongshu(story.id, {
        declaration: xhsDeclaration,
        repost_source: xhsRepostSource.trim(),
      })
      onStoryUpdated(updated)
      message.success('小红书发布设置已保存，请重新预览')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSavingXhsSettings(false)
    }
  }

  /**
   * 失败任务重新发起：只回填上次账号与定时并自动预览。
   * 仍要用户确认预览后手动创建任务，不做后端 retry，也不跳过预览。
   */
  const handleReuse = async (job: PublishJob) => {
    if (locked) {
      message.warning('请先保存本章文案，再重新发起')
      return
    }
    if (job.platform !== platform) {
      message.warning('发布记录与当前平台不一致，请刷新后再试')
      return
    }
    const targetAccountId = accounts.some((item) => item.id === job.account_id)
      ? job.account_id
      : accounts[0]?.id
    if (targetAccountId == null) {
      message.warning('还没有可用的发布账号')
      return
    }
    const jobMode = resolvePublishMode(job.payload.mode)
    const previous = dayjs(job.scheduled_at)
    const nextSchedule = previous.isAfter(dayjs().add(2, 'hour'))
      ? previous.second(0).millisecond(0)
      : defaultSchedule()
    setAccountId(targetAccountId)
    setMode(jobMode)
    setScheduleAt(nextSchedule)
    setPreview(null)
    message.info(
      jobMode === 'immediate'
        ? '已回填上次账号与立即发布方式，确认预览后再创建任务'
        : '已回填上次账号与定时，确认预览后再创建任务',
      6,
    )
    await requestPreview(targetAccountId, nextSchedule, jobMode)
  }

  const handlePublish = () => {
    if (preview == null || preview.payload_hash == null) {
      message.warning('请先生成预览')
      return
    }
    // 有阻塞项也打开弹窗：检查结果与修复入口都在里面
    setPreflightOpen(true)
  }

  /** 弹窗确认后创建任务；载荷仍以预览哈希为准。 */
  const createJob = async () => {
    if (preview == null || preview.payload_hash == null) return
    const immediate = resolvePublishMode(preview.publish_mode) === 'immediate'
    setSubmitting(true)
    try {
      const job = await api.createPublishJob({
        story_id: storyId,
        chapter_number: chapterNumber,
        platform: preview.platform,
        account_id: preview.account.id,
        publish_mode: resolvePublishMode(preview.publish_mode),
        schedule_at: immediate ? null : preview.schedule_at,
        preview_hash: preview.payload_hash,
        confirm: true,
      })
      setPreflightOpen(false)
      setPreview(null)
      setJobs((items) => [job, ...items])
      message.success(
        `发布任务已创建，正在上传到${PUBLISH_PLATFORM_META[job.platform].text}`,
      )
    } catch (error) {
      if (error instanceof ApiError && error.code === 'PUBLISH_PREVIEW_STALE') {
        setPreflightOpen(false)
        setPreview(null)
        message.error('内容已变化，请重新预览后再发布')
      } else {
        message.error(getErrorMessage(error))
      }
    } finally {
      setSubmitting(false)
    }
  }

  /** 弹窗内修复：加别名 / 检测登录后必须重新预览，旧哈希随即失效。 */
  const handlePreflightAction = async (action: PreflightAction) => {
    if (preview == null || preflightAction != null) return
    if (action === 'open_zhihu' || action === 'open_chapters') {
      setPreflightOpen(false)
      onNavigateTab?.(action === 'open_zhihu' ? 'zhihu' : 'chapters')
      return
    }
    if (action === 'open_post_config') {
      setPreflightOpen(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }

    const targetMode = resolvePublishMode(preview.publish_mode)
    const targetSchedule = preview.schedule_at
      ? dayjs(preview.schedule_at)
      : scheduleAt
    setPreflightAction(action)
    try {
      if (action === 'check_login') {
        const updated = await api.checkPublishAccount(preview.account.id)
        setAccounts((items) =>
          items.map((item) => (item.id === updated.id ? updated : item)),
        )
        if (updated.status === 'valid') {
          message.success('账号登录有效')
        } else {
          message.warning(
            `账号未登录或 Cookie 已失效，请先点「登录${platformLabel}」`,
          )
        }
      } else if (action === 'stamp_alias') {
        const result = await api.stampStoryAlias(storyId, {
          chapter_number: chapterNumber,
        })
        if (result.failed > 0) {
          message.warning(
            `已加别名 ${result.stamped} 张，失败 ${result.failed} 张，请逐项检查`,
          )
        } else {
          message.success(
            `已给 ${result.stamped} 张图片加上【${result.alias}】`,
          )
        }
      }
      await requestPreview(preview.account.id, targetSchedule, targetMode)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setPreflightAction(null)
    }
  }

  const openDetail = (job: PublishJob) => {
    setDetailJob(job)
  }

  const applyUpdated = (updated: PublishJob) => {
    setDetailJob(updated)
    setJobs((items) =>
      items.map((item) => (item.id === updated.id ? updated : item)),
    )
  }

  return (
    <div className="publish-panel">
      <div className="publish-panel-header">
        <div>
          <Typography.Title level={5} style={{ margin: 0 }}>
            <PlatformLabel platform={platform} suffix="图文发布" />
          </Typography.Title>
          <Typography.Text type="secondary">
            第 {chapterNumber} 章 · {chapterTitle} · 封面 → 正文 → 引导卡
          </Typography.Text>
        </div>
        <Space wrap>
          <Select
            value={platform}
            style={{ minWidth: 130 }}
            options={PLATFORM_OPTIONS}
            onChange={(value: PublishPlatform) => {
              if (value === platform) return
              setPlatform(value)
              setPreview(null)
              // 账号与记录都按平台隔离，切换时先清空，避免短暂显示另一平台的账号
              setAccounts([])
              setAccountId(null)
              setJobs([])
            }}
          />
          <Select
            value={accountId ?? undefined}
            style={{ minWidth: 200 }}
            placeholder="发布账号"
            options={accounts.map((item) => ({
              value: item.id,
              label: `${item.display_name}（${item.account_name}）`,
            }))}
            onChange={(value) => setAccountId(value)}
          />
          {account && (
            <Tag color={ACCOUNT_STATUS_META[account.status].color}>
              {ACCOUNT_STATUS_META[account.status].text}
            </Tag>
          )}
          <Button
            icon={<LoginOutlined />}
            loading={loggingIn}
            disabled={account == null}
            onClick={() => void handleLogin()}
          >
            登录<PlatformLabel platform={platform} />
          </Button>
          <Button
            icon={<SafetyCertificateOutlined />}
            loading={checking}
            disabled={account == null}
            onClick={() => void handleCheck()}
          >
            检测登录
          </Button>
        </Space>
      </div>

      {locked && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={
            dirty
              ? '文案有未保存修改，请先「保存本章文案」再预览发布'
              : '本章还没有保存发文配置，请先填写标题与正文'
          }
        />
      )}

      {platform === 'xiaohongshu' && (
        <div className="publish-xhs-settings">
          <div>
            <Typography.Text strong>小红书发布设置</Typography.Text>
            <Typography.Text type="secondary">
              {' '}
              · 故事级，本故事所有章节共用
            </Typography.Text>
          </div>
          <Space wrap size={12}>
            <Space size={6}>
              <Typography.Text>声明</Typography.Text>
              <Select
                value={xhsDeclaration}
                style={{ width: 180 }}
                loading={declarationOptions == null}
                options={declarationOptions?.options ?? []}
                onChange={setXhsDeclaration}
              />
            </Space>
            {declarationOptions != null &&
              xhsDeclaration === declarationOptions.repost_value && (
                <Space size={6}>
                  <Typography.Text>来源媒体</Typography.Text>
                  <Input
                    value={xhsRepostSource}
                    maxLength={64}
                    allowClear
                    placeholder="填写转载来源"
                    status={xhsRepostMissing ? 'error' : undefined}
                    style={{ width: 180 }}
                    onChange={(event) =>
                      setXhsRepostSource(event.target.value)
                    }
                    onPressEnter={() => void handleSaveXhsSettings()}
                  />
                </Space>
              )}
            <Button
              size="small"
              icon={<SaveOutlined />}
              loading={savingXhsSettings}
              disabled={!xhsSettingsDirty}
              onClick={() => void handleSaveXhsSettings()}
            >
              保存设置
            </Button>
          </Space>
          <Typography.Text type="secondary">
            内容声明按平台文案精确匹配，选「来源转载」时必须填写来源媒体；
            声明设置失败时 sau 会拒绝发布。合集暂未接入。
          </Typography.Text>
        </div>
      )}

      {xhsSettingsBlocked && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="小红书发布设置未保存，保存后才能预览发布"
        />
      )}

      <Space wrap size={12} className="publish-schedule">
        <Typography.Text strong>发布方式</Typography.Text>
        <Segmented
          value={mode}
          options={[
            { label: '定时发布', value: 'scheduled' },
            { label: '立即发布', value: 'immediate' },
          ]}
          onChange={(value) => {
            setMode(value as PublishMode)
            setPreview(null)
          }}
        />
        {mode === 'scheduled' ? (
          <>
            <DatePicker
              showTime={{ format: 'HH:mm' }}
              format="YYYY-MM-DD HH:mm"
              value={scheduleAt}
              minDate={dayjs()
                .add(PUBLISH_SCHEDULE_MIN_LEAD_HOURS, 'hour')
                .add(1, 'minute')}
              maxDate={dayjs().add(PUBLISH_SCHEDULE_MAX_DAYS, 'day')}
              allowClear={false}
              onChange={(value) => {
                setScheduleAt(value ?? defaultSchedule())
                setPreview(null)
              }}
            />
            <Typography.Text type="secondary">
              最早为当前时间 {PUBLISH_SCHEDULE_MIN_LEAD_HOURS} 小时后、最晚{' '}
              {PUBLISH_SCHEDULE_MAX_DAYS} 天内；这是{platformLabel}
              平台的定时发布，不是本地排队。
            </Typography.Text>
          </>
        ) : (
          <Typography.Text type="danger">
            创建任务后立即上传并发布，成功即对读者可见，不可撤回。
          </Typography.Text>
        )}
      </Space>

      <Space wrap style={{ marginBottom: 12 }}>
        <Button
          type="primary"
          icon={<CloudUploadOutlined />}
          loading={previewing}
          disabled={locked || accountId == null || xhsSettingsBlocked}
          onClick={() => void handlePreview()}
        >
          {preview ? '重新预览' : '预览发布内容'}
        </Button>
        <Button
          icon={<SendOutlined />}
          loading={submitting}
          disabled={locked || preview == null || preview.payload_hash == null}
          onClick={handlePublish}
        >
          {mode === 'immediate' ? '创建立即发布任务' : '创建定时发布任务'}
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => void loadJobs()}
          loading={jobsLoading}
        >
          刷新任务
        </Button>
      </Space>

      {preview && (
        <div className="publish-preview">
          {preview.errors.length > 0 && (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 8 }}
              message="不能发布"
              description={
                <ul className="publish-issue-list">
                  {preview.errors.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              }
            />
          )}
          {preview.warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 8 }}
              message="发布前请确认"
              description={
                <ul className="publish-issue-list">
                  {preview.warnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              }
            />
          )}
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="标题">
              {preview.title}（{preview.title_length} 字）
            </Descriptions.Item>
            <Descriptions.Item label="正文">
              {preview.note_length} 字
            </Descriptions.Item>
            <Descriptions.Item label="标签">
              {preview.tags.length > 0
                ? preview.tags.map((tag) => <Tag key={tag}>#{tag}</Tag>)
                : '无'}
            </Descriptions.Item>
            <Descriptions.Item label="图片">
              {preview.image_count} 张
            </Descriptions.Item>
            <Descriptions.Item label="账号">
              {preview.account.display_name}（{preview.account.account_name}）
            </Descriptions.Item>
            {preview.platform === 'xiaohongshu' && (
              <Descriptions.Item label="内容声明">
                {formatXhsDeclaration(preview.declaration, preview.repost_source)}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="发布方式">
              {PUBLISH_MODE_META[resolvePublishMode(preview.publish_mode)].text}
            </Descriptions.Item>
            {resolvePublishMode(preview.publish_mode) === 'scheduled' && (
              <Descriptions.Item label="平台定时">
                {formatPublishTime(preview.schedule_at)}
              </Descriptions.Item>
            )}
          </Descriptions>

          <Divider titlePlacement="start" plain>
            正文预览
          </Divider>
          <div className="publish-note-preview">{preview.note || '（空正文）'}</div>

          <Divider titlePlacement="start" plain>
            图片顺序
          </Divider>
          <Image.PreviewGroup>
            <div className="publish-image-grid">
              {preview.images.map((image, index) => (
                <div key={`${image.url}-${index}`} className="publish-image-item">
                  <Image src={image.url} width={120} height={160} />
                  <span>
                    {index + 1}. {image.label}
                  </span>
                </div>
              ))}
            </div>
          </Image.PreviewGroup>
        </div>
      )}

      <Divider titlePlacement="start" plain>
        本章发布记录
      </Divider>
      {jobs.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="还没有发布任务"
        />
      ) : (
        <Spin spinning={jobsLoading}>
          <div className="publish-job-list">
            {jobs.map((job) => {
              const jobMode = resolvePublishMode(job.payload.mode)
              return (
                <div key={job.id} className="publish-job-item">
                  <div className="publish-job-item-head">
                    <Space size={8} wrap>
                      <Tag color={PUBLISH_STATUS_META[job.status].color}>
                        {PUBLISH_STATUS_META[job.status].text}
                      </Tag>
                      <Typography.Text type="secondary">
                        {PUBLISH_MODE_META[jobMode].text}
                        {jobMode === 'scheduled'
                          ? ` · ${formatPublishTime(job.scheduled_at)}`
                          : ''}
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        创建 {formatPublishTime(job.created_at)}
                      </Typography.Text>
                    </Space>
                    <Space size={4}>
                      {job.status === 'failed' && (
                        <Button
                          size="small"
                          icon={<RedoOutlined />}
                          disabled={locked || previewing}
                          onClick={() => void handleReuse(job)}
                        >
                          重新发起
                        </Button>
                      )}
                      <Button size="small" onClick={() => openDetail(job)}>
                        详情
                      </Button>
                    </Space>
                  </div>
                  <div className="publish-job-item-title">
                    {job.payload.title}
                    <Typography.Text type="secondary">
                      {' '}
                      · {job.payload.images.length} 张图 ·{' '}
                      {job.payload.tags.map((tag) => `#${tag}`).join(' ') ||
                        '无标签'}
                    </Typography.Text>
                  </div>
                  {job.error_message ? (
                    <Typography.Text type="danger" className="publish-job-result">
                      {job.error_message}
                    </Typography.Text>
                  ) : job.external_url ? (
                    <a href={job.external_url} target="_blank" rel="noreferrer">
                      作品链接
                    </a>
                  ) : null}
                </div>
              )
            })}
          </div>
        </Spin>
      )}

      <PublishPreflightModal
        open={preflightOpen}
        chapterNumber={chapterNumber}
        preview={preview}
        submitting={submitting}
        actionPending={preflightAction}
        onClose={() => {
          if (submitting) return
          setPreflightOpen(false)
        }}
        onConfirm={() => void createJob()}
        onAction={(action) => void handlePreflightAction(action)}
      />

      <PublishJobDetailModal
        job={detailJob}
        onClose={() => setDetailJob(null)}
        onUpdated={applyUpdated}
      />
    </div>
  )
}
