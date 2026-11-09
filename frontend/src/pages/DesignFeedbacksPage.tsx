import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Collapse,
  Divider,
  Drawer,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Select,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  DeleteOutlined,
  EditOutlined,
  PlusCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'

import DesignRulePanel from '../components/DesignRulePanel'
import PageHeader from '../components/PageHeader'
import ImageUpload from '../components/ImageUpload'
import { api, getErrorMessage } from '../api/client'
import type {
  DesignFeedback,
  DesignFeedbackApplication,
  DesignFeedbackApplicationPayload,
  DesignFeedbackCategory,
  DesignFeedbackDetail,
  DesignFeedbackPayload,
  DesignFeedbackPriority,
  DesignFeedbackRuleTarget,
  DesignFeedbackScope,
  DesignFeedbackSource,
  DesignFeedbackStatus,
  DesignFeedbackTargetType,
  Story,
} from '../types'

const SOURCE_LABELS: Record<DesignFeedbackSource, string> = {
  xiaohongshu: '小红书',
  manual: '手动',
}

const CATEGORY_LABELS: Record<DesignFeedbackCategory, string> = {
  cover: '封面',
  comic: '漫画设计',
  title: '标题',
  color: '色彩',
  expression: '表情',
  text: '文字',
  pacing: '节奏',
  other: '其他',
}

const SCOPE_LABELS: Record<DesignFeedbackScope, string> = {
  global: '全局',
  story: '指定故事',
  chapter: '指定章节',
}

const PRIORITY_LABELS: Record<DesignFeedbackPriority, string> = {
  low: '低',
  medium: '中',
  high: '高',
}

const STATUS_LABELS: Record<DesignFeedbackStatus, string> = {
  open: '待处理',
  applied: '已应用',
  verified: '已验证',
  archived: '不适用',
}

const RULE_TARGET_LABELS: Record<DesignFeedbackRuleTarget, string> = {
  cover: '封面规则',
  comic: '正文 / 漫画规则',
  all: '封面 + 正文',
}

const TARGET_LABELS: Record<DesignFeedbackTargetType, string> = {
  cover: '章节封面',
  page: '正文页',
  guide: '引导卡',
  character: '角色卡',
  other: '其他',
}

const STATUS_COLORS: Record<DesignFeedbackStatus, string> = {
  open: 'gold',
  applied: 'blue',
  verified: 'green',
  archived: 'default',
}

const PRIORITY_COLORS: Record<DesignFeedbackPriority, string> = {
  high: 'red',
  medium: 'orange',
  low: 'default',
}

function optionsFrom<T extends string>(
  labels: Record<T, string>,
): { value: T; label: string }[] {
  return (Object.entries(labels) as [T, string][]).map(([value, label]) => ({
    value,
    label,
  }))
}

function scopeText(feedback: DesignFeedback): string {
  if (feedback.scope === 'global') return '全局'
  if (feedback.scope === 'story') {
    return `故事 · ${feedback.story_name ?? '已删除'}`
  }
  return `第${feedback.chapter_number ?? '?'}章 · ${
    feedback.story_name ?? '已删除'
  }`
}

function targetText(application: DesignFeedbackApplication): string {
  const story = application.story_name ?? `故事 ${application.story_id}`
  if (application.target_type === 'page') {
    return `${story} · 正文第${application.page_number ?? '?'}页`
  }
  if (application.target_type === 'cover' || application.target_type === 'guide') {
    return `${story} · 第${application.chapter_number ?? '?'}章 · ${
      TARGET_LABELS[application.target_type]
    }`
  }
  return `${story} · ${TARGET_LABELS[application.target_type]}`
}

interface FeedbackFormValues {
  title?: string
  content: string
  source: DesignFeedbackSource
  source_url?: string
  category: DesignFeedbackCategory
  scope: DesignFeedbackScope
  story_id?: number
  chapter_number?: number
  tags?: string[]
  priority: DesignFeedbackPriority
  status?: DesignFeedbackStatus
}

interface ApplicationFormValues {
  target_type: DesignFeedbackTargetType
  story_id: number
  chapter_number?: number
  page_number?: number
  summary: string
  before_prompt?: string
  after_prompt?: string
}

export default function DesignFeedbacksPage() {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm<FeedbackFormValues>()
  const [applicationForm] = Form.useForm<ApplicationFormValues>()

  const [feedbacks, setFeedbacks] = useState<DesignFeedback[]>([])
  const [stories, setStories] = useState<Story[]>([])
  const [loading, setLoading] = useState(false)
  const [keywordDraft, setKeywordDraft] = useState('')
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<DesignFeedbackStatus>()
  const [categoryFilter, setCategoryFilter] =
    useState<DesignFeedbackCategory>()
  const [storyFilter, setStoryFilter] = useState<number>()

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<DesignFeedback | null>(null)
  const [saving, setSaving] = useState(false)
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null)
  const [screenshotFilename, setScreenshotFilename] = useState<string | null>(
    null,
  )

  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState<DesignFeedbackDetail | null>(null)

  const [applicationOpen, setApplicationOpen] = useState(false)
  const [applicationSaving, setApplicationSaving] = useState(false)
  const [beforeImageUrl, setBeforeImageUrl] = useState<string | null>(null)
  const [afterImageUrl, setAfterImageUrl] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [feedbackList, storyList] = await Promise.all([
        api.listDesignFeedbacks({
          status: statusFilter,
          category: categoryFilter,
          story_id: storyFilter,
          keyword,
        }),
        api.listStories(),
      ])
      setFeedbacks(feedbackList)
      setStories(storyList)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, categoryFilter, storyFilter, keyword])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({
      source: 'xiaohongshu',
      category: 'cover',
      priority: 'medium',
      scope: 'global',
      tags: [],
    })
    setScreenshotUrl(null)
    setScreenshotFilename(null)
    setFormOpen(true)
  }

  const openEdit = (feedback: DesignFeedback) => {
    setEditing(feedback)
    form.resetFields()
    form.setFieldsValue({
      title: feedback.title,
      content: feedback.content,
      source: feedback.source,
      source_url: feedback.source_url,
      category: feedback.category,
      scope: feedback.scope,
      story_id: feedback.story_id ?? undefined,
      chapter_number: feedback.chapter_number ?? undefined,
      tags: feedback.tags,
      priority: feedback.priority,
      status: feedback.status,
    })
    setScreenshotUrl(feedback.screenshot_url)
    setScreenshotFilename(feedback.screenshot_filename)
    setFormOpen(true)
  }

  const uploadScreenshot = async (file: File) => {
    try {
      const result = await api.uploadCover(file)
      setScreenshotUrl(result.url)
      setScreenshotFilename(result.filename)
      message.success('截图已上传')
    } catch (error) {
      message.error(getErrorMessage(error))
      throw error
    }
  }

  const saveFeedback = async () => {
    let values: FeedbackFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    const content = (values.content ?? '').trim()
    if (!content && !screenshotFilename) {
      message.warning('截图和建议文字至少提供一个')
      return
    }
    const scope = values.scope
    const storyId = scope === 'global' ? null : (values.story_id ?? null)
    const chapterNumber =
      scope === 'chapter' ? (values.chapter_number ?? null) : null
    const payload: DesignFeedbackPayload = {
      title:
        values.title === undefined
          ? (editing?.title ?? '')
          : values.title.trim(),
      content,
      source: values.source,
      source_url: values.source_url?.trim() ?? '',
      screenshot_filename: screenshotFilename,
      category: values.category,
      scope,
      story_id: storyId,
      chapter_number: chapterNumber,
      tags: values.tags ?? [],
      priority: values.priority,
    }
    setSaving(true)
    try {
      if (editing) {
        await api.updateDesignFeedback(editing.id, {
          ...payload,
          status: values.status ?? editing.status,
        })
        message.success('建议已更新')
      } else {
        await api.createDesignFeedback(payload)
        message.success('建议已添加')
      }
      setFormOpen(false)
      await load()
      if (detail && editing && detail.id === editing.id) {
        const refreshed = await api.getDesignFeedback(detail.id)
        setDetail(refreshed)
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const openDetail = async (feedback: DesignFeedback) => {
    setDetailOpen(true)
    setDetailLoading(true)
    try {
      const data = await api.getDesignFeedback(feedback.id)
      setDetail(data)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setDetailLoading(false)
    }
  }

  const refreshDetail = async () => {
    if (!detail) return
    const data = await api.getDesignFeedback(detail.id)
    setDetail(data)
  }

  const deleteFeedback = (feedback: DesignFeedback) => {
    modal.confirm({
      title: '删除这条设计建议？',
      content: '应用记录和上传的截图也会一起删除，无法恢复。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await api.deleteDesignFeedback(feedback.id)
          if (detail?.id === feedback.id) {
            setDetailOpen(false)
            setDetail(null)
          }
          message.success('建议已删除')
          await load()
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }


  const openApplication = () => {
    if (!detail) return
    if (stories.length === 0) {
      message.warning('还没有故事，无法记录应用')
      return
    }
    applicationForm.resetFields()
    applicationForm.setFieldsValue({
      target_type: 'cover',
      story_id: detail.story_id ?? stories[0].id,
      chapter_number: detail.chapter_number ?? undefined,
      summary: '',
    })
    setBeforeImageUrl(null)
    setAfterImageUrl(null)
    setApplicationOpen(true)
  }

  const uploadApplicationImage = async (
    file: File,
    setter: (url: string) => void,
  ) => {
    try {
      const result = await api.uploadCover(file)
      setter(result.url)
      message.success('图片已上传')
    } catch (error) {
      message.error(getErrorMessage(error))
      throw error
    }
  }

  const saveApplication = async () => {
    if (!detail) return
    let values: ApplicationFormValues
    try {
      values = await applicationForm.validateFields()
    } catch {
      return
    }
    const payload: DesignFeedbackApplicationPayload = {
      target_type: values.target_type,
      story_id: values.story_id,
      chapter_number: values.chapter_number ?? null,
      page_number: values.page_number ?? null,
      summary: values.summary.trim(),
      before_prompt: values.before_prompt?.trim() || null,
      after_prompt: values.after_prompt?.trim() || null,
      before_image_url: beforeImageUrl,
      after_image_url: afterImageUrl,
    }
    setApplicationSaving(true)
    try {
      await api.createDesignFeedbackApplication(detail.id, payload)
      setApplicationOpen(false)
      message.success('应用记录已添加')
      await refreshDetail()
      await load()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setApplicationSaving(false)
    }
  }

  const deleteApplication = async (application: DesignFeedbackApplication) => {
    if (!detail) return
    try {
      await api.deleteDesignFeedbackApplication(detail.id, application.id)
      message.success('应用记录已删除')
      await refreshDetail()
      await load()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const columns: ColumnsType<DesignFeedback> = [
    {
      title: '建议',
      dataIndex: 'title',
      width: 360,
      render: (_, record) => (
        <div>
          <Space size={4} wrap>
            <Typography.Text strong>{record.title}</Typography.Text>
            {record.is_rule && <Tag color="purple">规则</Tag>}
          </Space>
          <Typography.Paragraph
            type="secondary"
            ellipsis={{ rows: 2 }}
            style={{ margin: '4px 0' }}
          >
            {record.content}
          </Typography.Paragraph>
          {record.tags.length > 0 && (
            <Space size={4} wrap>
              {record.tags.map((tag) => (
                <Tag key={tag}>{tag}</Tag>
              ))}
            </Space>
          )}
        </div>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 100,
      render: (value: DesignFeedbackCategory) => (
        <Tag color="geekblue">{CATEGORY_LABELS[value]}</Tag>
      ),
    },
    {
      title: '范围',
      dataIndex: 'scope',
      width: 180,
      render: (_, record) => <Typography.Text>{scopeText(record)}</Typography.Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: DesignFeedbackStatus) => (
        <Tag color={STATUS_COLORS[value]}>{STATUS_LABELS[value]}</Tag>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 80,
      render: (value: DesignFeedbackPriority) => (
        <Tag color={PRIORITY_COLORS[value]}>{PRIORITY_LABELS[value]}</Tag>
      ),
    },
    {
      title: '应用',
      dataIndex: 'application_count',
      width: 70,
      render: (value: number) => `${value} 次`,
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 150,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => void openDetail(record)}>
            查看
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => deleteFeedback(record)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="设计建议"
        description="上传小红书截图或粘贴建议原文即可；结构化规则由 Claude Code 提炼。这里负责追溯、审核和回滚。"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增建议
          </Button>
        }
      />

      <Card className="panel">
        <div className="story-list-toolbar">
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="搜索建议标题或原文"
              value={keywordDraft}
              onChange={(event) => {
                setKeywordDraft(event.target.value)
                if (!event.target.value) setKeyword('')
              }}
              onSearch={(value) => setKeyword(value.trim())}
              style={{ width: 280 }}
            />
            <Select
              allowClear
              placeholder="状态"
              options={optionsFrom(STATUS_LABELS)}
              value={statusFilter}
              onChange={setStatusFilter}
              style={{ width: 120 }}
            />
            <Select
              allowClear
              placeholder="分类"
              options={optionsFrom(CATEGORY_LABELS)}
              value={categoryFilter}
              onChange={setCategoryFilter}
              style={{ width: 130 }}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="故事"
              options={stories.map((story) => ({
                value: story.id,
                label: story.name || `未命名故事 #${story.id}`,
              }))}
              value={storyFilter}
              onChange={setStoryFilter}
              style={{ width: 180 }}
            />
          </Space>
          <Typography.Text type="secondary">
            共 {feedbacks.length} 条建议
          </Typography.Text>
        </div>

        <Table<DesignFeedback>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={feedbacks}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          scroll={{ x: 1100 }}
          locale={{
            emptyText: (
              <Empty description="还没有设计建议；上传截图或粘贴建议原文开始记录" />
            ),
          }}
        />
      </Card>

      <Modal
        title={editing ? '编辑设计建议' : '新增设计建议'}
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={() => void saveFeedback()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={760}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">
          你只需要上传截图或粘贴建议原文；标题、分类、作用范围和怎么改提示词，由 Claude Code
          从素材里提炼。截图和文字至少提供一个。
        </Typography.Paragraph>
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item label="小红书截图（可选）">
            <ImageUpload
              imageUrl={screenshotUrl}
              onUpload={uploadScreenshot}
              onRemove={() => {
                setScreenshotUrl(null)
                setScreenshotFilename(null)
              }}
              uploadText="上传小红书截图"
              replaceText="替换截图"
            />
          </Form.Item>
          <Form.Item
            name="content"
            label="建议原文 / 文字描述"
            extra="截图里已经有文字时可以留空；也可以直接粘贴小红书建议或你对原文的分析。"
          >
            <Input.TextArea
              rows={6}
              maxLength={5000}
              showCount
              placeholder="粘贴建议原文；只给截图时这里可以留空"
            />
          </Form.Item>
          <Collapse
            ghost
            items={[
              {
                key: 'optional',
                label: '可选信息（标题 / 来源 / 分类 / 范围）',
                forceRender: true,
                children: (
                  <>
                    <Form.Item name="title" label="标题（留空自动生成）">
                      <Input maxLength={120} showCount />
                    </Form.Item>
                    <Space size="middle" wrap>
                      <Form.Item
                        name="source"
                        label="来源"
                        style={{ width: 140 }}
                      >
                        <Select options={optionsFrom(SOURCE_LABELS)} />
                      </Form.Item>
                      <Form.Item
                        name="category"
                        label="分类"
                        style={{ width: 160 }}
                      >
                        <Select options={optionsFrom(CATEGORY_LABELS)} />
                      </Form.Item>
                      <Form.Item
                        name="priority"
                        label="优先级"
                        style={{ width: 120 }}
                      >
                        <Select options={optionsFrom(PRIORITY_LABELS)} />
                      </Form.Item>
                      {editing && (
                        <Form.Item
                          name="status"
                          label="状态"
                          style={{ width: 140 }}
                        >
                          <Select options={optionsFrom(STATUS_LABELS)} />
                        </Form.Item>
                      )}
                    </Space>
                    <Form.Item name="source_url" label="来源链接（可选）">
                      <Input
                        maxLength={500}
                        placeholder="小红书原帖或截图来源链接"
                      />
                    </Form.Item>
                    <Form.Item name="scope" label="适用范围">
                      <Select
                        options={optionsFrom(SCOPE_LABELS)}
                        onChange={() => {
                          form.setFieldValue('story_id', undefined)
                          form.setFieldValue('chapter_number', undefined)
                        }}
                      />
                    </Form.Item>
                    <Form.Item
                      noStyle
                      shouldUpdate={(previous, current) =>
                        previous.scope !== current.scope
                      }
                    >
                      {({ getFieldValue }) =>
                        getFieldValue('scope') !== 'global' ? (
                          <Form.Item
                            name="story_id"
                            label="关联故事"
                            rules={[
                              { required: true, message: '请选择故事' },
                            ]}
                          >
                            <Select
                              showSearch
                              optionFilterProp="label"
                              placeholder="选择这条建议针对的故事"
                              options={stories.map((story) => ({
                                value: story.id,
                                label:
                                  story.name || `未命名故事 #${story.id}`,
                              }))}
                            />
                          </Form.Item>
                        ) : null
                      }
                    </Form.Item>
                    <Form.Item
                      noStyle
                      shouldUpdate={(previous, current) =>
                        previous.scope !== current.scope
                      }
                    >
                      {({ getFieldValue }) =>
                        getFieldValue('scope') === 'chapter' ? (
                          <Form.Item
                            name="chapter_number"
                            label="章节号"
                            rules={[
                              { required: true, message: '请填写章节号' },
                            ]}
                          >
                            <InputNumber
                              min={1}
                              max={50}
                              style={{ width: '100%' }}
                            />
                          </Form.Item>
                        ) : null
                      }
                    </Form.Item>
                    <Form.Item name="tags" label="标签">
                      <Select
                        mode="tags"
                        tokenSeparators={[',', '，']}
                        placeholder="输入后回车，例如：表情、悬念、标题"
                      />
                    </Form.Item>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </Modal>

      <Drawer
        title={detail?.title ?? '设计建议详情'}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false)
          setDetail(null)
        }}
        width={780}
      >
        {detailLoading ? (
          <Skeleton active />
        ) : detail ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space wrap>
              <Tag color="geekblue">{CATEGORY_LABELS[detail.category]}</Tag>
              <Tag color={STATUS_COLORS[detail.status]}>
                {STATUS_LABELS[detail.status]}
              </Tag>
              <Tag color={PRIORITY_COLORS[detail.priority]}>
                优先级 {PRIORITY_LABELS[detail.priority]}
              </Tag>
              <Tag>{scopeText(detail)}</Tag>
              <Tag>{SOURCE_LABELS[detail.source]}</Tag>
              {detail.is_rule && (
                <Tag color="purple">
                  规则 · {RULE_TARGET_LABELS[detail.rule_target]}
                </Tag>
              )}
            </Space>
            {detail.tags.length > 0 && (
              <Space wrap size={4}>
                {detail.tags.map((tag) => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
              </Space>
            )}
            <Typography.Paragraph
              type={detail.content ? undefined : 'secondary'}
              style={{ whiteSpace: 'pre-wrap' }}
            >
              {detail.content || '（截图建议，无文字）'}
            </Typography.Paragraph>
            {detail.source_url && (
              <Typography.Link href={detail.source_url} target="_blank">
                查看来源链接
              </Typography.Link>
            )}
            {detail.screenshot_url && (
              <Image
                src={detail.screenshot_url}
                alt="小红书截图"
                style={{ maxHeight: 360, objectFit: 'contain' }}
              />
            )}
            <DesignRulePanel
              feedbackId={detail.id}
              stories={stories}
              onChanged={() => void load()}
            />
            <Divider titlePlacement="start">应用记录</Divider>
            <Button
              type="primary"
              ghost
              icon={<PlusCircleOutlined />}
              onClick={openApplication}
            >
              记录应用
            </Button>
            {detail.applications.length === 0 ? (
              <Empty description="还没有应用记录；改完图后可由 Claude Code 写回，也可以在这里手动补记" />
            ) : (
              <List
                itemLayout="vertical"
                dataSource={detail.applications}
                renderItem={(application) => (
                  <List.Item
                    actions={[
                      <Popconfirm
                        key="delete"
                        title="删除这条应用记录？"
                        onConfirm={() => void deleteApplication(application)}
                        okText="删除"
                        cancelText="取消"
                      >
                        <Button type="link" danger size="small">
                          删除
                        </Button>
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={targetText(application)}
                      description={dayjs(application.applied_at).format(
                        'YYYY-MM-DD HH:mm',
                      )}
                    />
                    <Typography.Paragraph>
                      {application.summary}
                    </Typography.Paragraph>
                    {(application.before_image_url ||
                      application.after_image_url) && (
                      <Space align="start" wrap>
                        {application.before_image_url && (
                          <div>
                            <Typography.Text type="secondary">
                              改前
                            </Typography.Text>
                            <div>
                              <Image
                                src={application.before_image_url}
                                width={180}
                                style={{ objectFit: 'cover' }}
                              />
                            </div>
                          </div>
                        )}
                        {application.after_image_url && (
                          <div>
                            <Typography.Text type="secondary">
                              改后
                            </Typography.Text>
                            <div>
                              <Image
                                src={application.after_image_url}
                                width={180}
                                style={{ objectFit: 'cover' }}
                              />
                            </div>
                          </div>
                        )}
                      </Space>
                    )}
                    {(application.before_prompt ||
                      application.after_prompt) && (
                      <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
                        <div style={{ flex: 1 }}>
                          <Typography.Text type="secondary">
                            改前提示词
                          </Typography.Text>
                          <pre
                            style={{
                              whiteSpace: 'pre-wrap',
                              maxHeight: 180,
                              overflow: 'auto',
                              background: '#fafafa',
                              padding: 8,
                              margin: '4px 0 0',
                              fontSize: 12,
                            }}
                          >
                            {application.before_prompt || '（无）'}
                          </pre>
                        </div>
                        <div style={{ flex: 1 }}>
                          <Typography.Text type="secondary">
                            改后提示词
                          </Typography.Text>
                          <pre
                            style={{
                              whiteSpace: 'pre-wrap',
                              maxHeight: 180,
                              overflow: 'auto',
                              background: '#fafafa',
                              padding: 8,
                              margin: '4px 0 0',
                              fontSize: 12,
                            }}
                          >
                            {application.after_prompt || '（无）'}
                          </pre>
                        </div>
                      </div>
                    )}
                  </List.Item>
                )}
              />
            )}
          </Space>
        ) : null}
      </Drawer>

      <Modal
        title="记录一次应用"
        open={applicationOpen}
        onCancel={() => setApplicationOpen(false)}
        onOk={() => void saveApplication()}
        confirmLoading={applicationSaving}
        okText="保存"
        cancelText="取消"
        width={760}
        destroyOnHidden
      >
        <Form form={applicationForm} layout="vertical" preserve={false}>
          <Space size="middle" wrap>
            <Form.Item
              name="target_type"
              label="目标类型"
              style={{ width: 160 }}
              rules={[{ required: true }]}
            >
              <Select
                options={optionsFrom(TARGET_LABELS)}
                onChange={(value: DesignFeedbackTargetType) => {
                  if (value !== 'page') {
                    applicationForm.setFieldValue('page_number', undefined)
                  }
                  if (value !== 'cover' && value !== 'guide') {
                    applicationForm.setFieldValue('chapter_number', undefined)
                  }
                }}
              />
            </Form.Item>
            <Form.Item
              name="story_id"
              label="故事"
              style={{ width: 240 }}
              rules={[{ required: true, message: '请选择故事' }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                options={stories.map((story) => ({
                  value: story.id,
                  label: story.name || `未命名故事 #${story.id}`,
                }))}
              />
            </Form.Item>
          </Space>
          <Form.Item
            noStyle
            shouldUpdate={(previous, current) =>
              previous.target_type !== current.target_type
            }
          >
            {({ getFieldValue }) => {
              const target = getFieldValue('target_type') as
                | DesignFeedbackTargetType
                | undefined
              return (
                <Space size="middle" wrap>
                  {(target === 'cover' || target === 'guide') && (
                    <Form.Item
                      name="chapter_number"
                      label="章节号"
                      style={{ width: 160 }}
                      rules={[{ required: true, message: '请填写章节号' }]}
                    >
                      <InputNumber min={1} max={50} style={{ width: '100%' }} />
                    </Form.Item>
                  )}
                  {target === 'page' && (
                    <Form.Item
                      name="page_number"
                      label="全局页码"
                      style={{ width: 160 }}
                      rules={[{ required: true, message: '请填写页码' }]}
                    >
                      <InputNumber min={1} max={200} style={{ width: '100%' }} />
                    </Form.Item>
                  )}
                </Space>
              )
            }}
          </Form.Item>
          <Form.Item
            name="summary"
            label="这次改了什么"
            rules={[{ required: true, message: '请写一句改动说明' }]}
          >
            <Input.TextArea
              rows={3}
              maxLength={500}
              showCount
              placeholder="例如：把副标题改成代价句；封面表情改成含泪但不哭"
            />
          </Form.Item>
          <Form.Item name="before_prompt" label="改前提示词（可选）">
            <Input.TextArea rows={4} maxLength={8000} />
          </Form.Item>
          <Form.Item name="after_prompt" label="改后提示词（可选）">
            <Input.TextArea rows={4} maxLength={8000} />
          </Form.Item>
          <Divider titlePlacement="start">改前 / 改后图片（可选）</Divider>
          <Space align="start" size="large" wrap>
            <div>
              <Typography.Text type="secondary">改前图</Typography.Text>
              <ImageUpload
                imageUrl={beforeImageUrl}
                onUpload={(file) =>
                  uploadApplicationImage(file, setBeforeImageUrl)
                }
                onRemove={() => setBeforeImageUrl(null)}
                variant="card"
                uploadText="上传改前图"
                replaceText="替换改前图"
              />
            </div>
            <div>
              <Typography.Text type="secondary">改后图</Typography.Text>
              <ImageUpload
                imageUrl={afterImageUrl}
                onUpload={(file) =>
                  uploadApplicationImage(file, setAfterImageUrl)
                }
                onRemove={() => setAfterImageUrl(null)}
                variant="card"
                uploadText="上传改后图"
                replaceText="替换改后图"
              />
            </div>
          </Space>
        </Form>
      </Modal>
    </div>
  )
}
