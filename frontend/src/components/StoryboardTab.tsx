import { useState } from 'react'
import {
  App,
  Button,
  Collapse,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'
import {
  CopyOutlined,
  DeleteOutlined,
  DiffOutlined,
  EditOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import StoryCompareModal from './StoryCompareModal'
import { api, getErrorMessage } from '../api/client'
import type {
  Story,
  StoryboardPage,
  StoryboardPagePayload,
  StoryboardShotType,
  StoryBreakdown,
} from '../types'
import { copyText } from '../utils/clipboard'
import { formatImagePrompt, parseImagePrompt } from '../utils/formatPrompt'

interface StoryboardTabProps {
  story: Story
  breakdown: StoryBreakdown | null
  /** 是否已配置 DeepSeek Key，决定「改动解读」是否可用 */
  aiEnabled: boolean
  onRefresh: () => Promise<void>
}

/** 编辑弹窗的表单值；对话在表单里是多行文本，保存前再拆分。 */
interface PageFormValues {
  is_flashback: boolean
  page_role: string
  story_content: string
  characters: string[]
  character_review: string
  scene: string
  action_state: string
  change_note: string
  narration_main: string
  narration_highlight: string
  narration_sub: string
  dialogues_text: string
  shot_type: StoryboardShotType
  image_prompt: string
}

const SHOT_TYPE_OPTIONS: { value: StoryboardShotType; label: string }[] = [
  { value: '全景', label: '全景' },
  { value: '中景', label: '中景' },
  { value: '特写', label: '特写' },
]

/** 页面作用：第 1 页固定为钩子封面，其余按本页在故事中的功能选择。 */
const PAGE_ROLE_OPTIONS = [
  { value: '钩子封面', label: '钩子封面' },
  { value: '铺垫', label: '铺垫' },
  { value: '冲突', label: '冲突' },
  { value: '反转', label: '反转' },
  { value: '爆点', label: '爆点' },
  { value: '情绪高潮', label: '情绪高潮' },
  { value: '收尾', label: '收尾' },
]

/** 页面作用对应的标签颜色，未知值回退为默认色。 */
const PAGE_ROLE_COLORS: Record<string, string> = {
  钩子封面: 'magenta',
  铺垫: 'blue',
  冲突: 'orange',
  反转: 'purple',
  爆点: 'red',
  情绪高潮: 'volcano',
  收尾: 'green',
}

/** 把多行文本拆成台词数组，忽略空行。 */
function parseDialogues(text: string | undefined): string[] {
  return (text ?? '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

/**
 * 分镜头脚本 tab。
 *
 * - 顶部按钮打开「原文 / 优化文对比」：逐字对比 + AI 改动解读，可查看 / 编辑优化文；
 * - 按页码折叠列出每页分镜的全部条目，并提供「复制提示词」直接粘贴到生图 agent；
 * - 支持单页编辑、删除以及清空分镜 / 清空整份拆解。
 */
export default function StoryboardTab({
  story,
  breakdown,
  aiEnabled,
  onRefresh,
}: StoryboardTabProps) {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm<PageFormValues>()

  const [editOpen, setEditOpen] = useState(false)
  const [editingPage, setEditingPage] = useState<StoryboardPage | null>(null)
  const [pageSaving, setPageSaving] = useState(false)

  const [compareOpen, setCompareOpen] = useState(false)

  // 受控的展开页码：默认全部折叠，支持一键展开 / 折叠全部
  const [activePageKeys, setActivePageKeys] = useState<string[]>([])

  const [optimizedOpen, setOptimizedOpen] = useState(false)
  const [optimizedText, setOptimizedText] = useState('')
  const [optimizedSaving, setOptimizedSaving] = useState(false)

  /** 复制单页生图提示词。 */
  const handleCopyPrompt = async (page: StoryboardPage) => {
    try {
      await copyText(formatImagePrompt(page.image_prompt))
      message.success(`第 ${page.page_number} 页生图提示词已复制`)
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  const openOptimized = () => {
    setOptimizedText(breakdown?.optimized_content ?? '')
    setOptimizedOpen(true)
  }

  const saveOptimized = async () => {
    const content = optimizedText.trim()
    if (!content) {
      message.warning('优化后文章不能为空')
      return
    }
    if (!breakdown) return

    setOptimizedSaving(true)
    try {
      await api.patchBreakdown(breakdown.story_id, {
        optimized_content: content,
      })
      setOptimizedOpen(false)
      message.success('优化后文章已保存')
      await onRefresh()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setOptimizedSaving(false)
    }
  }

  const openEdit = (page: StoryboardPage) => {
    setEditingPage(page)
    form.setFieldsValue({
      is_flashback: page.is_flashback,
      page_role: page.page_role || undefined,
      story_content: page.story_content,
      characters: page.characters,
      character_review: page.character_review,
      scene: page.scene,
      action_state: page.action_state,
      change_note: page.change_note,
      narration_main: page.narration_main,
      narration_highlight: page.narration_highlight,
      narration_sub: page.narration_sub,
      dialogues_text: page.dialogues.join('\n'),
      shot_type: page.shot_type,
      image_prompt: page.image_prompt,
    })
    setEditOpen(true)
  }

  const savePage = async () => {
    if (!breakdown || !editingPage) return

    let values: PageFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    const payload: StoryboardPagePayload = {
      is_flashback: values.is_flashback,
      page_role: values.page_role || '',
      story_content: values.story_content,
      characters: values.characters ?? [],
      character_review: values.character_review,
      scene: values.scene,
      action_state: values.action_state,
      change_note: values.change_note,
      narration_main: values.narration_main,
      narration_highlight: values.narration_highlight ?? '',
      narration_sub: values.narration_sub,
      dialogues: parseDialogues(values.dialogues_text),
      shot_type: values.shot_type,
      image_prompt: values.image_prompt,
    }

    setPageSaving(true)
    try {
      await api.putStoryboardPage(
        breakdown.story_id,
        editingPage.page_number,
        payload,
      )
      setEditOpen(false)
      message.success(`第 ${editingPage.page_number} 页已保存`)
      await onRefresh()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setPageSaving(false)
    }
  }

  const handleDeletePage = (page: StoryboardPage) => {
    if (!breakdown) return
    modal.confirm({
      title: `删除第 ${page.page_number} 页？`,
      content: '删除后不可恢复；如需重新生成，可使用「复制拆解指令」重跑。',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteStoryboardPage(breakdown.story_id, page.page_number)
          message.success('分镜页已删除')
          await onRefresh()
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  const handleClearPages = () => {
    if (!breakdown) return
    modal.confirm({
      title: '清空所有分镜页面？',
      content:
        '将删除全部页面，但保留优化后文章与角色设定卡。重新拆解前通常需要先清空，避免新旧分镜混在一起。',
      okText: '清空页面',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.clearStoryboardPages(breakdown.story_id)
          message.success('分镜页面已清空')
          await onRefresh()
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  const handleClearBreakdown = () => {
    if (!breakdown) return
    modal.confirm({
      title: '清空整份拆解？',
      content:
        '将删除优化后文章、角色设定卡与全部分镜页面，且不可恢复。',
      okText: '全部清空',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteBreakdown(breakdown.story_id)
          message.success('拆解结果已清空')
          await onRefresh()
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  // 尚未拆解：引导用户去复制指令
  if (!breakdown) {
    return (
      <Empty description="还没有拆解结果">
        <Typography.Text type="secondary">
          点击页面右上角「复制拆解指令」，粘贴到本项目的 Claude Code 中运行；
          优化后文章、角色设定卡与全部分镜会一次性写回这里。
        </Typography.Text>
      </Empty>
    )
  }

  const characterOptions = breakdown.characters.map((card) => ({
    value: card.name,
    label: card.role ? `${card.name}（${card.role}）` : card.name,
  }))

  return (
    <div>
      <div className="story-tab-toolbar">
        <Space wrap>
          <Typography.Text type="secondary">
            共 {breakdown.pages.length} 页
          </Typography.Text>
          {breakdown.pages.length > 0 && (
            <Typography.Text type="secondary">
              · 第 1 页为钩子封面 · 提示词使用 {'{{角色名}}'} 变量
            </Typography.Text>
          )}
          {breakdown.pages.length > 0 && (
            <Button
              size="small"
              icon={
                activePageKeys.length > 0 ? (
                  <MenuFoldOutlined />
                ) : (
                  <MenuUnfoldOutlined />
                )
              }
              onClick={() =>
                setActivePageKeys(
                  activePageKeys.length > 0
                    ? []
                    : breakdown.pages.map((page) => String(page.page_number)),
                )
              }
            >
              {activePageKeys.length > 0 ? '全部折叠' : '全部展开'}
            </Button>
          )}
        </Space>
        <Space wrap>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<DiffOutlined />}
            onClick={() => setCompareOpen(true)}
            disabled={!breakdown.optimized_content.trim()}
          >
            原文 / 优化文对比
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={openOptimized}>
            编辑优化文
          </Button>
          <Button
            size="small"
            icon={<DeleteOutlined />}
            onClick={handleClearPages}
            disabled={breakdown.pages.length === 0}
          >
            清空分镜页面
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={handleClearBreakdown}>
            清空整份拆解
          </Button>
        </Space>
      </div>

      {breakdown.pages.length === 0 ? (
        <Empty description="还没有分镜页面">
          <Typography.Text type="secondary">
            在 Claude Code 中运行拆解技能后，优化文、角色卡与全部分镜会一次性写回这里；
            写入完成后刷新页面即可查看。
          </Typography.Text>
        </Empty>
      ) : (
        // 分镜页默认全部折叠，标题栏直接展示本页故事内容，便于快速定位
        <Collapse
          ghost
          className="storyboard-pages"
          activeKey={activePageKeys}
          onChange={(keys) =>
            setActivePageKeys(
              (Array.isArray(keys) ? keys : [keys]).map(String),
            )
          }
          items={breakdown.pages.map((page) => ({
            key: String(page.page_number),
            label: (
              <div className="storyboard-page-label">
                <Typography.Text strong className="storyboard-page-title">
                  第 {page.page_number} 页
                </Typography.Text>
                {page.page_number === 1 && <Tag color="magenta">钩子封面</Tag>}
                {page.page_role && page.page_role !== '钩子封面' && (
                  <Tag color={PAGE_ROLE_COLORS[page.page_role] ?? 'default'}>
                    {page.page_role}
                  </Tag>
                )}
                {page.is_flashback && <Tag color="blue">回忆页</Tag>}
                <Tag>{page.shot_type}</Tag>
                <Typography.Text
                  type="secondary"
                  className="storyboard-page-summary"
                  title={page.story_content}
                >
                  {page.story_content}
                </Typography.Text>
              </div>
            ),
            extra: (
              <Space
                size="small"
                onClick={(event) => event.stopPropagation()}
              >
                <Button
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={() => void handleCopyPrompt(page)}
                >
                  复制提示词
                </Button>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => openEdit(page)}
                >
                  编辑
                </Button>
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => handleDeletePage(page)}
                >
                  删除
                </Button>
              </Space>
            ),
            children: (
              // 纯文案排版：标签在上、内容在下，不使用表格，便于直接阅读与复制
              <div className="storyboard-script">
                <div className="script-field">
                  <span className="script-label">本页故事内容</span>
                  <p className="script-text">{page.story_content}</p>
                </div>

                <div className="script-field">
                  <span className="script-label">出场人物</span>
                  {page.characters.length > 0 ? (
                    <Space wrap size={[4, 4]}>
                      {page.characters.map((name) => (
                        <Tag key={name}>{name}</Tag>
                      ))}
                    </Space>
                  ) : (
                    <Typography.Text type="secondary">无</Typography.Text>
                  )}
                </div>

                <div className="script-field">
                  <span className="script-label">人物设定回顾</span>
                  <p className="script-text">{page.character_review}</p>
                </div>

                <div className="script-field">
                  <span className="script-label">场景描述</span>
                  <p className="script-text">{page.scene}</p>
                </div>

                <div className="script-field">
                  <span className="script-label">动作与状态</span>
                  <p className="script-text">{page.action_state}</p>
                </div>

                <div className="script-field">
                  <span className="script-label">变化说明</span>
                  <p className="script-text">{page.change_note}</p>
                </div>

                <div className="script-field">
                  <span className="script-label">主要旁白</span>
                  <p className="script-text">{page.narration_main}</p>
                </div>

                <div className="script-field">
                  <span className="script-label">标红关键词</span>
                  {page.narration_highlight ? (
                    <div>
                      <Tag color="red">{page.narration_highlight}</Tag>
                    </div>
                  ) : (
                    <Typography.Text type="secondary">无</Typography.Text>
                  )}
                </div>

                <div className="script-field">
                  <span className="script-label">副旁白</span>
                  <p className="script-text">{page.narration_sub}</p>
                </div>

                <div className="script-field">
                  <span className="script-label">对话气泡</span>
                  {page.dialogues.length > 0 ? (
                    page.dialogues.map((line, index) => (
                      <p className="script-text script-dialogue" key={index}>
                        {line}
                      </p>
                    ))
                  ) : (
                    <Typography.Text type="secondary">无</Typography.Text>
                  )}
                </div>

                <div className="script-field">
                  <span className="script-label">镜头景别</span>
                  <div>
                    <Tag>{page.shot_type}</Tag>
                  </div>
                </div>

                <div className="script-field">
                  <span className="script-label">
                    生图提示词
                    <Button
                      size="small"
                      type="link"
                      icon={<CopyOutlined />}
                      onClick={() => void handleCopyPrompt(page)}
                      style={{ paddingLeft: 0 }}
                    >
                      复制提示词
                    </Button>
                  </span>
                  <div className="prompt-sections">
                    {parseImagePrompt(page.image_prompt).map(
                      (section, index) => (
                        <div
                          className="prompt-section"
                          key={`${section.label}-${index}`}
                        >
                          <span className="prompt-section-label">
                            【{section.label}】
                          </span>
                          <p className="prompt-section-text">{section.text}</p>
                        </div>
                      ),
                    )}
                  </div>
                </div>
              </div>
            ),
          }))}
        />
      )}

      {/* 原文 / 优化文对比与 AI 改动解读 */}
      <StoryCompareModal
        open={compareOpen}
        storyId={story.id}
        original={story.content}
        optimized={breakdown.optimized_content}
        aiEnabled={aiEnabled}
        isStale={breakdown.is_content_stale}
        onClose={() => setCompareOpen(false)}
      />

      {/* 单页编辑 */}
      <Modal
        title={editingPage ? `编辑第 ${editingPage.page_number} 页` : '编辑分镜页'}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={() => void savePage()}
        confirmLoading={pageSaving}
        okText="保存"
        cancelText="取消"
        width={880}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="is_flashback" label="回忆页" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Form.Item
            name="page_role"
            label="页面作用"
            extra="第 1 页固定为钩子封面；其余页选择本页在故事中的主要作用，会显示在标题栏。"
          >
            <Select
              allowClear
              placeholder="选择本页作用（可不选）"
              options={PAGE_ROLE_OPTIONS}
            />
          </Form.Item>

          <Form.Item
            name="story_content"
            label="本页故事内容"
            rules={[{ required: true, message: '请填写本页故事内容' }]}
            extra="概括本页讲什么；若为回忆页请在右侧开关标记。"
          >
            <Input.TextArea rows={3} maxLength={4000} showCount />
          </Form.Item>

          <Form.Item name="characters" label="出场人物">
            <Select
              mode="tags"
              maxCount={20}
              placeholder="选择或输入出场人物姓名"
              options={characterOptions}
            />
          </Form.Item>

          <Form.Item
            name="character_review"
            label="人物设定回顾"
            rules={[{ required: true, message: '请填写人物设定回顾' }]}
          >
            <Input.TextArea rows={2} maxLength={4000} showCount />
          </Form.Item>

          <Form.Item
            name="scene"
            label="场景描述"
            rules={[{ required: true, message: '请填写场景描述' }]}
          >
            <Input.TextArea rows={2} maxLength={4000} showCount />
          </Form.Item>

          <Form.Item
            name="action_state"
            label="动作与状态"
            rules={[{ required: true, message: '请填写动作与状态' }]}
          >
            <Input.TextArea rows={2} maxLength={4000} showCount />
          </Form.Item>

          <Form.Item
            name="change_note"
            label="变化说明"
            rules={[{ required: true, message: '请填写变化说明' }]}
          >
            <Input.TextArea rows={2} maxLength={4000} showCount />
          </Form.Item>

          <Form.Item
            name="narration_main"
            label="主要旁白"
            rules={[{ required: true, message: '请填写主要旁白' }]}
          >
            <Input maxLength={200} showCount />
          </Form.Item>

          <Form.Item name="narration_highlight" label="标红关键词">
            <Input maxLength={100} showCount placeholder="需要标红强调的词" />
          </Form.Item>

          <Form.Item
            name="narration_sub"
            label="副旁白"
            rules={[{ required: true, message: '请填写副旁白' }]}
          >
            <Input.TextArea rows={2} maxLength={4000} showCount />
          </Form.Item>

          <Form.Item
            name="dialogues_text"
            label="对话气泡"
            extra="每行一句，最多 2 句，单句不超过 100 字。"
            rules={[
              {
                validator: (_, value: string) => {
                  const lines = parseDialogues(value)
                  if (lines.length > 2) {
                    return Promise.reject(new Error('最多 2 句对话'))
                  }
                  if (lines.some((line) => line.length > 100)) {
                    return Promise.reject(new Error('单句对话不能超过 100 字'))
                  }
                  return Promise.resolve()
                },
              },
            ]}
          >
            <Input.TextArea rows={2} placeholder="小八老师：你应该有A8吧？" />
          </Form.Item>

          <Form.Item
            name="shot_type"
            label="镜头景别"
            rules={[{ required: true, message: '请选择景别' }]}
          >
            <Select options={SHOT_TYPE_OPTIONS} />
          </Form.Item>

          <Form.Item
            name="image_prompt"
            label="生图提示词"
            rules={[{ required: true, message: '请填写生图提示词' }]}
            extra="角色外形用 {{角色名}} 变量引用角色设定卡；变量在外部生图 AI 中绑定参考图后再使用。"
          >
            <Input.TextArea rows={8} maxLength={8000} showCount />
          </Form.Item>
        </Form>
      </Modal>

      {/* 优化后文章编辑 */}
      <Modal
        title="编辑优化后文章"
        open={optimizedOpen}
        onCancel={() => setOptimizedOpen(false)}
        onOk={() => void saveOptimized()}
        confirmLoading={optimizedSaving}
        okText="保存"
        cancelText="取消"
        width={880}
        destroyOnHidden
      >
        <Input.TextArea
          rows={16}
          maxLength={60000}
          showCount
          value={optimizedText}
          onChange={(event) => setOptimizedText(event.target.value)}
        />
      </Modal>
    </div>
  )
}
