import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  App,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Skeleton,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
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
  buildStoryMappingPrompt,
  getBreakdownBlockedReason,
} from '../utils/storyBreakdown'

/** 故事名可留空，列表中统一显示占位文案。 */
function displayStoryName(name: string | null | undefined): string {
  return name?.trim() || '未命名故事'
}

/** 画风状态标签：正常 / 已失效 / 未选择。 */
function ArtStyleTag({ story }: { story: Story }) {
  if (story.art_style_name) {
    return <Tag color="geekblue">{story.art_style_name}</Tag>
  }
  if (story.art_style_id) {
    return <Tag color="red">画风已失效</Tag>
  }
  return <Tag>未选择画风</Tag>
}

/**
 * 瀑布流布局。
 *
 * 按容器宽度计算栏数（每栏最小 240px），再把卡片按顺序轮流分到各栏，
 * 这样从左到右、从上到下的阅读顺序与列表顺序一致；
 * 各栏高度不同，保留瀑布流的错落感。
 */
function StoryMasonry({ children }: { children: ReactNode[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [columnCount, setColumnCount] = useState(3)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const MIN_CARD_WIDTH = 240
    const GAP = 16
    const update = () => {
      const width = container.clientWidth
      setColumnCount(
        Math.max(1, Math.floor((width + GAP) / (MIN_CARD_WIDTH + GAP))),
      )
    }

    update()
    const observer = new ResizeObserver(update)
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const columns: ReactNode[][] = Array.from(
    { length: columnCount },
    () => [],
  )
  children.forEach((child, index) => {
    columns[index % columnCount].push(child)
  })

  return (
    <div className="story-masonry" ref={containerRef}>
      {columns.map((items, index) => (
        <div className="story-masonry-column" key={index}>
          {items}
        </div>
      ))}
    </div>
  )
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
        (story.art_style_name ?? '').toLowerCase().includes(query) ||
        (story.zhihu_title ?? '').toLowerCase().includes(query) ||
        (story.zhihu_alias ?? '').toLowerCase().includes(query) ||
        story.zhihu_aliases.some((alias) =>
          alias.toLowerCase().includes(query),
        ) ||
        (story.zhihu_article_id ?? '').includes(query),
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

  // 只复制故事 ID；故事名、原文、画风与 mapping 由 Claude 在项目内自行查询数据库
  const handleCopyMapping = async (story: Story) => {
    const blockedReason = getBreakdownBlockedReason(story)
    if (blockedReason) {
      message.warning(blockedReason)
      return
    }
    try {
      await copyText(buildStoryMappingPrompt(story.id))
      message.success('分镜对照指令已复制（Claude 会先写回对照表，确认后再生成脚本）')
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

  return (
    <div>
      <PageHeader
        title="故事管理"
        description="维护故事原文与封面；故事名可留空，拆解时自动补填。为故事选择画风后，可复制分镜对照指令（只含故事 ID），粘贴到本项目的 Claude Code 中，它会先按优化文顺序写回「页码 → 原文段落」对照表；到详情页确认后，再复制分镜头脚本指令逐页生成。生图提示词使用 {{角色名}} 变量，参考垫图由你在外部生图 AI 中自行绑定。"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建故事
          </Button>
        }
      />

      <Card className="panel">
        <div className="story-list-toolbar">
          <Input.Search
            allowClear
            placeholder="搜索故事名、原文、画风、知乎标题、别名或 ID"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            style={{ maxWidth: 360 }}
          />
          <Typography.Text type="secondary">
            共 {filteredStories.length} 个故事
          </Typography.Text>
        </div>

        {loading ? (
          <StoryMasonry>
            {Array.from({ length: 6 }).map((_, index) => (
              <Card key={index} className="story-card">
                <Skeleton active paragraph={{ rows: 3 }} />
              </Card>
            ))}
          </StoryMasonry>
        ) : filteredStories.length === 0 ? (
          <Empty
            description={
              keyword.trim()
                ? '没有匹配的故事'
                : '还没有故事，点击右上角「新建故事」开始吧'
            }
          />
        ) : (
          <StoryMasonry>
            {filteredStories.map((story) => (
              <Card
                key={story.id}
                className="story-card"
                hoverable
                onClick={() => navigate(`/stories/${story.id}`)}
                cover={
                  story.cover_url ? (
                    <div className="story-card-cover">
                      <img
                        src={story.cover_url}
                        className="story-card-cover-img"
                        alt={displayStoryName(story.name)}
                      />
                    </div>
                  ) : (
                    <div className="story-card-cover story-card-cover-empty">
                      <span className="story-card-cover-initial">
                        {displayStoryName(story.name).slice(0, 1)}
                      </span>
                      <span className="story-card-cover-hint">暂无封面</span>
                    </div>
                  )
                }
                actions={[
                  <Tooltip title="查看详情" key="detail">
                    <EyeOutlined
                      onClick={(event) => {
                        event.stopPropagation()
                        navigate(`/stories/${story.id}`)
                      }}
                    />
                  </Tooltip>,
                  <Tooltip title="复制分镜对照指令" key="copy">
                    <CopyOutlined
                      onClick={(event) => {
                        event.stopPropagation()
                        void handleCopyMapping(story)
                      }}
                    />
                  </Tooltip>,
                  <Tooltip title="编辑" key="edit">
                    <EditOutlined
                      onClick={(event) => {
                        event.stopPropagation()
                        openEdit(story)
                      }}
                    />
                  </Tooltip>,
                  <Tooltip title="删除" key="delete">
                    <DeleteOutlined
                      onClick={(event) => {
                        event.stopPropagation()
                        handleDelete(story)
                      }}
                    />
                  </Tooltip>,
                ]}
              >
                <div className="story-card-head">
                  {/* 点击冒泡到整张卡片，由 Card onClick 统一进详情 */}
                  <Typography.Link
                    strong
                    ellipsis
                    className="story-card-title"
                  >
                    {displayStoryName(story.name)}
                  </Typography.Link>
                  <ArtStyleTag story={story} />
                  {story.zhihu_alias ? (
                    <Tag color="purple">别名：{story.zhihu_alias}</Tag>
                  ) : story.zhihu_aliases.length > 0 ? (
                    <Tag color="orange">别名待标注</Tag>
                  ) : null}
                </div>
                <Typography.Paragraph
                  className="story-card-excerpt"
                  ellipsis={{ rows: 3 }}
                >
                  {story.content}
                </Typography.Paragraph>
                <div className="story-card-meta">
                  <span>
                    更新 {dayjs(story.updated_at).format('YYYY-MM-DD HH:mm')}
                  </span>
                  <span>#{story.id}</span>
                </div>
              </Card>
            ))}
          </StoryMasonry>
        )}
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
