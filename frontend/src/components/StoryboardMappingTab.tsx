import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Empty,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { AuditOutlined, CopyOutlined, ReadOutlined } from '@ant-design/icons'
import MappingArticleView from './MappingArticleView'
import MappingReviewPanel from './MappingReviewPanel'
import { api, ApiError } from '../api/client'
import { copyText } from '../utils/clipboard'
import {
  buildOptimizeArticlePrompt,
  buildScriptPagePlan,
} from '../utils/storyBreakdown'
import type {
  MappingReview,
  StoryBreakdown,
  StoryboardChapterRead,
  StoryboardMappingItem,
} from '../types'

interface StoryboardMappingTabProps {
  breakdown: StoryBreakdown | null
  /** 已勾选要生成脚本的页码 */
  selectedPages: number[]
  onSelectedPagesChange: (pages: number[]) => void
  /** 审阅应用后把新 breakdown 回传给详情页 */
  onBreakdownUpdated?: (breakdown: StoryBreakdown) => void
}

/** 表格列：章节模式下展示章节 / 章内页，未分章时展示脚本页规划。 */
function buildColumns(
  existingPageByMapping: Map<number, number>,
  targetPageByMapping: Map<number, number>,
  chapters: StoryboardChapterRead[],
): ColumnsType<StoryboardMappingItem> {
  const chapterByMapping = new Map<
    number,
    { chapterNumber: number; chapterPageNumber: number }
  >()
  for (const chapter of chapters) {
    chapter.mapping_page_numbers.forEach((mappingNumber, index) => {
      chapterByMapping.set(mappingNumber, {
        chapterNumber: chapter.chapter_number,
        chapterPageNumber: index + 1,
      })
    })
  }

  const chapterColumn: ColumnsType<StoryboardMappingItem>[number] = {
    title: '章节',
    key: 'chapter',
    width: 150,
    render: (_, item) => {
      if (item.excluded) {
        return <Tag>已弃用</Tag>
      }
      const info = chapterByMapping.get(item.page_number)
      if (info) {
        return (
          <Tag color="blue">
            第{info.chapterNumber}章 · 第{info.chapterPageNumber}页
          </Tag>
        )
      }
      return <Tag color="orange">未分章</Tag>
    },
  }

  const scriptPageColumn: ColumnsType<StoryboardMappingItem>[number] = {
    title: '脚本页',
    key: 'script_page',
    width: 110,
    render: (_, item) => {
      const target = targetPageByMapping.get(item.page_number)
      if (target !== undefined) {
        return <Tag color="geekblue">第{target}页</Tag>
      }
      const existing = existingPageByMapping.get(item.page_number)
      if (existing !== undefined) {
        return (
          <Typography.Text type="secondary">
            第{existing}页（保留）
          </Typography.Text>
        )
      }
      return <Typography.Text type="secondary">—</Typography.Text>
    },
  }

  return [
    {
      title: '对照段',
      dataIndex: 'page_number',
      width: 90,
      render: (pageNumber: number, item) => (
        <Tag color={item.excluded ? 'default' : 'blue'}>
          第{pageNumber}段
        </Tag>
      ),
    },
    ...(chapters.length > 0 ? [chapterColumn] : [scriptPageColumn]),
    {
      title: '原文位置',
      key: 'position',
      width: 150,
      render: (_, item) => {
        const position = [item.paragraph, item.part]
          .filter(Boolean)
          .join(' · ')
        return position ? (
          <Typography.Text type="secondary">{position}</Typography.Text>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        )
      },
    },
    {
      title: '原文摘录',
      dataIndex: 'source_text',
      render: (text: string) => (
        <Typography.Paragraph
          className="mapping-source-text"
          style={{ marginBottom: 0 }}
        >
          {text}
        </Typography.Paragraph>
      ),
    },
    {
      title: '本段简述',
      dataIndex: 'summary',
      width: 240,
      render: (summary: string) =>
        summary ? (
          <Typography.Text>{summary}</Typography.Text>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
  ]
}

/**
 * 分镜对照表：第一步产物，只读。
 *
 * 页码 → 优化文原文摘录，按文章顺序排列；确认顺序后再生成分镜头脚本。
 * 另提供「查看优化文对照」弹窗：把优化文连续展示，并在每段前标出对应页码。
 */
export default function StoryboardMappingTab({
  breakdown,
  selectedPages,
  onSelectedPagesChange,
  onBreakdownUpdated,
}: StoryboardMappingTabProps) {
  const { message } = App.useApp()
  const [articleOpen, setArticleOpen] = useState(false)
  const [requirement, setRequirement] = useState('')
  const [review, setReview] = useState<MappingReview | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const mapping = breakdown?.mapping ?? []
  const chapters = breakdown?.chapters ?? []
  const storyId = breakdown?.story_id

  useEffect(() => {
    if (!storyId) {
      setReview(null)
      return
    }
    let cancelled = false
    api
      .getMappingReview(storyId)
      .then((data) => {
        if (!cancelled) {
          setReview(data.status === 'draft' ? data : null)
        }
      })
      .catch((error) => {
        if (
          !cancelled &&
          !(error instanceof ApiError && error.status === 404)
        ) {
          // 审阅接口失败不影响只读对照表展示，静默忽略
          setReview(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [storyId, breakdown?.updated_at])
  const isChaptered = chapters.length > 0
  const excludedCount = mapping.filter((item) => item.excluded).length
  const scriptPlan = useMemo(
    () =>
      buildScriptPagePlan(
        selectedPages,
        breakdown?.pages ?? [],
        mapping.map((item) => item.page_number),
      ),
    [selectedPages, breakdown?.pages, mapping],
  )
  const existingPageByMapping = useMemo(() => {
    const result = new Map<number, number>()
    for (const page of breakdown?.pages ?? []) {
      if (page.mapping_page_number != null) {
        result.set(page.mapping_page_number, page.page_number)
      }
    }
    return result
  }, [breakdown?.pages])
  const targetPageByMapping = useMemo(
    () =>
      new Map(
        scriptPlan.targets.map((target) => [
          target.mappingPageNumber,
          target.scriptPageNumber,
        ]),
      ),
    [scriptPlan.targets],
  )
  const columns = useMemo(
    () =>
      buildColumns(existingPageByMapping, targetPageByMapping, chapters),
    [existingPageByMapping, targetPageByMapping, chapters],
  )
  const targetPageNumbers = scriptPlan.targets.map(
    (target) => target.scriptPageNumber,
  )
  const targetPagesAreContinuous = targetPageNumbers.every(
    (pageNumber, index) => pageNumber === index + 1,
  )
  const planHint =
    scriptPlan.mode === 'new'
      ? `将生成脚本第 1–${scriptPlan.targets.length} 页`
      : scriptPlan.mode === 'regenerate'
        ? `将重新生成脚本第 ${
            targetPagesAreContinuous
              ? `1–${targetPageNumbers.length}`
              : targetPageNumbers.join('、')
          } 页`
        : null

  const togglePage = (pageNumber: number) => {
    const item = mapping.find((entry) => entry.page_number === pageNumber)
    if (!item || item.excluded) return
    const next = selectedPages.includes(pageNumber)
      ? selectedPages.filter((value) => value !== pageNumber)
      : [...selectedPages, pageNumber].sort((left, right) => left - right)
    onSelectedPagesChange(next)
  }

  const handleCopyOptimize = async () => {
    const value = requirement.trim()
    if (!value) {
      message.warning('请先输入优化要求')
      return
    }
    if (!breakdown) return
    try {
      await copyText(buildOptimizeArticlePrompt(breakdown.story_id, value))
      message.success(
        '优化指令已复制，粘贴到 Claude Code 中运行；完成后刷新查看新对照表',
      )
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  if (mapping.length === 0) {
    return (
      <Empty description="还没有分镜对照表">
        <Typography.Text type="secondary">
          点击右上角「复制分镜对照指令」，粘贴到本项目的 Claude Code 中运行；
          它会先按优化文顺序拆出「页码 → 原文段落」的对照表并写回这里，
          不会直接生成分镜脚本。
        </Typography.Text>
      </Empty>
    )
  }

  return (
    <div className="mapping-body">
      <div className="mapping-toolbar">
        {isChaptered ? (
          <Alert
            type="info"
            showIcon
            message={`对照表共 ${mapping.length} 段 · 已分 ${chapters.length} 章${
              excludedCount > 0 ? ` · 已弃用 ${excludedCount} 段` : ''
            }`}
            description="正文脚本请到「章节发布」按章生成；已弃用段不会分入章节，也不会生成脚本。"
          />
        ) : (
          <Alert
            type={scriptPlan.mode === 'blocked' ? 'warning' : 'info'}
            showIcon
            message={`对照表共 ${mapping.length} 段${
              excludedCount > 0 ? `（已弃用 ${excludedCount} 段）` : ''
            } · 已选 ${selectedPages.length} 段${
              planHint ? ` · ${planHint}` : ''
            }`}
            description={
              scriptPlan.mode === 'blocked'
                ? scriptPlan.reason ?? ''
                : '脚本页码按选中顺序连续编号，未选段不占号；已有脚本时只覆盖来源对应的脚本页。要新增或删除段落，请先清空分镜脚本再重新生成。'
            }
          />
        )}
        <Space wrap size={8}>
          {!isChaptered && (
            <>
              <Button
                size="small"
                onClick={() => {
                  const activeMapping = mapping.filter(
                    (item) => !item.excluded,
                  )
                  const mappingNumbers = new Set(
                    activeMapping.map((item) => item.page_number),
                  )
                  const existingSources = (breakdown?.pages ?? [])
                    .map((page) => page.mapping_page_number)
                    .filter(
                      (pageNumber): pageNumber is number =>
                        pageNumber != null && mappingNumbers.has(pageNumber),
                    )
                  onSelectedPagesChange(
                    existingSources.length > 0
                      ? Array.from(new Set(existingSources)).sort(
                          (left, right) => left - right,
                        )
                      : activeMapping.map((item) => item.page_number),
                  )
                }}
              >
                {breakdown?.pages.length ? '选中现有脚本' : '全选'}
              </Button>
              <Button
                size="small"
                onClick={() => onSelectedPagesChange([])}
              >
                清空
              </Button>
            </>
          )}
          <Button
            icon={<AuditOutlined />}
            onClick={() => setReviewOpen(true)}
          >
            审阅对照
            {review?.summary.pending_count
              ? `（${review.summary.pending_count}）`
              : ''}
          </Button>
          <Button
            icon={<ReadOutlined />}
            onClick={() => setArticleOpen(true)}
          >
            查看优化文对照
          </Button>
        </Space>
      </div>

      <Table<StoryboardMappingItem>
        className="mapping-table"
        rowKey="page_number"
        size="small"
        columns={columns}
        dataSource={mapping}
        pagination={false}
        scroll={{ y: 560 }}
        rowSelection={
          isChaptered
            ? undefined
            : {
                selectedRowKeys: selectedPages,
                preserveSelectedRowKeys: true,
                getCheckboxProps: (record) => ({
                  disabled: record.excluded,
                }),
                onChange: (keys) =>
                  onSelectedPagesChange(
                    keys
                      .map(Number)
                      .sort((left, right) => left - right),
                  ),
              }
        }
        onRow={
          isChaptered
            ? undefined
            : (record) => ({
                style: { cursor: 'pointer' },
                onClick: (event) => {
                  // 勾选列自己会切换，避免点复选框时被行点击再切一次
                  const target = event.target as HTMLElement
                  if (target.closest('.ant-table-selection-column')) return
                  if (record.excluded) return
                  togglePage(record.page_number)
                },
              })
        }
      />

      {breakdown ? (
        <MappingReviewPanel
          storyId={breakdown.story_id}
          open={reviewOpen}
          breakdown={breakdown}
          onClose={() => setReviewOpen(false)}
          onApplied={(result) => {
            onBreakdownUpdated?.(result.breakdown)
            setReviewOpen(false)
          }}
          onReviewUpdated={setReview}
        />
      ) : null}

      <Modal
        title="优化文 · 分镜对照"
        open={articleOpen}
        onCancel={() => setArticleOpen(false)}
        footer={null}
        width={980}
        destroyOnHidden
      >
        <Typography.Text type="secondary">
          蓝色数字是对照段号；悬浮可看本段简述。
          {isChaptered
            ? '标有「已弃用」的段落不会分入章节，也不会生成脚本。'
            : '灰色段落为未勾选，不会生成脚本。'}
          文本按优化文顺序连续展示，标点和换行保持原样。
        </Typography.Text>

        <div className="article-optimize-panel">
          <div className="article-optimize-title">
            <Typography.Text strong>AI 优化</Typography.Text>
            <Typography.Text type="secondary">
              写清要改什么；复制后到 Claude Code 运行，会同时重写优化文和对照表。
            </Typography.Text>
          </div>
          <Input.TextArea
            rows={3}
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            placeholder="例如：开头更抓人；压缩到 1500 字；加强奶奶这条线；减少书面语…"
            maxLength={1000}
            showCount
          />
          <Space wrap size={10}>
            <Button
              type="primary"
              icon={<CopyOutlined />}
              disabled={!requirement.trim()}
              onClick={() => void handleCopyOptimize()}
            >
              复制优化指令
            </Button>
            <Typography.Text type="secondary">
              只改优化文和对照表；章节/分镜页需要你确认后重新规划或重生成
            </Typography.Text>
          </Space>
        </div>

        <MappingArticleView
          mapping={mapping}
          selectedPages={isChaptered ? undefined : selectedPages}
        />
      </Modal>
    </div>
  )
}
