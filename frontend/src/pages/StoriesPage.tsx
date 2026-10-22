import { useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Image,
  Input,
  Modal,
  Space,
  Table,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import CoverUpload from '../components/CoverUpload'
import PageHeader from '../components/PageHeader'
import { api, ApiError, getErrorMessage } from '../api/client'
import type { Story } from '../types'

interface StoryFormValues {
  name: string
  content: string
  cover_filename?: string | null
}

export default function StoriesPage() {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm<StoryFormValues>()
  const [stories, setStories] = useState<Story[]>([])
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState('')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Story | null>(null)
  const [saving, setSaving] = useState(false)
  const [coverUploading, setCoverUploading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      setStories(await api.listStories())
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const filteredStories = useMemo(() => {
    const query = keyword.trim().toLowerCase()
    if (!query) return stories
    return stories.filter(
      (story) =>
        story.name.toLowerCase().includes(query) ||
        story.content.toLowerCase().includes(query),
    )
  }, [stories, keyword])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    setOpen(true)
  }

  const openEdit = (story: Story) => {
    setEditing(story)
    form.setFieldsValue({
      name: story.name,
      content: story.content,
      cover_filename: story.cover_filename,
    })
    setOpen(true)
  }

  const handleSubmit = async () => {
    let values: StoryFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    setSaving(true)
    try {
      const payload = {
        name: values.name,
        content: values.content,
        cover_filename: values.cover_filename ?? null,
      }
      if (editing) {
        await api.updateStory(editing.id, payload)
        message.success('故事已更新')
      } else {
        await api.createStory(payload)
        message.success('故事已创建')
      }
      setOpen(false)
      await load()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = (story: Story) => {
    modal.confirm({
      title: '删除这个故事？',
      content: `将删除「${story.name}」。若该故事下已有发文记录，系统会阻止删除。`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteStory(story.id)
          message.success('故事已删除')
          await load()
        } catch (error) {
          if (error instanceof ApiError && error.status === 409) {
            message.warning(error.message)
          } else {
            message.error(getErrorMessage(error))
          }
        }
      },
    })
  }

  const columns: ColumnsType<Story> = [
    {
      title: '封面',
      dataIndex: 'cover_url',
      width: 80,
      render: (coverUrl: string | null) =>
        coverUrl ? (
          <Image
            src={coverUrl}
            width={48}
            height={64}
            className="cover-thumb"
            preview={{ mask: '预览' }}
          />
        ) : (
          <div className="cover-placeholder">暂无</div>
        ),
    },
    {
      title: '故事名',
      dataIndex: 'name',
      width: 180,
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    {
      title: '故事原文',
      dataIndex: 'content',
      render: (content: string) => (
        <Typography.Paragraph
          className="content-preview"
          ellipsis={{ rows: 2 }}
          style={{ maxWidth: 460, marginBottom: 0 }}
        >
          {content}
        </Typography.Paragraph>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 160,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      render: (_, story) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => openEdit(story)}>
            编辑
          </Button>
          <Button type="link" size="small" danger onClick={() => handleDelete(story)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="故事管理"
        description="维护故事名称、原文和封面，作为生成小红书图文的素材。"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建故事
          </Button>
        }
      />

      <Card className="panel">
        <Input.Search
          allowClear
          placeholder="搜索故事名或原文"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          style={{ maxWidth: 360, marginBottom: 16 }}
        />
        <Table<Story>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={filteredStories}
          pagination={{
            pageSize: 8,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 个故事`,
          }}
          scroll={{ x: 900 }}
          locale={{ emptyText: '还没有故事，点击右上角「新建故事」开始吧' }}
        />
      </Card>

      <Modal
        title={editing ? '编辑故事' : '新建故事'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void handleSubmit()}
        confirmLoading={saving}
        okText={editing ? '保存' : '创建'}
        cancelText="取消"
        okButtonProps={{ disabled: coverUploading }}
        width={720}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="故事名"
            rules={[{ required: true, message: '请输入故事名' }]}
          >
            <Input maxLength={200} showCount placeholder="给故事起个名字" />
          </Form.Item>

          <Form.Item
            name="content"
            label="故事原文"
            rules={[{ required: true, message: '请输入故事原文' }]}
            extra="原文会作为 AI 生成文案的素材，最多 30000 字。"
          >
            <Input.TextArea
              rows={12}
              maxLength={30000}
              showCount
              placeholder="粘贴故事原文..."
            />
          </Form.Item>

          <Form.Item name="cover_filename" label="故事封面">
            <CoverUpload onUploadingChange={setCoverUploading} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
