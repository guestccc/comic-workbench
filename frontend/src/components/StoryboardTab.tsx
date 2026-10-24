import { useEffect, useMemo, useState } from 'react'
import {
  App,
  AutoComplete,
  Button,
  Checkbox,
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
import ImageUpload from './ImageUpload'
import { api, getErrorMessage } from '../api/client'
import type {
  Story,
  StoryboardChapterRead,
  StoryboardMappingItem,
  StoryboardPage,
  StoryboardPagePayload,
  StoryboardShotType,
  StoryBreakdown,
} from '../types'
import { copyText } from '../utils/clipboard'
import {
  formatImagePrompt,
  locateNarrationHighlight,
  parseImagePrompt,
  type ImagePromptContext,
} from '../utils/formatPrompt'

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
  camera_angle: string
  image_prompt: string
}

const SHOT_TYPE_OPTIONS: { value: StoryboardShotType; label: string }[] = [
  { value: '全景', label: '全景' },
  { value: '中景', label: '中景' },
  { value: '特写', label: '特写' },
]

/** 机位方位候选词（允许自由输入组合，如「俯视·侧面」）。 */
const CAMERA_ANGLE_OPTIONS = [
  '正面平视',
  '45°侧面',
  '正侧面',
  '背面',
  '过肩视角',
  '俯视',
  '仰视',
  '主观视角',
].map((value) => ({ value }))

/** 页面作用：新流程不生成钩子页；「钩子封面」仅保留用于旧数据或手动标注。 */
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

/** 页面在界面上的显示名：有章节时用章内页码，否则回退到全局页码。 */
function pageDisplayLabel(
  page: StoryboardPage,
  chapters: StoryboardChapterRead[],
): string {
  if (page.chapter_number != null && page.chapter_page_number != null) {
    return `第${page.chapter_number}章第${page.chapter_page_number}页`
  }
  return `第${page.display_page_number ?? page.page_number}页`
}

/** 图片里显示的页码：优先使用服务端计算值，旧响应才本地回退。 */
function pageImageNumber(page: StoryboardPage): number {
  return (
    page.display_page_number ??
    page.chapter_page_number ??
    page.page_number
  )
}

/** 把分镜页的结构化字段整理成提示词格式化上下文。 */
function toPromptContext(page: StoryboardPage): ImagePromptContext {
  return {
    dialogues: page.dialogues,
    cameraAngle: page.camera_angle,
    // 图片里的页码用章内页码；全局页码只作为接口 / 文件编号
    pageNumber: pageImageNumber(page),
    narration: {
      main: page.narration_main,
      highlight: page.narration_highlight,
      sub: page.narration_sub,
    },
  }
}

/** 标红词的位置说明；找不到时提醒用户该页不会标红。 */
function describeHighlight(page: StoryboardPage): string {
  if (!page.narration_highlight.trim()) return ''
  const location = locateNarrationHighlight({
    main: page.narration_main,
    highlight: page.narration_highlight,
    sub: page.narration_sub,
  })
  if (!location) return '未在旁白中找到，生图时不标红'
  return `标红位置：${location.block === 'main' ? '主旁白' : '副旁白'} · ${location.position}`
}

/** 成品图大小上限（与后端 MAX_PAGE_IMAGE_BYTES 保持一致，格式校验由 ImageUpload 统一处理）。 */
const PAGE_IMAGE_MAX_SIZE = 15 * 1024 * 1024

/**
 * 本页对应的优化文原段。
 *
 * 原段来自分镜对照表（mapping.source_text），按 mapping_page_number 关联；
 * 只读展示，方便对照本页脚本相比原文做了哪些取舍。
 */
function OriginalSegment({ item }: { item?: StoryboardMappingItem }) {
  if (!item) return null
  const position = [item.paragraph, item.part].filter(Boolean).join(' · ')
  return (
    <section className="page-sheet-section page-sheet-source">
      <h4 className="page-sheet-section-title">
        原文摘录
        {position && (
          <span className="page-sheet-source-position">{position}</span>
        )}
      </h4>
      <blockquote className="page-sheet-source-text">
        {item.source_text}
      </blockquote>
    </section>
  )
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

  // 分镜脚本按章节折叠：章节和页都默认收起，避免长列表一次铺开
  const [activeChapterKeys, setActiveChapterKeys] = useState<string[]>([])
  // 受控的展开页码：默认全部折叠，支持一键展开 / 折叠全部
  const [activePageKeys, setActivePageKeys] = useState<string[]>([])
  // 批量复制选中的页面；只存在前端，不写数据库
  const [selectedPageNumbers, setSelectedPageNumbers] = useState<Set<number>>(
    new Set(),
  )

  // 页面被删除或重新生成后，清掉不存在的选中项
  useEffect(() => {
    const valid = new Set((breakdown?.pages ?? []).map((page) => page.page_number))
    setSelectedPageNumbers((previous) => {
      const next = new Set(
        [...previous].filter((pageNumber) => valid.has(pageNumber)),
      )
      return next.size === previous.size ? previous : next
    })
  }, [breakdown])

  const selectedPages = useMemo(
    () =>
      (breakdown?.pages ?? [])
        .filter((page) => selectedPageNumbers.has(page.page_number))
        .sort((left, right) => left.page_number - right.page_number),
    [breakdown, selectedPageNumbers],
  )

  const [optimizedOpen, setOptimizedOpen] = useState(false)
  const [optimizedText, setOptimizedText] = useState('')
  const [optimizedSaving, setOptimizedSaving] = useState(false)

  // 成品图上传中的页码集合；imageVersions 用于替换图片后打破浏览器缓存
  const [imageBusy, setImageBusy] = useState<Record<number, boolean>>({})
  const [imageVersions, setImageVersions] = useState<Record<number, number>>({})

  /** 复制单页生图提示词。 */
  const handleCopyPrompt = async (page: StoryboardPage) => {
    try {
      await copyText(
        formatImagePrompt(page.image_prompt, toPromptContext(page)),
      )
      message.success(
        `${pageDisplayLabel(page, breakdown?.chapters ?? [])} 生图提示词已复制`,
      )
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  /** 勾选 / 取消勾选一组页面（整章或整章未分章组）。 */
  const setPagesSelected = (pages: StoryboardPage[], checked: boolean) => {
    setSelectedPageNumbers((previous) => {
      const next = new Set(previous)
      pages.forEach((page) => {
        if (checked) {
          next.add(page.page_number)
        } else {
          next.delete(page.page_number)
        }
      })
      return next
    })
  }

  /** 批量复制：按全局页码顺序输出，每页复用单页复制渲染器。 */
  const handleCopySelected = async () => {
    if (selectedPages.length === 0) {
      message.warning('请先勾选要复制的分镜页')
      return
    }

    const total = selectedPages.length
    const chapters = breakdown?.chapters ?? []
    const chapterNumberOf = (page: StoryboardPage): number | undefined => {
      if (page.chapter_number != null) return page.chapter_number
      if (page.mapping_page_number == null) return undefined
      return chapters.find((chapter) =>
        chapter.mapping_page_numbers.includes(page.mapping_page_number!),
      )?.chapter_number
    }

    const blocks = selectedPages.map((page, index) => {
      const chapterNumber = chapterNumberOf(page)
      const title =
        chapterNumber == null
          ? ''
          : chapters.find(
              (chapter) => chapter.chapter_number === chapterNumber,
            )?.title ?? ''
      const chapterLabel =
        chapterNumber == null
          ? ''
          : `第${chapterNumber}章${title ? ` · ${title}` : ''} · `
      return [
        `=== 第${index + 1}张 / 共${total}张 ===`,
        `${chapterLabel}${formatImagePrompt(
          page.image_prompt,
          toPromptContext(page),
        )}`,
      ].join('\n')
    })

    const text = `请按顺序生成以下 ${total} 张条漫图片。每张单独生成一张完整图片，不要合并成一张，不要分格。\n\n${blocks.join(
      '\n\n---\n\n',
    )}`
    try {
      await copyText(text)
      message.success(`已复制 ${total} 页生图提示词（按章节顺序）`)
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  /** 上传 / 替换某页成品图；上传成功即视为该页完成。类型与大小由 ImageUpload 统一校验。 */
  const handleUploadImage = async (page: StoryboardPage, file: File) => {
    if (!breakdown) return

    setImageBusy((previous) => ({ ...previous, [page.page_number]: true }))
    try {
      await api.uploadStoryboardPageImage(
        breakdown.story_id,
        page.page_number,
        file,
      )
      setImageVersions((previous) => ({
        ...previous,
        [page.page_number]: Date.now(),
      }))
      message.success(
        `${pageDisplayLabel(page, breakdown?.chapters ?? [])} 成品图已上传，标记为完成`,
      )
      await onRefresh()
    } catch (error) {
      message.error(getErrorMessage(error))
      // 抛出后由 ImageUpload 保持上传弹窗打开，方便重试
      throw error
    } finally {
      setImageBusy((previous) => ({ ...previous, [page.page_number]: false }))
    }
  }

  /** 删除某页成品图，取消完成标记。 */
  const handleDeleteImage = (page: StoryboardPage) => {
    if (!breakdown) return
    modal.confirm({
      title: `删除${pageDisplayLabel(
        page,
        breakdown.chapters,
      )}的成品图？`,
      content: '删除后该页恢复为未完成状态，图片文件会从本地删除。',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteStoryboardPageImage(
            breakdown.story_id,
            page.page_number,
          )
          message.success('成品图已删除')
          await onRefresh()
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  /** 替换图片后 URL 不变，用版本号参数强制浏览器重新加载。 */
  const pageImageSrc = (page: StoryboardPage): string | null => {
    if (!page.image_url) return null
    const version = imageVersions[page.page_number]
    return version ? `${page.image_url}?v=${version}` : page.image_url
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
      camera_angle: page.camera_angle,
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
      // 来源对照段 / 章节由生成时写入；手动编辑不修改它们
      mapping_page_number: editingPage.mapping_page_number ?? undefined,
      chapter_number: editingPage.chapter_number ?? undefined,
      chapter_page_number: editingPage.chapter_page_number ?? undefined,
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
      camera_angle: (values.camera_angle ?? '').trim(),
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
      message.success(
        `${pageDisplayLabel(editingPage, breakdown.chapters)}已保存`,
      )
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
      title: `删除${pageDisplayLabel(page, breakdown.chapters)}？`,
      content:
        '删除后不可恢复，章节页码会出现空号。如需继续生成，请先清空全部分镜页面，再按新的章节规划重新生成。',
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
        '将删除全部正文分镜页及其成品图，但保留优化后文章、角色设定卡、分镜对照表、章节规划以及章节封面/引导卡。要调整章节或新增/删除对照段时，先清空正文页再按新规划重新生成。',
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
        '将删除优化后文章、角色设定卡、分镜对照表与全部分镜页面，且不可恢复。',
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
          先点击页面右上角「复制分镜对照指令」，粘贴到本项目的 Claude Code 中运行；
          确认分镜对照表顺序无误后，再复制「分镜头脚本指令」逐页生成分镜。
        </Typography.Text>
      </Empty>
    )
  }

  const characterOptions = breakdown.characters.map((card) => ({
    value: card.name,
    label: card.role ? `${card.name}（${card.role}）` : card.name,
  }))

  // 分镜页按 mapping_page_number 关联对照表原段，脚本页只展示，不重复存储
  const mappingByPage = new Map(
    breakdown.mapping.map((item) => [item.page_number, item]),
  )

  // 有成品图的页数，用于顶部进度提示
  const doneCount = breakdown.pages.filter((page) => page.image_url).length

  // 分镜页按章节归组：优先用页面上的章号，旧数据回退到对照段所属章节
  const chapterByMapping = new Map<number, number>()
  breakdown.chapters.forEach((chapter) => {
    chapter.mapping_page_numbers.forEach((mappingNumber) => {
      chapterByMapping.set(mappingNumber, chapter.chapter_number)
    })
  })
  const chapterNumberOfPage = (page: StoryboardPage): number | undefined =>
    page.chapter_number ??
    (page.mapping_page_number != null
      ? chapterByMapping.get(page.mapping_page_number)
      : undefined)

  const pagesByChapter = new Map<number, StoryboardPage[]>()
  const unassignedPages: StoryboardPage[] = []
  breakdown.pages.forEach((page) => {
    const chapterNumber = chapterNumberOfPage(page)
    if (
      chapterNumber == null ||
      !breakdown.chapters.some(
        (chapter) => chapter.chapter_number === chapterNumber,
      )
    ) {
      unassignedPages.push(page)
      return
    }
    const list = pagesByChapter.get(chapterNumber) ?? []
    list.push(page)
    pagesByChapter.set(chapterNumber, list)
  })
  const chapterPageOrder = (left: StoryboardPage, right: StoryboardPage) =>
    (left.chapter_page_number ?? left.page_number) -
    (right.chapter_page_number ?? right.page_number)
  pagesByChapter.forEach((list) => list.sort(chapterPageOrder))
  unassignedPages.sort((left, right) => left.page_number - right.page_number)

  const chapterGroups = breakdown.chapters.map((chapter) => ({
    key: `chapter-${chapter.chapter_number}`,
    chapter,
    pages: pagesByChapter.get(chapter.chapter_number) ?? [],
  }))
  const allChapterKeys = [
    ...chapterGroups.map((group) => group.key),
    ...(unassignedPages.length > 0 ? ['unassigned'] : []),
  ]
  const allPageKeys = breakdown.pages.map((page) => String(page.page_number))
  const hasExpanded =
    activeChapterKeys.length > 0 || activePageKeys.length > 0

  /** 生成某一章（或未分章）下的分镜页折叠项。 */
  const renderPageItems = (groupPages: StoryboardPage[]) =>
    groupPages.map((page) => ({
      key: String(page.page_number),
      // 已上传成品图的页整行淡绿，扫一眼就能看出进度
      className: page.image_url ? 'storyboard-page-done' : undefined,
      label: (
        <div className="storyboard-page-label">
          {/* 勾选后加入批量复制；阻止冒泡，避免顺带展开/收起 */}
          <Checkbox
            checked={selectedPageNumbers.has(page.page_number)}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) =>
              setPagesSelected([page], event.target.checked)
            }
          />
          {/* 已完成标记放在页码前面，扫一眼即可分辨进度 */}
          {page.image_url && <Tag color="success">已完成</Tag>}
          <Typography.Text strong className="storyboard-page-title">
            {pageDisplayLabel(page, breakdown.chapters)}
          </Typography.Text>
          {page.chapter_number != null && (
            <Tag color="geekblue">第{page.chapter_number}章</Tag>
          )}
          {page.mapping_page_number != null && (
            <Tag>对照第{page.mapping_page_number}段</Tag>
          )}
          {page.page_role && (
            <Tag color={PAGE_ROLE_COLORS[page.page_role] ?? 'default'}>
              {page.page_role}
            </Tag>
          )}
          {page.is_flashback && <Tag color="blue">回忆页</Tag>}
          {page.camera_angle && <Tag color="cyan">{page.camera_angle}</Tag>}
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
        <Space size="small" onClick={(event) => event.stopPropagation()}>
          {/* 标题栏直接上传成品图，无需展开折叠面板；交互与展开区一致（弹窗选择或粘贴） */}
          <ImageUpload
            variant="button"
            imageUrl={pageImageSrc(page)}
            uploadText="上传成品图"
            replaceText="替换图片"
            maxSizeBytes={PAGE_IMAGE_MAX_SIZE}
            onUpload={(file) => handleUploadImage(page, file)}
            disabled={imageBusy[page.page_number]}
          />
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
        // 双栏拍摄单：左侧剧本字段，右侧成品图与生图提示词
        <div className="page-sheet">
          <div className="page-sheet-meta">
            <Tag color="blue">
              {pageDisplayLabel(page, breakdown.chapters)}
            </Tag>
            {page.chapter_number != null && (
              <Tag color="geekblue">第{page.chapter_number}章</Tag>
            )}
            {page.mapping_page_number != null && (
              <Tag>来源：对照第{page.mapping_page_number}段</Tag>
            )}
            {page.page_role && (
              <Tag color={PAGE_ROLE_COLORS[page.page_role] ?? 'default'}>
                {page.page_role}
              </Tag>
            )}
            {page.is_flashback && <Tag color="blue">回忆页</Tag>}
            <Tag>{page.shot_type}</Tag>
            {page.camera_angle && <Tag color="cyan">{page.camera_angle}</Tag>}
            {page.characters.map((name) => (
              <Tag key={name}>{name}</Tag>
            ))}
          </div>

          <div className="page-sheet-grid">
            <div className="page-sheet-script">
              <OriginalSegment
                item={
                  page.mapping_page_number != null
                    ? mappingByPage.get(page.mapping_page_number)
                    : undefined
                }
              />

              <div className="script-field">
                <span className="script-label">本页内容</span>
                <p className="script-text page-sheet-lead">
                  {page.story_content}
                </p>
              </div>

              <section className="page-sheet-section">
                <h4 className="page-sheet-section-title">画面</h4>
                <div className="script-field">
                  <span className="script-label">场景</span>
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
              </section>

              <section className="page-sheet-section page-sheet-narration">
                <h4 className="page-sheet-section-title">旁白</h4>
                <div className="page-sheet-main-narration">
                  {page.narration_main}
                </div>
                {page.narration_highlight && (
                  <div className="page-sheet-highlight">
                    <Tag color="red">{page.narration_highlight}</Tag>
                    <Typography.Text
                      type="secondary"
                      style={{ fontSize: 12 }}
                    >
                      {describeHighlight(page)}
                    </Typography.Text>
                  </div>
                )}
                <div className="script-field">
                  <span className="script-label">副旁白</span>
                  <p className="script-text">{page.narration_sub}</p>
                </div>
              </section>

              <section className="page-sheet-section">
                <h4 className="page-sheet-section-title">对话</h4>
                {page.dialogues.length > 0 ? (
                  page.dialogues.map((line, index) => (
                    <p className="script-text script-dialogue" key={index}>
                      {line}
                    </p>
                  ))
                ) : (
                  <Typography.Text type="secondary">无</Typography.Text>
                )}
              </section>

              <div className="page-sheet-character-review">
                <span className="script-label">人物设定回顾</span>
                <Typography.Paragraph
                  type="secondary"
                  ellipsis={{
                    rows: 2,
                    expandable: true,
                    symbol: '展开',
                  }}
                  style={{ marginBottom: 0 }}
                >
                  {page.character_review}
                </Typography.Paragraph>
              </div>
            </div>

            <div className="page-sheet-visual">
              <div className="page-sheet-card">
                <div className="page-sheet-card-head">
                  <span className="script-label">成品图</span>
                </div>
                <ImageUpload
                  variant="thumb"
                  imageUrl={pageImageSrc(page)}
                  uploadText="上传成品图并标记完成"
                  replaceText="替换图片"
                  maxSizeBytes={PAGE_IMAGE_MAX_SIZE}
                  onUpload={(file) => handleUploadImage(page, file)}
                  onRemove={() => handleDeleteImage(page)}
                  disabled={imageBusy[page.page_number]}
                />
              </div>

              <div className="page-sheet-card page-sheet-prompt-card">
                <div className="page-sheet-card-head">
                  <span className="script-label">生图提示词</span>
                  <Button
                    size="small"
                    type="link"
                    icon={<CopyOutlined />}
                    onClick={() => void handleCopyPrompt(page)}
                    style={{ paddingInline: 0 }}
                  >
                    复制提示词
                  </Button>
                </div>
                <div className="prompt-sections">
                  {parseImagePrompt(
                    page.image_prompt,
                    toPromptContext(page),
                  ).map((section, index) => (
                    <div
                      className="prompt-section"
                      key={`${section.label}-${index}`}
                    >
                      <span className="prompt-section-label">
                        【{section.label}】
                      </span>
                      <p className="prompt-section-text">{section.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      ),
    }))

  /** 章节内部（或未分章时）的分镜页折叠列表。 */
  const renderPageCollapse = (groupPages: StoryboardPage[]) => (
    <Collapse
      ghost
      className="storyboard-pages"
      activeKey={activePageKeys}
      onChange={(keys) =>
        setActivePageKeys(
          (Array.isArray(keys) ? keys : [keys]).map(String),
        )
      }
      items={renderPageItems(groupPages)}
    />
  )

  return (
    <div>
      <div className="story-tab-toolbar">
        <Space wrap>
          <Typography.Text type="secondary">
            共 {breakdown.pages.length} 页
          </Typography.Text>
          {breakdown.chapters.length > 0 && (
            <Typography.Text type="secondary">
              · {breakdown.chapters.length} 章
            </Typography.Text>
          )}
          {breakdown.pages.length > 0 && (
            <Typography.Text type="secondary">
              · 已完成 {doneCount} 页
            </Typography.Text>
          )}
          {breakdown.pages.length > 0 && (
            <Typography.Text type="secondary">
              · 章内页码 · 提示词使用 {'{{角色名}}'} 变量
            </Typography.Text>
          )}
          {breakdown.pages.length > 0 && (
            <Button
              size="small"
              icon={
                hasExpanded ? (
                  <MenuFoldOutlined />
                ) : (
                  <MenuUnfoldOutlined />
                )
              }
              onClick={() => {
                if (hasExpanded) {
                  setActiveChapterKeys([])
                  setActivePageKeys([])
                  return
                }
                setActiveChapterKeys(allChapterKeys)
                setActivePageKeys(allPageKeys)
              }}
            >
              {hasExpanded ? '全部折叠' : '全部展开'}
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

      {breakdown.pages.length > 0 && (
        <div className="storyboard-selection-bar">
          <Checkbox
            checked={selectedPages.length === breakdown.pages.length}
            indeterminate={
              selectedPages.length > 0 &&
              selectedPages.length < breakdown.pages.length
            }
            onChange={(event) =>
              setPagesSelected(breakdown.pages, event.target.checked)
            }
          >
            全选本故事
          </Checkbox>
          <Typography.Text type="secondary">
            已选 {selectedPages.length} 页
          </Typography.Text>
          <Button
            size="small"
            type="primary"
            icon={<CopyOutlined />}
            disabled={selectedPages.length === 0}
            onClick={() => void handleCopySelected()}
          >
            复制选中提示词
          </Button>
          <Button
            size="small"
            disabled={selectedPages.length === 0}
            onClick={() => setSelectedPageNumbers(new Set())}
          >
            清空选择
          </Button>
        </div>
      )}

      {breakdown.pages.length === 0 ? (
        <Empty description="还没有正文分镜页">
          <Typography.Text type="secondary">
            到「章节发布」按章复制脚本指令生成正文；封面和引导卡也在那里管理。
          </Typography.Text>
        </Empty>
      ) : breakdown.chapters.length > 0 ? (
        // 分镜脚本按章节归组；章节和页都默认收起，点标题栏展开
        <Collapse
          ghost
          className="storyboard-chapters"
          activeKey={activeChapterKeys}
          onChange={(keys) =>
            setActiveChapterKeys(
              (Array.isArray(keys) ? keys : [keys]).map(String),
            )
          }
          items={[
            ...chapterGroups.map((group) => {
              const done = group.pages.filter((page) => page.image_url).length
              const selectedCount = group.pages.filter((page) =>
                selectedPageNumbers.has(page.page_number),
              ).length
              const allSelected =
                group.pages.length > 0 &&
                selectedCount === group.pages.length
              const firstMapping = group.chapter.mapping_page_numbers[0]
              const lastMapping =
                group.chapter.mapping_page_numbers[
                  group.chapter.mapping_page_numbers.length - 1
                ]
              return {
                key: group.key,
                className: 'storyboard-chapter',
                label: (
                  <div className="storyboard-chapter-label">
                    <Checkbox
                      checked={allSelected}
                      indeterminate={
                        !allSelected && selectedCount > 0
                      }
                      disabled={group.pages.length === 0}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) =>
                        setPagesSelected(group.pages, event.target.checked)
                      }
                    />
                    <Typography.Text strong>
                      第 {group.chapter.chapter_number} 章 ·{' '}
                      {group.chapter.title}
                    </Typography.Text>
                    <Tag color="blue">正文 {group.pages.length} 页</Tag>
                    {group.pages.length > 0 && (
                      <Tag
                        color={
                          done === group.pages.length ? 'success' : 'default'
                        }
                      >
                        已完成 {done}/{group.pages.length}
                      </Tag>
                    )}
                    {firstMapping != null && (
                      <Tag>
                        对照第 {firstMapping}
                        {lastMapping != null && lastMapping !== firstMapping
                          ? `–${lastMapping}`
                          : ''}{' '}
                        段
                      </Tag>
                    )}
                    {group.pages.length === 0 && (
                      <Tag color="orange">待生成脚本</Tag>
                    )}
                  </div>
                ),
                children:
                  group.pages.length > 0 ? (
                    renderPageCollapse(group.pages)
                  ) : (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="本章还没有正文分镜页，请到「章节发布」复制脚本指令生成"
                    />
                  ),
              }
            }),
            ...(unassignedPages.length > 0
              ? [
                  {
                    key: 'unassigned',
                    className: 'storyboard-chapter',
                    label: (
                      <div className="storyboard-chapter-label">
                        <Checkbox
                          checked={unassignedPages.every((page) =>
                            selectedPageNumbers.has(page.page_number),
                          )}
                          indeterminate={
                            unassignedPages.some((page) =>
                              selectedPageNumbers.has(page.page_number),
                            ) &&
                            !unassignedPages.every((page) =>
                              selectedPageNumbers.has(page.page_number),
                            )
                          }
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) =>
                            setPagesSelected(
                              unassignedPages,
                              event.target.checked,
                            )
                          }
                        />
                        <Typography.Text strong>未分章</Typography.Text>
                        <Tag>{unassignedPages.length} 页</Tag>
                        <Typography.Text type="secondary">
                          这些页没有归入章节，请到「章节发布」检查章节规划
                        </Typography.Text>
                      </div>
                    ),
                    children: renderPageCollapse(unassignedPages),
                  },
                ]
              : []),
          ]}
        />
      ) : (
        renderPageCollapse(breakdown.pages)
      )}

      {/* 原文 / 优化文对比与 AI 改动解读 */}
      <StoryCompareModal
        open={compareOpen}
        storyId={story.id}
        original={story.content}
        optimized={breakdown.optimized_content}
        pages={breakdown.pages}
        mapping={breakdown.mapping}
        aiEnabled={aiEnabled}
        isStale={breakdown.is_content_stale}
        onClose={() => setCompareOpen(false)}
      />

      {/* 单页编辑 */}
      <Modal
        title={
          editingPage
            ? `编辑${pageDisplayLabel(editingPage, breakdown.chapters)}`
            : '编辑分镜页'
        }
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
            extra="新流程不生成钩子页；这里只标注本页在故事中的主要作用，会显示在标题栏。"
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

          <Form.Item
            name="narration_highlight"
            label="标红关键词"
            extra="必须是主要旁白或副旁白中的连续片段；生图时会内嵌在该句标红，不会单独占一行。"
          >
            <Input maxLength={100} showCount placeholder="需要标红强调的词" />
          </Form.Item>

          <Form.Item
            name="narration_sub"
            label="副旁白"
            rules={[{ required: true, message: '请填写副旁白' }]}
            extra="1–2 行，少于 50 个汉字（标点不计）；以「本页内容」为底稿，第一行交代情境，第二行写结果/情绪。需要两行时直接换行。"
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
            name="camera_angle"
            label="机位方位"
            rules={[{ required: true, message: '请填写机位方位' }]}
            extra="如「正面平视」「过肩视角」「俯视·侧面」；同一场景的相邻页不要使用相同的机位+景别组合。"
          >
            <AutoComplete
              options={CAMERA_ANGLE_OPTIONS}
              maxLength={50}
              placeholder="选择或输入机位方位"
            />
          </Form.Item>

          <Form.Item
            name="image_prompt"
            label="生图提示词"
            rules={[{ required: true, message: '请填写生图提示词' }]}
            extra="角色外形用 {{角色名}} 变量引用角色设定卡；【文字区】由上方旁白字段与对话气泡自动生成，复制时以结构化字段为准。"
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
