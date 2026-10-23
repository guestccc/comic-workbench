import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined, ThunderboltOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import PageHeader from '../components/PageHeader'
import CopyOptionsModal from '../components/CopyOptionsModal'
import { api, ApiError, getErrorMessage } from '../api/client'
import type {
  GeneratedCopyOption,
  Post,
  PostStatus,
  SettingsData,
  Story,
} from '../types'

interface PostFormValues {
  story_id: number
  title: string
  content: string
  status: PostStatus
}

const statusMeta: Record<PostStatus, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'gold' },
  published: { label: '已发布', color: 'green' },
}

export default function PostsPage() {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<PostFormValues>()
  const [posts, setPosts] = useState<Post[]>([])
  const [stories, setStories] = useState<Story[]>([])
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Post | null>(null)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  // AI 返回的多个文案方案；用户选定后才填入表单
  const [copyOptions, setCopyOptions] = useState<GeneratedCopyOption[]>([])
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [storyFilter, setStoryFilter] = useState<number | undefined>()
  const [statusFilter, setStatusFilter] = useState<PostStatus | undefined>()
  const [keyword, setKeyword] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [postList, storyList, settingsData] = await Promise.all([
        api.listPosts(),
        api.listStories(),
        api.getSettings(),
      ])
      setPosts(postList)
      setStories(storyList)
      setSettings(settingsData)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const storyOptions = useMemo(
    () =>
      stories.map((story) => ({
        value: story.id,
        label: story.name.trim() || '未命名故事',
      })),
    [stories],
  )

  const filteredPosts = useMemo(() => {
    const query = keyword.trim().toLowerCase()
    return posts.filter((post) => {
      if (storyFilter !== undefined && post.story_id !== storyFilter) return false
      if (statusFilter !== undefined && post.status !== statusFilter) return false
      if (
        query &&
        !post.title.toLowerCase().includes(query) &&
        !post.content.toLowerCase().includes(query) &&
        !post.story_name.toLowerCase().includes(query)
      ) {
        return false
      }
      return true
    })
  }, [posts, storyFilter, statusFilter, keyword])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ status: 'draft' })
    setOpen(true)
  }

  const openEdit = (post: Post) => {
    setEditing(post)
    form.setFieldsValue({
      story_id: post.story_id,
      title: post.title,
      content: post.content,
      status: post.status,
    })
    setOpen(true)
  }

  const handleGenerate = async () => {
    let storyId: number
    try {
      const values = await form.validateFields(['story_id'])
      storyId = values.story_id
    } catch {
      return
    }

    setGenerating(true)
    try {
      const copy = await api.generateCopy(storyId)
      // 先让用户对比多个方案，选定后再填表
      setCopyOptions(copy.options)
      setOptionsOpen(true)
    } catch (error) {
      if (error instanceof ApiError && error.code === 'DEEPSEEK_KEY_MISSING') {
        modal.confirm({
          title: '尚未配置 DeepSeek API Key',
          content: error.message,
          okText: '去配置',
          cancelText: '取消',
          onOk: () => navigate('/settings'),
        })
      } else {
        message.error(getErrorMessage(error))
      }
    } finally {
      setGenerating(false)
    }
  }

  /**
   * 采用方案：单个填入表单继续编辑；多个说明用户想把一个故事
   * 拆成多次发作品，直接按选中数量各建一条草稿。
   */
  const applyCopyOption = async (selected: GeneratedCopyOption[]) => {
    if (selected.length === 0) return
    if (selected.length === 1) {
      form.setFieldsValue({
        title: selected[0].title,
        content: selected[0].content,
      })
      setOptionsOpen(false)
      message.success(`已采用「${selected[0].style}」方案，可继续编辑后保存`)
      return
    }

    setSaving(true)
    try {
      await Promise.all(
        selected.map((option) =>
          api.createPost({
            story_id: form.getFieldValue('story_id') as number,
            title: option.title,
            content: option.content,
            status: 'draft',
          }),
        ),
      )
      setOptionsOpen(false)
      setOpen(false)
      message.success(`已创建 ${selected.length} 条草稿，可分别编辑后发布`)
    } catch (error) {
      // 并发创建可能部分成功，提示后仍刷新列表，避免误以为全部失败
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
      await load()
    }
  }

  const handleSubmit = async () => {
    let values: PostFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    setSaving(true)
    try {
      if (editing) {
        await api.updatePost(editing.id, {
          title: values.title,
          content: values.content,
          status: values.status,
        })
        message.success('发文已更新')
      } else {
        await api.createPost({
          story_id: values.story_id,
          title: values.title,
          content: values.content,
          status: values.status,
        })
        message.success('发文已保存')
      }
      setOpen(false)
      await load()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleToggleStatus = async (post: Post) => {
    const nextStatus: PostStatus = post.status === 'draft' ? 'published' : 'draft'
    try {
      await api.updatePost(post.id, { status: nextStatus })
      message.success(nextStatus === 'published' ? '已标记为已发布' : '已转为草稿')
      await load()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const handleDelete = (post: Post) => {
    modal.confirm({
      title: '删除这条发文？',
      content: `将删除「${post.title}」，删除后不可恢复。`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deletePost(post.id)
          message.success('发文已删除')
          await load()
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  const columns: ColumnsType<Post> = [
    {
      title: '故事',
      dataIndex: 'story_name',
      width: 140,
      ellipsis: true,
      render: (name: string) =>
        name.trim() ? name : <Typography.Text type="secondary">未命名故事</Typography.Text>,
    },
    {
      title: '标题',
      dataIndex: 'title',
      width: 220,
      render: (title: string) => <Typography.Text strong>{title}</Typography.Text>,
    },
    {
      title: '正文',
      dataIndex: 'content',
      render: (content: string) => (
        <Typography.Paragraph
          className="content-preview"
          ellipsis={{ rows: 2 }}
          style={{ maxWidth: 400, marginBottom: 0 }}
        >
          {content}
        </Typography.Paragraph>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: PostStatus) => (
        <Tag color={statusMeta[status].color}>{statusMeta[status].label}</Tag>
      ),
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
      width: 200,
      render: (_, post) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => openEdit(post)}>
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => void handleToggleStatus(post)}>
            {post.status === 'draft' ? '标记发布' : '转草稿'}
          </Button>
          <Button type="link" size="small" danger onClick={() => handleDelete(post)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const keyConfigured = settings?.deepseek.configured ?? false

  return (
    <div>
      <PageHeader
        title="发文管理"
        description="根据故事生成小红书图文的标题与正文，编辑确认后保存并跟踪发布状态。"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建发文
          </Button>
        }
      />

      {settings && !keyConfigured && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="尚未配置 DeepSeek API Key，暂时无法使用 AI 生成文案"
          description="仍可手动填写标题与正文并保存草稿。"
          action={
            <Button size="small" onClick={() => navigate('/settings')}>
              去配置
            </Button>
          }
        />
      )}

      <Card className="panel">
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="按故事筛选"
            style={{ width: 200 }}
            options={storyOptions}
            value={storyFilter}
            onChange={(value) => setStoryFilter(value)}
          />
          <Select
            allowClear
            placeholder="按状态筛选"
            style={{ width: 140 }}
            options={[
              { value: 'draft', label: '草稿' },
              { value: 'published', label: '已发布' },
            ]}
            value={statusFilter}
            onChange={(value) => setStatusFilter(value)}
          />
          <Input.Search
            allowClear
            placeholder="搜索标题、正文或故事名"
            style={{ width: 280 }}
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
        </Space>

        <Table<Post>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={filteredPosts}
          pagination={{
            pageSize: 8,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 条发文`,
          }}
          scroll={{ x: 1050 }}
          locale={{ emptyText: '还没有发文，点击右上角「新建发文」生成第一篇吧' }}
        />
      </Card>

      <Modal
        title={editing ? '编辑发文' : '新建发文'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void handleSubmit()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={760}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="story_id"
            label="关联故事"
            rules={[{ required: true, message: '请选择要生成文案的故事' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="选择故事"
              options={storyOptions}
              disabled={editing !== null}
            />
          </Form.Item>

          <Form.Item label="AI 生成">
            <Space>
              <Button
                icon={<ThunderboltOutlined />}
                loading={generating}
                onClick={() => void handleGenerate()}
                disabled={!keyConfigured}
              >
                AI 生成文案
              </Button>
              <Typography.Text type="secondary" className="modal-form-tip">
                {keyConfigured
                  ? '生成多个方案；可多选一次建多条草稿，单选则填入表单'
                  : '请先在设置页配置 DeepSeek API Key'}
              </Typography.Text>
            </Space>
          </Form.Item>

          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input maxLength={200} showCount placeholder="小红书图文标题" />
          </Form.Item>

          <Form.Item
            name="content"
            label="正文"
            rules={[{ required: true, message: '请输入正文' }]}
          >
            <Input.TextArea
              rows={12}
              maxLength={20000}
              showCount
              placeholder="小红书正文描述，可包含 emoji 和话题标签"
            />
          </Form.Item>

          <Form.Item name="status" label="状态">
            <Radio.Group
              options={[
                { value: 'draft', label: '草稿' },
                { value: 'published', label: '已发布' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <CopyOptionsModal
        open={optionsOpen}
        options={copyOptions}
        generating={generating}
        multiple={editing === null}
        onApply={(selected) => void applyCopyOption(selected)}
        onRegenerate={() => void handleGenerate()}
        onClose={() => setOptionsOpen(false)}
      />
    </div>
  )
}
