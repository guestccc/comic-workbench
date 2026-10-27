import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, App, Button, Card, Skeleton, Tabs } from 'antd'
import {
  ArrowLeftOutlined,
  CopyOutlined,
  ReadOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate, useParams } from 'react-router-dom'
import CharacterCardsTab from '../components/CharacterCardsTab'
import PageHeader from '../components/PageHeader'
import PostConfigTab from '../components/PostConfigTab'
import StoryboardChaptersTab from '../components/StoryboardChaptersTab'
import StoryboardMappingTab from '../components/StoryboardMappingTab'
import StoryboardTab from '../components/StoryboardTab'
import ZhihuInfoCard from '../components/ZhihuInfoCard'
import { api, ApiError, getErrorMessage } from '../api/client'
import type {
  SettingsData,
  Story,
  StoryBreakdown,
  StoryPostConfig,
} from '../types'
import { copyText } from '../utils/clipboard'
import {
  buildScriptPagePlan,
  buildStoryMappingPrompt,
  buildStoryScriptPrompt,
  getBreakdownBlockedReason,
} from '../utils/storyBreakdown'

/** 故事名可留空，详情页统一显示占位文案。 */
function displayStoryName(name: string | null | undefined): string {
  return name?.trim() || '未命名故事'
}

/**
 * 故事详情页。
 *
 * 四个 tab 共用同一份故事数据：
 * - 分镜对照：第一步产物，只读的「页码 → 原文摘录」表，用来确认拆页顺序；
 * - 分镜头脚本 / 角色设定卡：第二步拆解产物，由 Claude Code 技能写回，页面可编辑；
 *   生图提示词用 {{角色名}} 变量引用角色卡，参考垫图在外部生图 AI 中绑定；
 * - 发文配置：每个故事一份的小红书标题与正文。
 */
export default function StoryDetailPage() {
  const { id } = useParams<{ id: string }>()
  const storyId = Number(id)
  const navigate = useNavigate()
  const { message } = App.useApp()

  const [story, setStory] = useState<Story | null>(null)
  const [breakdown, setBreakdown] = useState<StoryBreakdown | null>(null)
  const [postConfig, setPostConfig] = useState<StoryPostConfig | null>(null)
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  // 章节发布会成为主要工作区；首次加载时根据数据选择默认 tab
  const [activeTab, setActiveTab] = useState('mapping')
  // 分镜对照里勾选要生成脚本的对照段；已有脚本时默认选中它实际用到的段
  const [selectedMappingPages, setSelectedMappingPages] = useState<number[]>([])
  const mappingPageKey = useMemo(
    () =>
      (breakdown?.mapping ?? [])
        .filter((item) => !item.excluded)
        .map((item) => item.page_number)
        .join(','),
    [breakdown?.mapping],
  )
  // 已有脚本时，默认勾选它实际用到的对照段
  const pageSourceKey = useMemo(
    () =>
      (breakdown?.pages ?? [])
        .map((page) => page.mapping_page_number)
        .filter((pageNumber): pageNumber is number => pageNumber != null)
        .join(','),
    [breakdown?.pages],
  )
  // 选中对照段会落到哪些脚本页：空白时连续编号，已有脚本时按来源页覆盖
  const scriptPagePlan = useMemo(
    () =>
      buildScriptPagePlan(
        selectedMappingPages,
        breakdown?.pages ?? [],
        (breakdown?.mapping ?? []).map((item) => item.page_number),
      ),
    [selectedMappingPages, breakdown?.pages, breakdown?.mapping],
  )

  useEffect(() => {
    const mappingNumbers = mappingPageKey
      ? mappingPageKey.split(',').map(Number)
      : []
    const mappingSet = new Set(mappingNumbers)
    const pageSources = pageSourceKey
      ? pageSourceKey.split(',').map(Number)
      : []
    const validPageSources = pageSources.filter((pageNumber) =>
      mappingSet.has(pageNumber),
    )
    // 对照表已变化时不再默认勾选旧来源，改为全选当前对照表，
    // 让脚本计划明确提示“先清空脚本再重新生成”。
    if (
      pageSources.length > 0 &&
      validPageSources.length === pageSources.length
    ) {
      setSelectedMappingPages(validPageSources)
    } else {
      setSelectedMappingPages(mappingNumbers)
    }
    // 只在对照表变化时重置默认选段；清空 / 删除分镜页时保留当前勾选，
    // 方便用户在原有选段基础上补选第 7 段后再重新生成。
  }, [mappingPageKey])

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      // 非法的路由参数直接回列表，避免发出无意义的请求
      if (!Number.isInteger(storyId) || storyId <= 0) {
        message.error('故事 ID 无效')
        navigate('/stories', { replace: true })
        return
      }

      setLoading(true)
      try {
        // 四个请求互不依赖，并行加载；拆解与发文配置允许为空
        const [storyData, breakdownData, postConfigData, settingsData] =
          await Promise.all([
            api.getStory(storyId),
            api.getBreakdown(storyId),
            api.getPostConfig(storyId),
            api.getSettings(),
          ])
        if (cancelled) return
        setStory(storyData)
        setBreakdown(breakdownData)
        setPostConfig(postConfigData)
        setSettings(settingsData)
        if (breakdownData?.chapters?.length) {
          setActiveTab('chapters')
        } else if (breakdownData?.mapping?.length) {
          setActiveTab('mapping')
        } else {
          setActiveTab('storyboard')
        }
      } catch (error) {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 404) {
          message.error('故事不存在或已被删除')
          navigate('/stories', { replace: true })
          return
        }
        message.error(getErrorMessage(error))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [storyId, navigate, message])

  /** 分镜 / 人设编辑后只刷新拆解结果，避免整页重新加载闪屏。 */
  const refreshBreakdown = useCallback(async () => {
    try {
      const data = await api.getBreakdown(storyId)
      setBreakdown(data)
      if (data?.mapping?.length) {
        message.info(`已刷新：分镜对照表共 ${data.mapping.length} 段`)
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }, [storyId, message])

  // 复制前统一校验：原文为空、未选画风或画风失效时给出明确原因
  const handleCopyMapping = async () => {
    if (!story) return
    const blockedReason = getBreakdownBlockedReason(story)
    if (blockedReason) {
      message.warning(blockedReason)
      return
    }
    try {
      await copyText(buildStoryMappingPrompt(story.id))
      message.success('分镜对照指令已复制，Claude 会先按优化文顺序写回对照表，不会直接生成脚本')
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  const handleCopyScript = async () => {
    if (!story) return
    if (!breakdown?.mapping?.length) {
      message.warning('还没有分镜对照表，请先复制并运行「分镜对照指令」')
      return
    }
    if (selectedMappingPages.length === 0) {
      message.warning('请先在「分镜对照」里勾选至少一段')
      return
    }
    if (scriptPagePlan.mode === 'blocked') {
      message.warning(scriptPagePlan.reason ?? '当前选段无法生成脚本')
      return
    }
    try {
      await copyText(
        buildStoryScriptPrompt(
          story.id,
          selectedMappingPages,
          breakdown.pages,
        ),
      )
      const summary =
        scriptPagePlan.mode === 'new'
          ? `将生成脚本第 1–${scriptPagePlan.targets.length} 页`
          : `将重新生成脚本第 ${scriptPagePlan.targets
              .map((target) => target.scriptPageNumber)
              .join('、')} 页`
      message.success(`分镜头脚本指令已复制（${summary}）`)
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  if (loading) {
    return (
      <div>
        <PageHeader title="故事详情" />
        <Card className="panel">
          <Skeleton active paragraph={{ rows: 6 }} />
        </Card>
      </div>
    )
  }

  if (!story) {
    // 加载失败（非 404）时保留一个可返回的出口
    return (
      <div>
        <PageHeader
          title="故事详情"
          extra={
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/stories')}>
              返回列表
            </Button>
          }
        />
        <Card className="panel">
          <Alert
            type="error"
            showIcon
            message="故事加载失败"
            description="请返回列表后重试，或确认后端服务是否已启动。"
          />
        </Card>
      </div>
    )
  }

  const blockedReason = getBreakdownBlockedReason(story)
  const chapters = breakdown?.chapters ?? []
  const hasChapters = chapters.length > 0

  return (
    <div>
      <PageHeader
        title={displayStoryName(story.name)}
        description={`画风：${
          story.art_style_name ?? '未选择'
        } · 最近更新：${dayjs(story.updated_at).format('YYYY-MM-DD HH:mm')}`}
        extra={
          <div className="page-header-actions">
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/stories')}
            >
              返回列表
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => void refreshBreakdown()}
            >
              刷新
            </Button>
            <Button
              type={breakdown?.mapping?.length ? 'default' : 'primary'}
              icon={<CopyOutlined />}
              onClick={() => void handleCopyMapping()}
            >
              复制分镜对照指令
            </Button>
            {hasChapters ? (
              <Button
                type="primary"
                icon={<ReadOutlined />}
                onClick={() => setActiveTab('chapters')}
              >
                章节发布（{chapters.length}）
              </Button>
            ) : (
              <Button
                type={breakdown?.mapping?.length ? 'primary' : 'default'}
                icon={<CopyOutlined />}
                onClick={() => void handleCopyScript()}
                disabled={
                  !breakdown?.mapping?.length ||
                  selectedMappingPages.length === 0
                }
              >
                复制分镜头脚本指令
              </Button>
            )}
          </div>
        }
      />

      {/* 无法拆解时提前提示原因，避免用户复制指令后才发现缺画风 */}
      {blockedReason && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="当前无法复制拆解指令"
          description={`${blockedReason}。请回到故事列表编辑该故事后再试。`}
        />
      )}

      {breakdown?.is_content_stale && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="故事原文已修改"
          description="当前分镜基于修改前的原文生成，建议重新拆解后再用于生图。"
        />
      )}

      {breakdown?.is_art_style_stale && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="故事画风已变更或失效"
          description="已有分镜的生图提示词仍使用旧画风。建议重新拆解，或逐页调整提示词后再使用。"
        />
      )}

      {!hasChapters &&
        breakdown &&
        (breakdown.mapping?.length ?? 0) > 0 &&
        (scriptPagePlan.mode === 'blocked' ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="当前选段无法直接生成脚本"
            description={scriptPagePlan.reason}
          />
        ) : breakdown.pages.length === 0 ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={`对照表共 ${breakdown.mapping.length} 段，已选 ${selectedMappingPages.length} 段`}
            description={`生成后脚本页码为第 1–${selectedMappingPages.length} 页；未选中的段不生成，也不占号。`}
          />
        ) : selectedMappingPages.length < breakdown.pages.length ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={`当前脚本共 ${breakdown.pages.length} 页，本次选中 ${selectedMappingPages.length} 段`}
            description={`将只重新生成对应脚本页（第 ${scriptPagePlan.targets
              .map((target) => target.scriptPageNumber)
              .join('、')} 页），其余页保持不变。`}
          />
        ) : null)}

      <Card className="panel">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'mapping',
              label: breakdown?.mapping?.length
                ? `分镜对照（${breakdown.mapping.length}）`
                : '分镜对照',
              children: (
                <StoryboardMappingTab
                  breakdown={breakdown}
                  selectedPages={selectedMappingPages}
                  onSelectedPagesChange={setSelectedMappingPages}
                  onBreakdownUpdated={(next) => {
                    setBreakdown(next)
                    setSelectedMappingPages([])
                  }}
                />
              ),
            },
            {
              key: 'chapters',
              label: hasChapters
                ? `章节发布（${chapters.length}）`
                : '章节发布',
              children: (
                <StoryboardChaptersTab
                  story={story}
                  breakdown={breakdown}
                  onRefresh={refreshBreakdown}
                />
              ),
            },
            {
              key: 'storyboard',
              label: '分镜头脚本',
              children: (
                <StoryboardTab
                  story={story}
                  breakdown={breakdown}
                  aiEnabled={settings?.deepseek.configured ?? false}
                  onRefresh={refreshBreakdown}
                />
              ),
            },
            {
              key: 'characters',
              label: '角色设定卡',
              children: (
                <CharacterCardsTab
                  breakdown={breakdown}
                  aiEnabled={settings?.deepseek.configured ?? false}
                  prefixPrompt={settings?.image_prefix_prompt ?? ''}
                  artStyleName={story.art_style_name}
                  onPrefixSaved={setSettings}
                  onRefresh={refreshBreakdown}
                />
              ),
            },
            {
              key: 'zhihu',
              label: story.zhihu_alias
                ? `知乎推广（${story.zhihu_alias}）`
                : story.zhihu_aliases.length > 0
                  ? '知乎推广（待标注）'
                  : '知乎推广',
              children: (
                <ZhihuInfoCard story={story} onUpdated={setStory} />
              ),
            },
            {
              key: 'post-config',
              label: '发文配置',
              children: (
                <PostConfigTab
                  story={story}
                  breakdown={breakdown}
                  postConfig={postConfig}
                  keyConfigured={settings?.deepseek.configured ?? false}
                  onSaved={setPostConfig}
                />
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
