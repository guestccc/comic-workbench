import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Collapse,
  Empty,
  Form,
  Input,
  Modal,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  CloudUploadOutlined,
  CopyOutlined,
  DownloadOutlined,
  DownOutlined,
  EditOutlined,
  HistoryOutlined,
  PictureOutlined,
  ReloadOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  UpOutlined,
} from '@ant-design/icons'
import ImageUpload from './ImageUpload'
import ImageGenerationModal from './ImageGenerationModal'
import ChapterCoverOptimizerModal from './ChapterCoverOptimizerModal'
import CoverCopyOptionsModal from './CoverCopyOptionsModal'
import PromptSnapshotDrawer from './PromptSnapshotDrawer'
import ChapterAssetHistoryDrawer from './ChapterAssetHistoryDrawer'
import AliasStampModal from './AliasStampModal'
import { api, getErrorMessage } from '../api/client'
import type {
  ImageGenerationItem,
  ImageGenerationPreview,
  MappingReview,
  Story,
  StoryboardChapter,
  StoryboardChapterRead,
  StoryboardPage,
  StoryBreakdown,
} from '../types'
import { copyText } from '../utils/clipboard'
import { buildImageIngestInstruction } from '../utils/imageIngest'
import {
  buildChapterCoverInstructionPrompt,
  buildChapterGuideInstructionPrompt,
  buildChapterPageTargets,
  buildChapterPlanPrompt,
  buildChapterScriptPrompt,
  buildCharacterCardsPrompt,
} from '../utils/storyBreakdown'

interface StoryboardChaptersTabProps {
  story: Story
  breakdown: StoryBreakdown | null
  /** 是否已配置生图服务 */
  imageEnabled: boolean
  onRefresh: () => Promise<void>
}

interface ChapterEditValues {
  title: string
  cover_label: string
  cover_main: string
  cover_highlight: string
  cover_sub: string
  cover_prompt: string
  guide_text: string
  guide_sub: string
  guide_prompt: string
}

/** 章节 → 编辑表单值。Modal 内容可能晚于 useEffect 挂载，必须同时作为 initialValues 传入。 */
function chapterEditValues(chapter: StoryboardChapterRead): ChapterEditValues {
  return {
    title: chapter.title,
    cover_label: chapter.cover.label,
    cover_main: chapter.cover.narration_main,
    cover_highlight: chapter.cover.narration_highlight,
    cover_sub: chapter.cover.narration_sub,
    cover_prompt: chapter.cover.image_prompt,
    guide_text: chapter.guide.text,
    guide_sub: chapter.guide.sub_text,
    guide_prompt: chapter.guide.image_prompt,
  }
}

/** 成品图 / 章节图片上限，与后端 MAX_PAGE_IMAGE_BYTES 保持一致。 */
const CHAPTER_IMAGE_MAX_SIZE = 15 * 1024 * 1024

/** 本章是否已经上传过任何图片（封面 / 正文 / 引导卡）。 */
function chapterHasImages(
  chapter: StoryboardChapterRead,
  pages: StoryboardPage[],
): boolean {
  if (chapter.cover.image_url || chapter.guide.image_url) return true
  return pages.some(
    (page) =>
      page.chapter_number === chapter.chapter_number && Boolean(page.image_url),
  )
}

/** 触发浏览器下载；ZIP 内的文件名由服务端 Content-Disposition 决定。 */
function downloadUrl(url: string) {
  const link = document.createElement('a')
  link.href = url
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

/**
 * 章节发布 tab。
 *
 * 一章 = 一篇小红书笔记：1 封面 + 1..16 正文 + 1 引导卡。
 * 正文脚本按章生成；封面 / 引导卡有独立的生图提示词和图片上传。
 */
export default function StoryboardChaptersTab({
  story,
  breakdown,
  imageEnabled,
  onRefresh,
}: StoryboardChaptersTabProps) {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm<ChapterEditValues>()
  const [editing, setEditing] = useState<StoryboardChapterRead | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [mappingReview, setMappingReview] = useState<MappingReview | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)

  // 分镜对照还有未处理的审阅草稿时，不允许生成正文脚本
  useEffect(() => {
    let active = true
    api
      .getMappingReview(story.id)
      .then((review) => {
        if (active) setMappingReview(review)
      })
      .catch(() => {
        if (active) setMappingReview(null)
      })
    return () => {
      active = false
    }
  }, [story.id, breakdown?.mapping])

  const mappingDraft = mappingReview?.status === 'draft'
  const charactersReady = (breakdown?.characters.length ?? 0) > 0

  // 章节默认折叠，标题栏保留进度标签；需要操作时再展开对应章节
  const [activeChapterKeys, setActiveChapterKeys] = useState<string[]>([])
  const [promptHistoryChapter, setPromptHistoryChapter] = useState<StoryboardChapterRead | null>(null)
  const [assetHistory, setAssetHistory] = useState<{
    chapter: StoryboardChapterRead
    kind: 'cover' | 'guide'
  } | null>(null)
  const [coverOptimizerOpen, setCoverOptimizerOpen] = useState(false)
  const [coverOptimizerValues, setCoverOptimizerValues] = useState<{
    chapterTitle: string
    coverLabel: string
    coverMain: string
    coverSub: string
    coverHighlight: string
    imagePrompt: string
  } | null>(null)
  const [coverCopyOpen, setCoverCopyOpen] = useState(false)
  const [coverCopyValues, setCoverCopyValues] = useState<{
    chapterTitle: string
    coverLabel: string
    coverMain: string
    coverHighlight: string
    coverSub: string
  } | null>(null)

  // 生图对比弹窗：章节封面
  const [generationChapter, setGenerationChapter] =
    useState<StoryboardChapterRead | null>(null)
  const [generationOpen, setGenerationOpen] = useState(false)
  const [generationLoading, setGenerationLoading] = useState(false)
  const [generationPreview, setGenerationPreview] =
    useState<ImageGenerationPreview | null>(null)
  const [generationHistory, setGenerationHistory] = useState<
    ImageGenerationItem[]
  >([])
  const [generationBytes, setGenerationBytes] = useState(0)
  const [generationUsing, setGenerationUsing] = useState(false)
  const [aliasOpen, setAliasOpen] = useState(false)
  const [aliasChapters, setAliasChapters] = useState<number[]>([])

  const chapters = breakdown?.chapters ?? []
  const pages = breakdown?.pages ?? []

  const generatedContentPages = pages.filter(
    (page) => page.chapter_number != null,
  ).length
  const totalContentPages = chapters.reduce(
    (sum, chapter) => sum + chapter.mapping_page_numbers.length,
    0,
  )
  const hasAnyImages = chapters.some((chapter) =>
    chapterHasImages(chapter, pages),
  )
  const aliasImageCount =
    pages.filter((page) => page.image_url).length +
    chapters.reduce(
      (sum, chapter) =>
        sum +
        (chapter.cover.image_url ? 1 : 0) +
        (chapter.guide.image_url ? 1 : 0),
      0,
    )
  const pageByChapter = useMemo(() => {
    const chapterByMapping = new Map<number, number>()
    for (const chapter of chapters) {
      chapter.mapping_page_numbers.forEach((mappingNumber) => {
        chapterByMapping.set(mappingNumber, chapter.chapter_number)
      })
    }

    const result = new Map<number, Map<number, (typeof pages)[number]>>()
    for (const page of pages) {
      if (page.mapping_page_number == null) continue
      const chapterNumber =
        page.chapter_number ??
        chapterByMapping.get(page.mapping_page_number)
      if (chapterNumber == null) continue
      const chapterPages = result.get(chapterNumber) ?? new Map()
      chapterPages.set(page.mapping_page_number, page)
      result.set(chapterNumber, chapterPages)
    }
    return result
  }, [pages, chapters])

  const aliasChapterOptions = chapters.map((chapter) => {
    const chapterPages = pageByChapter.get(chapter.chapter_number)
    const count =
      (chapter.cover.image_url ? 1 : 0) +
      (chapter.guide.image_url ? 1 : 0) +
      (chapterPages
        ? [...chapterPages.values()].filter((page) => page.image_url).length
        : 0)
    return {
      value: chapter.chapter_number,
      label: `第${chapter.chapter_number}章 ${chapter.title}`,
      count,
    }
  })

  const copy = async (text: string, success: string) => {
    try {
      await copyText(text)
      message.success(success)
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  /** 复制章节封面/引导卡的回传指令。 */
  const handleCopyAssetIngest = (
    chapter: StoryboardChapterRead,
    target: 'cover' | 'guide',
  ) => {
    void copy(
      buildImageIngestInstruction({
        storyId: story.id,
        storyName: story.name,
        target,
        chapterNumber: chapter.chapter_number,
        chapterTitle: chapter.title,
      }),
      target === 'cover' ? '封面回传指令已复制' : '引导卡回传指令已复制',
    )
  }

  const handleCopyPlan = () => {
    if (!breakdown?.mapping?.length) {
      message.warning('还没有分镜对照表，请先完成「分镜对照」')
      return
    }
    if (pages.length > 0) {
      modal.warning({
        title: '已有正文分镜页，不能直接重新规划章节',
        content:
          '章节结构变化会让页面的章节归属和章内页码失效。请先到「分镜头脚本」清空全部分镜页面，再重新规划章节。',
        okText: '知道了',
      })
      return
    }
    const run = () =>
      void copy(
        buildChapterPlanPrompt(story.id),
        '章节规划指令已复制，运行后刷新查看章节结构',
      )
    if (chapters.length > 0) {
      modal.confirm({
        title: '重新生成章节规划？',
        content:
          '会覆盖现有章节划分、封面文字与引导卡文字；当前没有正文分镜页，不会影响页面数据。',
        okText: '复制指令',
        cancelText: '取消',
        onOk: run,
      })
      return
    }
    run()
  }

  const handleCopyChapterScript = (
    chapter: StoryboardChapterRead,
    force: boolean,
  ) => {
    if (!charactersReady) {
      message.warning('还没有角色卡，请先到「角色设定卡」复制角色卡指令并拆完角色')
      return
    }
    const run = () =>
      void copy(
        buildChapterScriptPrompt(
          story.id,
          chapter.chapter_number,
          chapters,
          pages,
          force,
        ),
        force
          ? `第 ${chapter.chapter_number} 章整章重做指令已复制`
          : `第 ${chapter.chapter_number} 章补页指令已复制`,
      )
    if (force) {
      modal.confirm({
        title: `重新生成第 ${chapter.chapter_number} 章全部正文？`,
        content:
          '会覆盖本章已有的正文分镜页；封面、引导卡和其他章节不受影响。',
        okText: '复制重做指令',
        cancelText: '取消',
        onOk: run,
      })
      return
    }
    run()
  }

  const loadGenerationHistory = async (chapter: StoryboardChapterRead) => {
    try {
      const data = await api.listImageGenerations(story.id, {
        targetType: 'chapter_cover',
        chapterNumber: chapter.chapter_number,
      })
      setGenerationHistory(data.items)
      setGenerationBytes(data.total_bytes)
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const startGeneration = async (chapter: StoryboardChapterRead) => {
    setGenerationChapter(chapter)
    setGenerationOpen(true)
    setGenerationLoading(true)
    setGenerationPreview(null)
    setGenerationHistory([])
    setGenerationBytes(0)
    try {
      const preview = await api.generateChapterCover(
        story.id,
        chapter.chapter_number,
      )
      setGenerationPreview(preview)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setGenerationLoading(false)
      void loadGenerationHistory(chapter)
    }
  }

  const confirmGenerateCover = (chapter: StoryboardChapterRead) => {
    if (!chapter.cover.image_prompt.trim()) {
      message.warning('本章还没有封面生图提示词，请先生成或填写提示词')
      return
    }
    modal.confirm({
      title: '立即生成章节封面？',
      content: `将用本章封面提示词和角色资产图生成 1 张封面，消耗一次生图额度。缺少资产图的角色会先被拦下。`,
      okText: '开始生成',
      cancelText: '取消',
      onOk: () => startGeneration(chapter),
    })
  }

  const openGenerationHistory = (chapter: StoryboardChapterRead) => {
    setGenerationChapter(chapter)
    setGenerationOpen(true)
    setGenerationPreview(null)
    setGenerationLoading(false)
    void loadGenerationHistory(chapter)
  }

  const handleUseGeneration = async (generationId: string) => {
    setGenerationUsing(true)
    try {
      await api.useImageGeneration(story.id, generationId)
      await onRefresh()
      setGenerationOpen(false)
      message.success('已使用这张章节封面')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setGenerationUsing(false)
    }
  }

  const handleClearGenerationHistory = async () => {
    if (!generationChapter) return
    try {
      const result = await api.clearImageGenerations(story.id, {
        targetType: 'chapter_cover',
        chapterNumber: generationChapter.chapter_number,
      })
      setGenerationHistory([])
      setGenerationBytes(0)
      message.success(`已清除 ${result.deleted} 张历史图片`)
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const handleCopyCharacterCardsInstruction = () => {
    void copy(
      buildCharacterCardsPrompt(story.id),
      '角色卡指令已复制，运行后刷新查看角色卡',
    )
  }

  const handleCopyCoverInstruction = (chapter: StoryboardChapterRead) => {
    if (!charactersReady) {
      message.warning('还没有角色卡，请先到「角色设定卡」复制角色卡指令并拆完角色')
      return
    }
    void copy(
      buildChapterCoverInstructionPrompt(
        story.id,
        chapter.chapter_number,
        chapter,
      ),
      `第 ${chapter.chapter_number} 章封面生成指令已复制`,
    )
  }

  const handleCopyGuideInstruction = (chapter: StoryboardChapterRead) => {
    if (!charactersReady) {
      message.warning('还没有角色卡，请先到「角色设定卡」复制角色卡指令并拆完角色')
      return
    }
    void copy(
      buildChapterGuideInstructionPrompt(
        story.id,
        chapter.chapter_number,
        chapter,
      ),
      `第 ${chapter.chapter_number} 章引导卡生成指令已复制`,
    )
  }

  const handleUploadChapterImage = async (
    chapter: StoryboardChapterRead,
    kind: 'cover' | 'guide',
    file: File,
  ) => {
    const key = `${chapter.chapter_number}-${kind}`
    setBusyKey(key)
    try {
      if (kind === 'cover') {
        await api.uploadChapterCover(story.id, chapter.chapter_number, file)
      } else {
        await api.uploadChapterGuide(story.id, chapter.chapter_number, file)
      }
      message.success(
        `第 ${chapter.chapter_number} 章${
          kind === 'cover' ? '封面' : '引导卡'
        }已上传`,
      )
      await onRefresh()
    } catch (error) {
      message.error(getErrorMessage(error))
      throw error
    } finally {
      setBusyKey(null)
    }
  }

  const handleDeleteChapterImage = (
    chapter: StoryboardChapterRead,
    kind: 'cover' | 'guide',
  ) => {
    modal.confirm({
      title: `删除第 ${chapter.chapter_number} 章的${
        kind === 'cover' ? '封面' : '引导卡'
      }图？`,
      content: '删除后可以重新上传，文字和提示词不会丢失。',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          if (kind === 'cover') {
            await api.deleteChapterCover(story.id, chapter.chapter_number)
          } else {
            await api.deleteChapterGuide(story.id, chapter.chapter_number)
          }
          message.success('图片已删除')
          await onRefresh()
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  const openEdit = (chapter: StoryboardChapterRead) => {
    setEditing(chapter)
    setCoverOptimizerOpen(false)
    setEditOpen(true)
  }

  // 弹窗使用 destroyOnHidden + preserve=false：Form 每次打开都会重新挂载，
  // 挂载时会用 initialValues 重置 store。因此章节值既作为 initialValues，
  // 也在表单已挂载后回填一次，避免时序差异导致字段为空。
  const editInitialValues = useMemo(
    () => (editing ? chapterEditValues(editing) : undefined),
    [editing],
  )
  useEffect(() => {
    if (!editOpen || !editInitialValues) return
    form.setFieldsValue(editInitialValues)
  }, [editOpen, editInitialValues, form])

  /** 点击时快照表单值，确保刚输入的封面内容一定被带到 AI 优化弹窗。 */
  const openCoverOptimizer = () => {
    const values = form.getFieldsValue()
    setCoverOptimizerValues({
      chapterTitle: values.title ?? '',
      coverLabel: values.cover_label ?? '',
      coverMain: values.cover_main ?? '',
      coverSub: values.cover_sub ?? '',
      coverHighlight: values.cover_highlight ?? '',
      imagePrompt: values.cover_prompt ?? '',
    })
    setCoverOptimizerOpen(true)
  }

  /** 封面文案方案也使用点击时的表单快照，避免未保存的修改丢失。 */
  const openCoverCopyOptions = () => {
    const values = form.getFieldsValue()
    setCoverCopyValues({
      chapterTitle: values.title ?? '',
      coverLabel: values.cover_label ?? '',
      coverMain: values.cover_main ?? '',
      coverHighlight: values.cover_highlight ?? '',
      coverSub: values.cover_sub ?? '',
    })
    setCoverCopyOpen(true)
  }

  const saveChapter = async () => {
    if (!editing) return
    let values: ChapterEditValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    const payload: StoryboardChapter[] = chapters.map((chapter) => {
      if (chapter.chapter_number !== editing.chapter_number) {
        return {
          chapter_number: chapter.chapter_number,
          title: chapter.title,
          mapping_page_numbers: chapter.mapping_page_numbers,
          cover: {
            label: chapter.cover.label,
            narration_main: chapter.cover.narration_main,
            narration_highlight: chapter.cover.narration_highlight,
            narration_sub: chapter.cover.narration_sub,
            image_prompt: chapter.cover.image_prompt,
          },
          guide: {
            text: chapter.guide.text,
            sub_text: chapter.guide.sub_text,
            image_prompt: chapter.guide.image_prompt,
          },
        }
      }
      return {
        chapter_number: chapter.chapter_number,
        title: (values.title ?? '').trim(),
        mapping_page_numbers: chapter.mapping_page_numbers,
        cover: {
          label: (values.cover_label ?? '').trim(),
          narration_main: (values.cover_main ?? '').trim(),
          narration_highlight: (values.cover_highlight ?? '').trim(),
          narration_sub: (values.cover_sub ?? '').trim(),
          image_prompt: (values.cover_prompt ?? '').trim(),
        },
        guide: {
          text: (values.guide_text ?? '').trim(),
          sub_text: (values.guide_sub ?? '').trim(),
          image_prompt: (values.guide_prompt ?? '').trim(),
        },
      }
    })

    setSaving(true)
    try {
      await api.patchBreakdown(story.id, { chapters: payload })
      setEditOpen(false)
      message.success('章节信息已保存')
      await onRefresh()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  if (!breakdown) {
    return (
      <Empty description="还没有拆解结果">
        <Typography.Text type="secondary">
          先完成「分镜对照」，再复制章节规划指令。
        </Typography.Text>
      </Empty>
    )
  }

  if (chapters.length === 0) {
    return (
      <>
        <Empty description="还没有章节规划">
          <Space direction="vertical" size={10} align="center">
            <Typography.Text type="secondary">
              一章 = 一篇小红书笔记：1 张封面 + 1–16 张正文 + 1 张引导卡，
              合计最多 18 张。先让 Claude 按剧情钩子拆章。
            </Typography.Text>
            <Space wrap>
              <Button
                type="primary"
                icon={<CopyOutlined />}
                onClick={handleCopyPlan}
                disabled={!breakdown.mapping.length}
              >
                复制章节规划指令
              </Button>
              <Button
                icon={<EditOutlined />}
                disabled={aliasImageCount === 0}
                onClick={() => {
                  setAliasChapters([])
                  setAliasOpen(true)
                }}
              >
                给正文页批量加别名（{aliasImageCount} 张）
              </Button>
            </Space>
          </Space>
        </Empty>
        <AliasStampModal
          open={aliasOpen}
          storyId={story.id}
          defaultAlias={story.zhihu_alias}
          defaultChapterNumbers={[]}
          imageCount={aliasImageCount}
          onClose={() => {
            setAliasOpen(false)
            setAliasChapters([])
          }}
          onDone={onRefresh}
        />
      </>
    )
  }

  return (
    <div className="chapter-tab">
      <div className="chapter-tab-toolbar">
        <Alert
          type="info"
          showIcon
          message={`共 ${chapters.length} 章 · 正文档 ${generatedContentPages}/${totalContentPages}`}
          description="每章 1 封面 + 最多 16 正文 + 1 引导卡 = 最多 18 张；正文按章生成，封面和引导卡单独生成。"
        />
        {mappingDraft && (
          <Alert
            type="warning"
            showIcon
            message="分镜对照还有未处理的审阅变更"
            description="请先到「分镜对照 → 审阅对照」逐条处理并应用，再生成正文脚本。"
          />
        )}
        {!charactersReady && (
          <Alert
            type="warning"
            showIcon
            message="还没有角色卡"
            description="角色卡是生图变量的唯一来源。先拆完全部角色并写回，再生成正文、封面和引导卡。"
            action={
              <Button
                size="small"
                type="primary"
                icon={<RobotOutlined />}
                onClick={handleCopyCharacterCardsInstruction}
              >
                复制角色卡指令
              </Button>
            }
          />
        )}
        <Space wrap size={8}>
          <Button
            icon={<DownOutlined />}
            onClick={() =>
              setActiveChapterKeys(
                chapters.map((chapter) => String(chapter.chapter_number)),
              )
            }
          >
            展开全部
          </Button>
          <Button icon={<UpOutlined />} onClick={() => setActiveChapterKeys([])}>
            收起全部
          </Button>
          <Button
            icon={<DownloadOutlined />}
            disabled={!hasAnyImages}
            onClick={() =>
              downloadUrl(api.allChaptersExportUrl(story.id))
            }
          >
            导出全部章节图片
          </Button>
          <Button
            icon={<EditOutlined />}
            disabled={!hasAnyImages}
            onClick={() => {
              setAliasChapters([])
              setAliasOpen(true)
            }}
          >
            批量加别名
          </Button>
          <Button icon={<CopyOutlined />} onClick={handleCopyPlan}>
            重新规划章节
          </Button>
        </Space>
      </div>

      <div className="chapter-list">
        <Collapse
          ghost
          activeKey={activeChapterKeys}
          onChange={(keys) =>
            setActiveChapterKeys(
              (Array.isArray(keys) ? keys : [keys]).map(String),
            )
          }
          items={chapters.map((chapter) => {
            const targets = buildChapterPageTargets(
              chapter.chapter_number,
              chapters,
            )
            const chapterPages = pageByChapter.get(chapter.chapter_number)
            const missing = targets.filter(
              (target) => !chapterPages?.has(target.mappingPageNumber),
            )
            const previousIncomplete = chapters
              .filter(
                (item) => item.chapter_number < chapter.chapter_number,
              )
              .filter((item) => {
                const previousPages = pageByChapter.get(item.chapter_number)
                return item.mapping_page_numbers.some(
                  (mappingNumber) =>
                    !previousPages?.has(mappingNumber),
                )
              })
            const totalImages = targets.length + 2
            const chapterImageCount =
              (chapter.cover.image_url ? 1 : 0) +
              (chapter.guide.image_url ? 1 : 0) +
              (chapterPages
                ? [...chapterPages.values()].filter((page) => page.image_url)
                    .length
                : 0)
            const coverBusy =
              busyKey === `${chapter.chapter_number}-cover`
            const guideBusy =
              busyKey === `${chapter.chapter_number}-guide`

            return {
              key: String(chapter.chapter_number),
              className: 'chapter-card',
              label: (
                <Space wrap size={8}>
                  <Typography.Text strong>
                    第 {chapter.chapter_number} 章 · {chapter.title}
                  </Typography.Text>
                  <Tag color="blue">正文 {targets.length}/16</Tag>
                  <Tag color={totalImages <= 18 ? 'success' : 'error'}>
                    总图 {totalImages}/18
                  </Tag>
                  <Tag>封面 {chapter.cover.image_url ? '已上传' : '待上传'}</Tag>
                  <Tag>
                    引导卡 {chapter.guide.image_url ? '已上传' : '待上传'}
                  </Tag>
                </Space>
              ),
              extra: (
                <Space size={8}>
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    disabled={chapterImageCount === 0}
                    onClick={(event) => {
                      event.stopPropagation()
                      setAliasChapters([chapter.chapter_number])
                      setAliasOpen(true)
                    }}
                  >
                    本章加别名
                  </Button>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    disabled={!chapterHasImages(chapter, pages)}
                    onClick={(event) => {
                      event.stopPropagation()
                      downloadUrl(
                        api.chapterExportUrl(story.id, chapter.chapter_number),
                      )
                    }}
                  >
                    导出本章图片
                  </Button>
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    onClick={(event) => {
                      // 编辑按钮在折叠标题栏内，避免点击时顺带展开/收起
                      event.stopPropagation()
                      openEdit(chapter)
                    }}
                  >
                    编辑章节
                  </Button>
                </Space>
              ),
              children: (
                <>
                  <div className="chapter-asset-grid">
                    <div className="chapter-asset-card">
                      <div className="chapter-asset-head">
                        <Typography.Text strong>章节封面</Typography.Text>
                        <Typography.Text type="secondary">
                          不显示页码
                        </Typography.Text>
                      </div>
                      <ImageUpload
                        variant="thumb"
                        imageUrl={chapter.cover.image_url}
                        uploadText="上传封面图"
                        replaceText="替换封面"
                        maxSizeBytes={CHAPTER_IMAGE_MAX_SIZE}
                        onUpload={(file) =>
                          handleUploadChapterImage(chapter, 'cover', file)
                        }
                        onRemove={() =>
                          handleDeleteChapterImage(chapter, 'cover')
                        }
                        disabled={coverBusy}
                      />
                      <div className="chapter-text-preview">
                        <Typography.Text type="secondary">
                          {chapter.cover.label}
                        </Typography.Text>
                        <div className="chapter-cover-main">
                          {chapter.cover.narration_main}
                          {chapter.cover.narration_highlight && (
                            <Tag color="red" style={{ marginLeft: 6 }}>
                              {chapter.cover.narration_highlight}
                            </Tag>
                          )}
                        </div>
                        <Typography.Text type="secondary">
                          {chapter.cover.narration_sub}
                        </Typography.Text>
                      </div>
                      <Space wrap size={8}>
                        <Button
                          size="small"
                          icon={<CopyOutlined />}
                          disabled={!charactersReady}
                          onClick={() => handleCopyCoverInstruction(chapter)}
                        >
                          复制封面生成指令
                        </Button>
                        <Tooltip
                          title={
                            imageEnabled
                              ? undefined
                              : '请先在「设置」页配置生图服务'
                          }
                        >
                          <Button
                            size="small"
                            icon={<PictureOutlined />}
                            disabled={
                              !imageEnabled ||
                              !chapter.cover.image_prompt.trim()
                            }
                            onClick={() => confirmGenerateCover(chapter)}
                          >
                            立即生图
                          </Button>
                        </Tooltip>
                        <Button
                          size="small"
                          icon={<HistoryOutlined />}
                          onClick={() => openGenerationHistory(chapter)}
                        >
                          历史
                        </Button>
                        <Button
                          size="small"
                          icon={<HistoryOutlined />}
                          onClick={() => setPromptHistoryChapter(chapter)}
                        >
                          提示词历史
                        </Button>
                        <Button
                          size="small"
                          icon={<HistoryOutlined />}
                          onClick={() =>
                            setAssetHistory({ chapter, kind: 'cover' })
                          }
                        >
                          成品图历史
                        </Button>
                        <Button
                          size="small"
                          disabled={!chapter.cover.image_prompt.trim()}
                          onClick={() =>
                            void copy(
                              chapter.cover.image_prompt,
                              '封面提示词已复制',
                            )
                          }
                        >
                          复制封面提示词
                        </Button>
                        <Button
                          size="small"
                          icon={<CloudUploadOutlined />}
                          onClick={() =>
                            handleCopyAssetIngest(chapter, 'cover')
                          }
                        >
                          复制回传指令
                        </Button>
                      </Space>
                      {chapter.cover.image_prompt && (
                        <Typography.Paragraph
                          type="secondary"
                          className="chapter-prompt-preview"
                          ellipsis={{
                            rows: 3,
                            expandable: true,
                            symbol: '展开',
                          }}
                        >
                          {chapter.cover.image_prompt}
                        </Typography.Paragraph>
                      )}
                    </div>

                    <div className="chapter-asset-card">
                      <div className="chapter-asset-head">
                        <Typography.Text strong>章节引导卡</Typography.Text>
                        <Typography.Text type="secondary">
                          不显示页码
                        </Typography.Text>
                      </div>
                      <ImageUpload
                        variant="thumb"
                        imageUrl={chapter.guide.image_url}
                        uploadText="上传引导卡图"
                        replaceText="替换引导卡"
                        maxSizeBytes={CHAPTER_IMAGE_MAX_SIZE}
                        onUpload={(file) =>
                          handleUploadChapterImage(chapter, 'guide', file)
                        }
                        onRemove={() =>
                          handleDeleteChapterImage(chapter, 'guide')
                        }
                        disabled={guideBusy}
                      />
                      <div className="chapter-text-preview">
                        <div className="chapter-cover-main">
                          {chapter.guide.text}
                        </div>
                        <Typography.Text type="secondary">
                          {chapter.guide.sub_text}
                        </Typography.Text>
                      </div>
                      <Space wrap size={8}>
                        <Button
                          size="small"
                          icon={<CopyOutlined />}
                          disabled={!charactersReady}
                          onClick={() => handleCopyGuideInstruction(chapter)}
                        >
                          复制引导卡生成指令
                        </Button>
                        <Button
                          size="small"
                          disabled={!chapter.guide.image_prompt.trim()}
                          onClick={() =>
                            void copy(
                              chapter.guide.image_prompt,
                              '引导卡提示词已复制',
                            )
                          }
                        >
                          复制引导卡提示词
                        </Button>
                        <Button
                          size="small"
                          icon={<CloudUploadOutlined />}
                          onClick={() =>
                            handleCopyAssetIngest(chapter, 'guide')
                          }
                        >
                          复制回传指令
                        </Button>
                        <Button
                          size="small"
                          icon={<HistoryOutlined />}
                          onClick={() =>
                            setAssetHistory({ chapter, kind: 'guide' })
                          }
                        >
                          成品图历史
                        </Button>
                      </Space>
                      {chapter.guide.image_prompt && (
                        <Typography.Paragraph
                          type="secondary"
                          className="chapter-prompt-preview"
                          ellipsis={{
                            rows: 3,
                            expandable: true,
                            symbol: '展开',
                          }}
                        >
                          {chapter.guide.image_prompt}
                        </Typography.Paragraph>
                      )}
                    </div>
                  </div>

                  <div className="chapter-content">
                    <div className="chapter-content-head">
                      <Typography.Text strong>
                        正文 {targets.length} 页
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        已生成 {targets.length - missing.length} 页
                        {missing.length > 0
                          ? ` · 待生成 ${missing.length} 页`
                          : ' · 已完整'}
                      </Typography.Text>
                    </div>
                    <Typography.Text type="secondary">
                      发布顺序：封面 → 第1…
                      {targets.length}页正文 → 引导卡（共 {totalImages} 张）
                    </Typography.Text>
                    {previousIncomplete.length > 0 && (
                      <Typography.Text type="warning">
                        请先生成第{' '}
                        {previousIncomplete
                          .map((item) => item.chapter_number)
                          .join('、')}{' '}
                        章正文，再生成本章；否则全局页码会出现空号。
                      </Typography.Text>
                    )}
                    <div className="chapter-page-list">
                      {targets.map((target) => {
                        const page = chapterPages?.get(target.mappingPageNumber)
                        return (
                          <Tag
                            key={target.mappingPageNumber}
                            color={page ? 'success' : 'default'}
                          >
                            第{target.chapterPageNumber}页 · 对照第
                            {target.mappingPageNumber}段
                            {page ? ' ✓' : ' · 待生成'}
                          </Tag>
                        )
                      })}
                    </div>
                    <Space wrap size={8}>
                      <Button
                        type="primary"
                        icon={<CopyOutlined />}
                        disabled={
                          mappingDraft ||
                          !charactersReady ||
                          missing.length === 0 ||
                          previousIncomplete.length > 0
                        }
                        onClick={() =>
                          handleCopyChapterScript(chapter, false)
                        }
                      >
                        复制本章脚本指令（补 {missing.length} 页）
                      </Button>
                      <Button
                        danger
                        icon={<ReloadOutlined />}
                        disabled={
                          mappingDraft ||
                          !charactersReady ||
                          previousIncomplete.length > 0
                        }
                        onClick={() => handleCopyChapterScript(chapter, true)}
                      >
                        重新生成本章全部正文
                      </Button>
                      <Button
                        icon={<EditOutlined />}
                        disabled={chapterImageCount === 0}
                        onClick={() => {
                          setAliasChapters([chapter.chapter_number])
                          setAliasOpen(true)
                        }}
                      >
                        本章加别名（{chapterImageCount} 张）
                      </Button>
                    </Space>
                  </div>
                </>
              ),
            }
          })}
        />
      </div>

      <Modal
        title={
          editing
            ? `编辑第 ${editing.chapter_number} 章`
            : '编辑章节'
        }
        open={editOpen}
        onCancel={() => {
          setCoverOptimizerOpen(false)
          setEditOpen(false)
        }}
        onOk={() => void saveChapter()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={760}
        destroyOnHidden
        afterOpenChange={(open) => {
          // 打开动画结束后 Form 必定已挂载，再回填一次，兜住挂载时序差异
          if (open && editing) {
            form.setFieldsValue(chapterEditValues(editing))
          }
        }}
      >
        <Form
          form={form}
          layout="vertical"
          preserve={false}
          initialValues={editInitialValues}
        >
          <Form.Item
            name="title"
            label="章节标题"
            rules={[{ required: true, message: '请填写章节标题' }]}
          >
            <Input maxLength={50} showCount />
          </Form.Item>

          <Typography.Title level={5}>封面文字</Typography.Title>
          <Space wrap style={{ marginBottom: 8 }}>
            <Button
              icon={<ThunderboltOutlined />}
              onClick={openCoverCopyOptions}
            >
              AI 生成封面文案（3 选 1）
            </Button>
            <Typography.Text type="secondary">
              从本章最强钩子生成主标题/副标题，选定后回填；保存后再复制封面生成指令。
            </Typography.Text>
          </Space>
          <Form.Item name="cover_label" label="顶部小字">
            <Input maxLength={100} placeholder="第1章 · 如果一切能重来" />
          </Form.Item>
          <Form.Item
            name="cover_main"
            label="主旁白"
            rules={[{ required: true, message: '请填写主旁白' }]}
          >
            <Input maxLength={200} placeholder="这一次，她只想回家" />
          </Form.Item>
          <Form.Item name="cover_highlight" label="标红关键词">
            <Input maxLength={100} placeholder="回家" />
          </Form.Item>
          <Form.Item
            name="cover_sub"
            label="副旁白 / 前情提要"
            rules={[{ required: true, message: '请填写副旁白' }]}
          >
            <Input.TextArea rows={2} maxLength={4000} showCount />
          </Form.Item>
          <Form.Item
            name="cover_prompt"
            label={
              <Space size={8}>
                <span>封面生图提示词</span>
                <Button
                  size="small"
                  type="link"
                  icon={<ThunderboltOutlined />}
                  onClick={openCoverOptimizer}
                >
                  AI 优化画面提示词
                </Button>
              </Space>
            }
            extra="提示词为空也可以直接生成新版；AI 只优化主标题、副标题和画面提示词，顶部小字与标红词不变。结果回填后仍需点击「保存」。"
          >
            <Input.TextArea rows={5} maxLength={8000} showCount />
          </Form.Item>

          <Typography.Title level={5}>引导卡文字</Typography.Title>
          <Form.Item
            name="guide_text"
            label="主文案"
            rules={[{ required: true, message: '请填写主文案' }]}
          >
            <Input maxLength={100} showCount />
          </Form.Item>
          <Form.Item
            name="guide_sub"
            label="副文案"
            rules={[{ required: true, message: '请填写副文案' }]}
          >
            <Input maxLength={200} showCount />
          </Form.Item>
          <Form.Item name="guide_prompt" label="引导卡生图提示词">
            <Input.TextArea rows={5} maxLength={8000} showCount />
          </Form.Item>
        </Form>
      </Modal>

      <ChapterCoverOptimizerModal
        open={coverOptimizerOpen}
        storyId={story.id}
        chapterNumber={editing?.chapter_number ?? 0}
        chapterTitle={
          coverOptimizerValues?.chapterTitle ?? editing?.title ?? ''
        }
        coverLabel={coverOptimizerValues?.coverLabel ?? ''}
        coverMain={coverOptimizerValues?.coverMain ?? ''}
        coverSub={coverOptimizerValues?.coverSub ?? ''}
        coverHighlight={coverOptimizerValues?.coverHighlight ?? ''}
        imagePrompt={coverOptimizerValues?.imagePrompt ?? ''}
        onClose={() => setCoverOptimizerOpen(false)}
        onApply={(values) => {
          form.setFieldsValue({
            cover_main: values.narration_main,
            cover_sub: values.narration_sub,
            cover_prompt: values.image_prompt,
          })
        }}
      />

      <CoverCopyOptionsModal
        open={coverCopyOpen}
        storyId={story.id}
        chapterNumber={editing?.chapter_number ?? 0}
        chapterTitle={
          coverCopyValues?.chapterTitle ?? editing?.title ?? ''
        }
        coverLabel={coverCopyValues?.coverLabel ?? ''}
        coverMain={coverCopyValues?.coverMain ?? ''}
        coverHighlight={coverCopyValues?.coverHighlight ?? ''}
        coverSub={coverCopyValues?.coverSub ?? ''}
        onClose={() => setCoverCopyOpen(false)}
        onApply={(option) => {
          form.setFieldsValue({
            cover_main: option.narration_main,
            cover_highlight: option.narration_highlight,
            cover_sub: option.narration_sub,
            cover_prompt: option.image_prompt,
          })
        }}
      />

      <ImageGenerationModal
        open={generationOpen}
        title={
          generationChapter
            ? `章节封面 · 第${generationChapter.chapter_number}章 ${generationChapter.title}`
            : '章节封面'
        }
        loading={generationLoading}
        preview={generationPreview}
        history={generationHistory}
        historyBytes={generationBytes}
        using={generationUsing}
        onUse={handleUseGeneration}
        onRegenerate={() => {
          if (generationChapter) void startGeneration(generationChapter)
        }}
        onClose={() => {
          setGenerationOpen(false)
          setGenerationChapter(null)
          setGenerationPreview(null)
        }}
        onClearHistory={handleClearGenerationHistory}
      />

      <AliasStampModal
        open={aliasOpen}
        storyId={story.id}
        defaultAlias={story.zhihu_alias}
        chapterOptions={aliasChapterOptions}
        defaultChapterNumbers={aliasChapters}
        imageCount={aliasImageCount}
        onClose={() => {
          setAliasOpen(false)
          setAliasChapters([])
        }}
        onDone={onRefresh}
      />
      <ChapterAssetHistoryDrawer
        open={Boolean(assetHistory)}
        storyId={story.id}
        chapterNumber={assetHistory?.chapter.chapter_number ?? 0}
        kind={assetHistory?.kind ?? 'cover'}
        onClose={() => setAssetHistory(null)}
        onRestored={() => void onRefresh()}
      />
      <PromptSnapshotDrawer
        open={Boolean(promptHistoryChapter)}
        storyId={story.id}
        targetType="cover"
        chapterNumber={promptHistoryChapter?.chapter_number}
        onClose={() => setPromptHistoryChapter(null)}
        onRestored={() => void onRefresh()}
      />

    </div>
  )
}
