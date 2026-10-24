import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Form,
  Input,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  CopyOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, getErrorMessage } from '../api/client'
import { copyText } from '../utils/clipboard'
import CopyOptionsModal from './CopyOptionsModal'
import type {
  GeneratedCopyOption,
  Story,
  StoryBreakdown,
  StoryChapterPostConfig,
  StoryPostConfig,
} from '../types'

interface PostConfigTabProps {
  story: Story
  breakdown: StoryBreakdown | null
  postConfig: StoryPostConfig | null
  keyConfigured: boolean
  onSaved: (config: StoryPostConfig) => void
}

interface PostConfigFormValues {
  title: string
  content: string
}

const LEADING_ALIAS_PATTERN = /^\s*【[^】]{1,20}】\s*/

/** 与后端一致：去掉旧别名行，再把当前别名放到正文第一行。 */
function applyAliasPrefix(content: string, alias: string): string {
  if (!content.trim()) return content
  const body = content.replace(LEADING_ALIAS_PATTERN, '').trim()
  if (!body) return alias ? `【${alias}】` : ''
  return alias ? `【${alias}】\n${body}` : body
}

/**
 * 发文配置 tab。
 *
 * 没有章节的老故事仍是一份整篇配置；有章节时按章保存，一章一份文案。
 * 第 2 章起的 AI 文案会自动加入前情提要，最后一章结尾引导主页简介。
 */
export default function PostConfigTab({
  story,
  breakdown,
  postConfig,
  keyConfigured,
  onSaved,
}: PostConfigTabProps) {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<PostConfigFormValues>()
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [dirty, setDirty] = useState(false)
  // AI 一次生成多份方案，先在弹窗里对比，再由用户选用其中一份
  const [copyOptions, setCopyOptions] = useState<GeneratedCopyOption[]>([])
  const [optionsOpen, setOptionsOpen] = useState(false)

  const chapters = useMemo(
    () =>
      [...(breakdown?.chapters ?? [])].sort(
        (left, right) => left.chapter_number - right.chapter_number,
      ),
    [breakdown?.chapters],
  )
  const hasChapters = chapters.length > 0
  const chapterKey = chapters
    .map((chapter) => `${chapter.chapter_number}:${chapter.title}`)
    .join(',')
  const [chapterNumber, setChapterNumber] = useState<number | null>(null)
  const [chapterConfig, setChapterConfig] =
    useState<StoryChapterPostConfig | null>(null)
  const [chapterLoading, setChapterLoading] = useState(false)

  const currentChapter = chapters.find(
    (chapter) => chapter.chapter_number === chapterNumber,
  )
  const isLastChapter =
    currentChapter != null &&
    chapters.length > 0 &&
    currentChapter.chapter_number ===
      chapters[chapters.length - 1].chapter_number
  const activeConfig = hasChapters ? chapterConfig : postConfig

  // 有章节时默认选中第一章；章节列表变化时保留仍然存在的选中项
  useEffect(() => {
    if (!hasChapters) {
      setChapterNumber(null)
      return
    }
    setChapterNumber((previous) =>
      previous != null &&
      chapters.some((chapter) => chapter.chapter_number === previous)
        ? previous
        : chapters[0].chapter_number,
    )
  }, [chapterKey, hasChapters, chapters])

  // 切换章节：读取该章已保存的文案
  useEffect(() => {
    if (!hasChapters || chapterNumber == null) return
    let cancelled = false
    setChapterLoading(true)
    api
      .getChapterPostConfig(story.id, chapterNumber)
      .then((config) => {
        if (cancelled) return
        setChapterConfig(config)
        form.resetFields()
        form.setFieldsValue({
          title: config?.title ?? '',
          content: config?.content ?? '',
        })
        setDirty(false)
      })
      .catch((error) => {
        if (cancelled) return
        message.error(getErrorMessage(error))
      })
      .finally(() => {
        if (!cancelled) setChapterLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [story.id, chapterNumber, hasChapters, form, message])

  // 没有章节时沿用旧版整篇配置
  useEffect(() => {
    if (hasChapters) return
    form.setFieldsValue({
      title: postConfig?.title ?? '',
      content: postConfig?.content ?? '',
    })
    setDirty(false)
  }, [postConfig, form, hasChapters])

  // 别名在顶部卡片被修改后，当前表单里的开头立即跟着换，不需要等重新加载
  useEffect(() => {
    const content = form.getFieldValue('content') as string | undefined
    if (!content?.trim()) return
    const next = applyAliasPrefix(content, story.zhihu_alias)
    if (next !== content) {
      form.setFieldValue('content', next)
    }
  }, [story.zhihu_alias, form])

  const handleCopyContent = async () => {
    const content = (form.getFieldValue('content') ?? '') as string
    if (!content.trim()) {
      message.warning('正文还是空的')
      return
    }
    try {
      await copyText(applyAliasPrefix(content, story.zhihu_alias))
      message.success('完整正文已复制')
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  const handleChapterChange = (nextChapter: number) => {
    if (nextChapter === chapterNumber) return
    if (dirty) {
      modal.confirm({
        title: '切换章节？',
        content: '当前章节的文案还没有保存，切换后会丢失。',
        okText: '放弃并切换',
        cancelText: '取消',
        onOk: () => setChapterNumber(nextChapter),
      })
      return
    }
    setChapterNumber(nextChapter)
  }

  const handleSave = async () => {
    if (hasChapters && chapterNumber == null) {
      message.warning('请先选择章节')
      return
    }
    let values: PostConfigFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    setSaving(true)
    try {
      if (hasChapters && chapterNumber != null) {
        const saved = await api.saveChapterPostConfig(
          story.id,
          chapterNumber,
          {
            title: values.title ?? '',
            content: values.content ?? '',
          },
        )
        setChapterConfig(saved)
        setDirty(false)
        message.success(`第 ${chapterNumber} 章文案已保存`)
      } else {
        const saved = await api.savePostConfig(story.id, {
          title: values.title ?? '',
          content: values.content ?? '',
        })
        onSaved(saved)
        setDirty(false)
        message.success('发文配置已保存')
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleGenerate = async () => {
    if (hasChapters && chapterNumber == null) {
      message.warning('请先选择章节')
      return
    }
    setGenerating(true)
    try {
      const copy = await api.generateCopy(
        story.id,
        hasChapters && chapterNumber != null ? chapterNumber : undefined,
      )
      // 先展示方案列表，用户选定后才填入表单，且不自动保存
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

  /** 采用某个方案：只填表单，仍由用户手动点击「保存」落库。 */
  const applyOption = (options: GeneratedCopyOption[]) => {
    const option = options[0]
    if (!option) return
    form.setFieldsValue({ title: option.title, content: option.content })
    setOptionsOpen(false)
    setDirty(true)
    message.success(`已采用「${option.style}」方案，确认后请点击保存`)
  }

  const aliasPrefix = story.zhihu_alias
    ? `【${story.zhihu_alias}】`
    : ''
  const contentExtraParts: string[] = []
  if (aliasPrefix) {
    contentExtraParts.push(`保存时正文开头会自动加入 ${aliasPrefix}`)
  } else if (story.zhihu_aliases.length > 0) {
    contentExtraParts.push(
      '已有候选别名，但还没有标注最终使用；正文不会自动带【别名】',
    )
  } else {
    contentExtraParts.push('还没有设置知乎别名，正文不会自动带【别名】')
  }
  if (hasChapters) {
    contentExtraParts.push(
      currentChapter?.chapter_number === 1
        ? '第一章不会自动加前情提要'
        : '第 2 章起会自动加入 1–2 句前情提要',
    )
  }
  contentExtraParts.push('可包含 emoji 与话题标签')
  const contentExtra = `${contentExtraParts.join('；')}。`

  return (
    <div>
      {!keyConfigured && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="尚未配置 DeepSeek API Key，暂时无法使用 AI 生成文案"
          description="仍可手动填写标题与正文并保存；如需 AI 生成，请先到「设置」页配置 Key。"
          action={
            <Button size="small" onClick={() => navigate('/settings')}>
              去配置
            </Button>
          }
        />
      )}

      <div className="post-config-alias-bar">
        <Space wrap size={8}>
          <Typography.Text strong>知乎别名</Typography.Text>
          {story.zhihu_alias ? (
            <Tag color="purple">{story.zhihu_alias}</Tag>
          ) : (
            <Tag color="orange">
              {story.zhihu_aliases.length > 0 ? '待标注' : '未设置'}
            </Tag>
          )}
          <Typography.Text type="secondary">
            {story.zhihu_alias
              ? `正文开头：${aliasPrefix}`
              : story.zhihu_aliases.length > 0
                ? '已有候选别名，请到「知乎推广」tab 标注最终使用哪一个'
                : '请到「知乎推广」tab 录入，或让 AI 先生成候选'}
          </Typography.Text>
          <Button
            size="small"
            icon={<CopyOutlined />}
            onClick={() => void handleCopyContent()}
          >
            复制完整正文
          </Button>
        </Space>
      </div>

      {hasChapters && (
        <div className="post-config-chapter-bar">
          <Space wrap size={8}>
            <Typography.Text strong>章节</Typography.Text>
            <Select
              value={chapterNumber ?? undefined}
              loading={chapterLoading}
              disabled={chapterLoading}
              style={{ minWidth: 240 }}
              options={chapters.map((chapter) => ({
                value: chapter.chapter_number,
                label: `第${chapter.chapter_number}章 · ${chapter.title}`,
              }))}
              onChange={handleChapterChange}
            />
            {currentChapter && (
              <>
                <Tag color="blue">
                  正文 {currentChapter.mapping_page_numbers.length} 页
                </Tag>
                <Tag>
                  总图 {currentChapter.mapping_page_numbers.length + 2} 张
                </Tag>
              </>
            )}
          </Space>
          <Typography.Text type="secondary">
            {currentChapter?.chapter_number === 1
              ? '第一章不自动加前情提要。'
              : '本章正文会自动加入上一章的前情提要。'}
            {isLastChapter
              ? '最后一章结尾引导「主页简介」。'
              : '结尾会埋下一章钩子。'}
          </Typography.Text>
        </div>
      )}

      <Form
        form={form}
        layout="vertical"
        onValuesChange={() => setDirty(true)}
      >
        <Form.Item
          name="title"
          label="小红书标题（18 字以内）"
          rules={[{ max: 18, message: '标题不能超过 18 字' }]}
          extra={
            hasChapters
              ? '围绕本章的钩子写标题，不要概括整篇故事。'
              : '用户刷到作品时，第一眼只看到标题和第 1 页封面图，正文要点进来才看得到。标题用反差、悬念、利益点或强情绪制造点击欲，不要平铺直叙地概括剧情。'
          }
        >
          <Input
            maxLength={18}
            showCount
            placeholder="例如：相亲对象开口就问我有没有A8"
          />
        </Form.Item>

        <Form.Item
          name="content"
          label="内容介绍"
          extra={contentExtra}
        >
          <Input.TextArea
            rows={12}
            maxLength={20000}
            showCount
            placeholder="正文内容..."
          />
        </Form.Item>
      </Form>

      <div className="panel-footer">
        <Typography.Text type="secondary">
          {activeConfig
            ? `最近保存：${dayjs(activeConfig.updated_at).format(
                'YYYY-MM-DD HH:mm',
              )}`
            : hasChapters
              ? `第 ${chapterNumber ?? '?'} 章尚未保存文案`
              : '尚未保存过发文配置'}
          {dirty ? ' · 有未保存修改' : ''}
        </Typography.Text>
        <Space wrap>
          <Button
            icon={<ThunderboltOutlined />}
            loading={generating}
            disabled={
              !keyConfigured ||
              (hasChapters && chapterNumber == null) ||
              chapterLoading
            }
            onClick={() => void handleGenerate()}
          >
            {hasChapters ? 'AI 生成本章文案' : 'AI 生成文案'}
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={
              chapterLoading || (hasChapters && chapterNumber == null)
            }
            onClick={() => void handleSave()}
          >
            {hasChapters ? '保存本章文案' : '保存配置'}
          </Button>
        </Space>
      </div>

      <CopyOptionsModal
        open={optionsOpen}
        options={copyOptions}
        generating={generating}
        onApply={applyOption}
        onRegenerate={() => void handleGenerate()}
        onClose={() => setOptionsOpen(false)}
      />
    </div>
  )
}
