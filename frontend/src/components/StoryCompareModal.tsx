import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Empty,
  Modal,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import {
  DiffOutlined,
  OrderedListOutlined,
  ReloadOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import ReactDiffViewer, {
  DiffMethod,
  type ReactDiffViewerStylesOverride,
} from 'react-diff-viewer-continued'
import { api, getErrorMessage } from '../api/client'
import type {
  StoryboardMappingItem,
  StoryboardPage,
  StoryOptimizationAnalysis,
} from '../types'
import { alignPagesToText } from '../utils/pageAlignment'
import MappingArticleView from './MappingArticleView'

interface StoryCompareModalProps {
  open: boolean
  storyId: number
  /** 故事原文，显示在左侧 */
  original: string
  /** 优化后文章，显示在右侧 */
  optimized: string
  /** 分镜页；用于在优化文上标注每段对应的镜头 */
  pages?: StoryboardPage[]
  /** 分镜对照表；有 mapping 时优先用它标注页码 */
  mapping?: StoryboardMappingItem[]
  /** 未配置 DeepSeek Key 时禁用 AI 解读 */
  aiEnabled: boolean
  /** 原文在拆解后被修改过，对比结果可能不一致 */
  isStale: boolean
  onClose: () => void
}

/** 中文文本以字符级对比更准确；长文本由组件的 Web Worker 异步计算。 */
const DIFF_STYLES: ReactDiffViewerStylesOverride = {
  contentText: {
    fontFamily: 'Menlo, Consolas, monospace',
    fontSize: 12,
    lineHeight: 1.6,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    // 标题栏里的 <pre> 默认带 1em 边距，会把标题顶出固定高度的标题块
    margin: 0,
  },
  // 标题块默认固定 2.4em 高并裁切溢出内容，行高稍大就会把标题切掉一半
  titleBlock: {
    height: 'auto',
    minHeight: '2.4em',
    overflow: 'visible',
  },
}

/** 改动类型对应的标签颜色。 */
const KIND_COLORS: Record<string, string> = {
  钩子: 'magenta',
  悬念: 'purple',
  信息差: 'gold',
  爆点: 'red',
  节奏: 'blue',
  情绪: 'volcano',
  口语化: 'green',
  细节: 'cyan',
  删减: 'default',
  保留: 'geekblue',
}

/**
 * 原文 / 优化文对比弹窗。
 *
 * - 「逐字对比」：开源 diff 组件左右分栏，字符级高亮；
 * - 「改动解读」：调用 DeepSeek 逐条说明改了什么、为什么更能吸引读者。
 *   解读结果在弹窗关闭后仍保留，避免每次打开都重复消耗额度；
 *   优化文变化后自动失效并重新解读一次。
 */
export default function StoryCompareModal({
  open,
  storyId,
  original,
  optimized,
  pages = [],
  mapping = [],
  aiEnabled,
  isStale,
  onClose,
}: StoryCompareModalProps) {
  const [analysis, setAnalysis] = useState<StoryOptimizationAnalysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const inFlightRef = useRef(false)

  // 把优化文按分镜页切开，供「分镜对照」标签页展示
  const alignment = useMemo(
    () => alignPagesToText(optimized, pages),
    [optimized, pages],
  )

  // 优化文被重新拆解或手动编辑后，旧解读不再可信
  useEffect(() => {
    setAnalysis(null)
    setAnalysisError('')
  }, [storyId, optimized])

  /**
   * 请求改动解读。
   *
   * 普通调用会先走服务端缓存：原文与优化文不变时直接返回上次结果；
   * 只有用户主动点「重新解读」才传 force=true 重新调用模型。
   */
  const runAnalysis = useCallback(
    async (force = false) => {
      if (!aiEnabled || inFlightRef.current) return
      inFlightRef.current = true
      setAnalyzing(true)
      setAnalysisError('')
      try {
        setAnalysis(await api.analyzeBreakdown(storyId, force))
      } catch (error) {
        setAnalysisError(getErrorMessage(error))
      } finally {
        inFlightRef.current = false
        setAnalyzing(false)
      }
    },
    [aiEnabled, storyId],
  )

  // 打开弹窗且有 Key 时自动解读一次；成功后直接复用，不重复调用
  useEffect(() => {
    if (!open || !aiEnabled || analysis || analyzing || analysisError) return
    void runAnalysis()
  }, [open, aiEnabled, analysis, analyzing, analysisError, runAnalysis])

  const diffPane = (
    <Space direction="vertical" size={10} style={{ width: '100%' }}>
      {isStale && (
        <Alert
          type="warning"
          showIcon
          message="原文在拆解后被修改过，当前对比可能不一致"
          description="建议重新拆解后再对比，或直接以右侧优化文为准。"
        />
      )}
      <Typography.Text type="secondary">
        左侧为原文，右侧为优化后文章；深色块标出字符级改动。想看每段对应第几页，切到「分镜对照」。
      </Typography.Text>
      <Space size={16} wrap>
        <Typography.Text>
          原文 <Typography.Text strong>{original.length}</Typography.Text> 字
        </Typography.Text>
        <Typography.Text>
          优化后 <Typography.Text strong>{optimized.length}</Typography.Text> 字
        </Typography.Text>
      </Space>
      <div className="compare-body">
        {optimized.trim() ? (
          <ReactDiffViewer
            oldValue={original}
            newValue={optimized}
            splitView
            compareMethod={DiffMethod.CHARS}
            leftTitle="原文"
            rightTitle="优化后文章"
            showDiffOnly={false}
            hideSummary
            useDarkTheme={false}
            styles={DIFF_STYLES}
            loadingElement={() => (
              <Typography.Text type="secondary">
                正在计算差异…
              </Typography.Text>
            )}
          />
        ) : (
          <Empty description="暂无优化后文章，请先完成拆解" />
        )}
      </div>
    </Space>
  )

  const analysisPane = (
    <div className="analysis-body">
      {!aiEnabled ? (
        <Alert
          type="info"
          showIcon
          message="未配置 DeepSeek API Key"
          description="到「设置」页配置 Key 后，AI 会逐句告诉你哪里改了、为什么更吸引读者。"
        />
      ) : analyzing ? (
        <div className="analysis-loading">
          <Spin />
          <Typography.Text type="secondary">
            AI 正在对比两篇文章，找出钩子、悬念和爆点…
          </Typography.Text>
        </div>
      ) : analysisError ? (
        <Alert
          type="error"
          showIcon
          message="AI 解读失败"
          description={analysisError}
          action={
            <Button size="small" onClick={() => void runAnalysis(true)}>
              重试
            </Button>
          }
        />
      ) : analysis ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert type="info" showIcon message={analysis.summary} />
          {analysis.changes.length === 0 ? (
            <Empty description="AI 没有找到明显的改动" />
          ) : (
            analysis.changes.map((change, index) => (
              <div className="change-card" key={`${change.kind}-${index}`}>
                <Space wrap size={8}>
                  <Tag color={KIND_COLORS[change.kind] ?? 'default'}>
                    {change.kind}
                  </Tag>
                  <Typography.Text type="secondary">
                    改动 {index + 1}
                  </Typography.Text>
                </Space>
                {change.original && (
                  <Typography.Paragraph className="change-quote">
                    <Typography.Text type="secondary">原文：</Typography.Text>
                    {change.original}
                  </Typography.Paragraph>
                )}
                {change.optimized && (
                  <Typography.Paragraph className="change-quote change-quote-new">
                    <Typography.Text type="secondary">优化后：</Typography.Text>
                    {change.optimized}
                  </Typography.Paragraph>
                )}
                <Typography.Paragraph style={{ marginBottom: 0 }}>
                  {change.why}
                </Typography.Paragraph>
              </div>
            ))
          )}
          <Space wrap size={12}>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => void runAnalysis(true)}
            >
              重新解读
            </Button>
            <Typography.Text type="secondary">
              原文与优化文不变时复用上次解读；点「重新解读」才会再次调用 AI
            </Typography.Text>
          </Space>
        </Space>
      ) : null}
    </div>
  )

  const pageMapPane = (
    <div className="page-map">
      {mapping.length > 0 ? (
        <>
          <Typography.Text type="secondary">
            已使用分镜对照表：蓝色数字是对照段号，悬浮可看本段简述。
          </Typography.Text>
          <MappingArticleView mapping={mapping} />
        </>
      ) : (
        <>
          <Typography.Text type="secondary">
            按优化文原文顺序分段，块头「第X页」是对应的分镜页；同一段文字被拆到相邻页时会合并显示。
            第 1 页是钩子，综合开头信息，通常不对应单独段落。
          </Typography.Text>
          {alignment.blocks.length === 0 ? (
            <Empty description="还没有可对照的分镜页" />
          ) : (
            <div className="page-map-list">
              {alignment.blocks.map((block, index) => (
                <div
                  className="page-map-block"
                  key={`${block.pageNumbers.join('-')}-${index}`}
                >
                  <div className="page-map-header">
                    {block.pageNumbers.length > 0 ? (
                      block.pageNumbers.map((pageNumber) => (
                        <Tag color="blue" key={pageNumber}>
                          第{pageNumber}页
                        </Tag>
                      ))
                    ) : (
                      <Tag>开头</Tag>
                    )}
                    {block.pageRoles.map((role, roleIndex) => (
                      <Tag key={`${role}-${roleIndex}`}>{role}</Tag>
                    ))}
                    {block.mains[0] && (
                      <Typography.Text
                        type="secondary"
                        className="page-map-main"
                      >
                        {block.mains[0]}
                      </Typography.Text>
                    )}
                  </div>
                  <p className="page-map-text">{block.text}</p>
                </div>
              ))}
            </div>
          )}
          {alignment.unmapped.length > 0 && (
            <Alert
              type="info"
              showIcon
              message="未自动对齐的分镜页"
              description={
                <Space wrap size={4}>
                  {alignment.unmapped.map((page) => (
                    <Tag key={page.page_number}>
                      第{page.page_number}页
                      {page.page_number === 1 ? '（钩子）' : ''}
                    </Tag>
                  ))}
                  <Typography.Text type="secondary">
                    第 1 页为钩子；其余页如未对齐，请检查副旁白是否改写过多。
                  </Typography.Text>
                </Space>
              }
            />
          )}
        </>
      )}
    </div>
  )

  return (
    <Modal
      title="原文 / 优化文对比"
      open={open}
      onCancel={onClose}
      footer={null}
      width={1080}
      destroyOnHidden={false}
    >
      <Tabs
        defaultActiveKey="diff"
        items={[
          {
            key: 'diff',
            label: (
              <Space size={6}>
                <DiffOutlined />
                逐字对比
              </Space>
            ),
            children: diffPane,
          },
          {
            key: 'pages',
            label: (
              <Space size={6}>
                <OrderedListOutlined />
                分镜对照
              </Space>
            ),
            children: pageMapPane,
          },
          {
            key: 'analysis',
            label: (
              <Space size={6}>
                <RobotOutlined />
                改动解读
              </Space>
            ),
            children: analysisPane,
          },
        ]}
      />
    </Modal>
  )
}
