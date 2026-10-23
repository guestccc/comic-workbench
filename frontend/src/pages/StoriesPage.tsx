import { useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Image,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CopyOutlined,
  EyeOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import CoverUpload from '../components/CoverUpload'
import PageHeader from '../components/PageHeader'
import { api, ApiError, getErrorMessage } from '../api/client'
import type { ArtStyle, Story } from '../types'
import { copyText } from '../utils/clipboard'
import {
  buildStoryBreakdownPrompt,
  getBreakdownBlockedReason,
} from '../utils/storyBreakdown'

/** 故事名可留空，列表中统一显示占位文案。 */
function displayStoryName(name: string | null | undefined): string {
  return name?.trim() || '未命名故事'
}

interface StoryFormValues {
  name: string
  content: string
  cover_filename?: string | null
  art_style_id?: string | null
}

export default function StoriesPage() {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<StoryFormValues>()
  const [stories, setStories] = useState<Story[]>([])
  const [artStyles, setArtStyles] = useState<ArtStyle[]>([])
  const [activeArtStyleId, setActiveArtStyleId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState('')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Story | null>(null)
  const [saving, setSaving] = useState(false)
  const [coverUploading, setCoverUploading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      // 故事列表与画风列表一起加载：故事选择画风时需要展示可选画风
      const [storyList, settings] = await Promise.all([
        api.listStories(),
        api.getSettings(),
      ])
      setStories(storyList)
      setArtStyles(settings.art_styles)
      setActiveArtStyleId(settings.active_art_style)
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
        story.content.toLowerCase().includes(query) ||
        (story.art_style_name ?? '').toLowerCase().includes(query),
    )
  }, [stories, keyword])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    // 新建时默认跟随当前选用的画风，仍可为该故事单独选择
    form.setFieldsValue({ art_style_id: activeArtStyleId ?? undefined })
    setOpen(true)
  }

  const openEdit = (story: Story) => {
    setEditing(story)
    form.setFieldsValue({
      name: story.name,
      content: story.content,
      cover_filename: story.cover_filename,
      // 画风被删除（解析不到名称）时回退到当前选用画风，避免下拉框显示无效 id
      art_style_id: story.art_style_name
        ? story.art_style_id
        : (activeArtStyleId ?? undefined),
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
        name: (values.name ?? '').trim(),
        content: values.content,
        cover_filename: values.cover_filename ?? null,
        art_style_id: values.art_style_id ?? null,
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

  // 只复制故事 ID；故事名、原文与画风由 Claude 在项目内自行查询数据库
  const handleCopyBreakdown = async (story: Story) => {
    const blockedReason = getBreakdownBlockedReason(story)
    if (blockedReason) {
      message.warning(blockedReason)
      return
    }
    try {
      await copyText(buildStoryBreakdownPrompt(story.id))
      message.success('拆解指令已复制（Claude 会一次性生成角色卡与全部分镜并写回）')
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  const handleDelete = (story: Story) => {
    modal.confirm({
      title: '删除这个故事？',
      content: `将删除「${displayStoryName(story.name)}」。若该故事下已有发文记录，系统会阻止删除。`,
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
      render: (name: string, story) => (
        <Typography.Link
          strong={Boolean(name?.trim())}
          type={name?.trim() ? undefined : 'secondary'}
          onClick={() => navigate(`/stories/${story.id}`)}
        >
          {displayStoryName(name)}
        </Typography.Link>
      ),
    },
    {
      title: '画风',
      dataIndex: 'art_style_name',
      width: 140,
      render: (name: string | null, story: Story) =>
        name ? (
          <Typography.Text>{name}</Typography.Text>
        ) : story.art_style_id ? (
          <Typography.Text type="danger">画风已失效</Typography.Text>
        ) : (
          <Typography.Text type="secondary">未选择</Typography.Text>
        ),
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
      width: 300,
      render: (_, story) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/stories/${story.id}`)}
          >
            详情
          </Button>
          <Button
            type="link"
            size="small"
            icon={<CopyOutlined />}
            onClick={() => void handleCopyBreakdown(story)}
          >
            复制拆解指令
          </Button>
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
        description="维护故事原文与封面；故事名可留空，拆解时自动补填。为故事选择画风后，可复制拆解指令（只含故事 ID），粘贴到本项目的 Claude Code 中，它会读取原文与画风，一次性生成角色设定卡与全部分镜并写回详情页。生图提示词使用 {{角色名}} 变量，参考垫图由你在外部生图 AI 中自行绑定。"
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
          scroll={{ x: 1240 }}
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
            extra="可留空：先只创建原文，拆解时由 Claude 拟定名称并自动回写。"
          >
            <Input maxLength={200} showCount placeholder="可留空，拆解后再补填" />
          </Form.Item>

          <Form.Item
            name="art_style_id"
            label="画风"
            rules={[{ required: true, message: '请选择画风' }]}
            extra="拆解时会严格使用该画风；画风列表可在「启动提示词」页维护。"
          >
            <Select
              allowClear
              placeholder="选择该故事使用的画风"
              options={artStyles.map((style) => ({
                value: style.id,
                label: style.name,
              }))}
              notFoundContent="还没有画风，请先到「启动提示词」页添加"
            />
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
