import { useCallback, useEffect, useState } from 'react'
import { Alert, App, Button, Card, Skeleton, Tabs } from 'antd'
import { ArrowLeftOutlined, CopyOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate, useParams } from 'react-router-dom'
import CharacterCardsTab from '../components/CharacterCardsTab'
import PageHeader from '../components/PageHeader'
import PostConfigTab from '../components/PostConfigTab'
import StoryboardTab from '../components/StoryboardTab'
import { api, ApiError, getErrorMessage } from '../api/client'
import type {
  SettingsData,
  Story,
  StoryBreakdown,
  StoryPostConfig,
} from '../types'
import { copyText } from '../utils/clipboard'
import {
  buildStoryBreakdownPrompt,
  getBreakdownBlockedReason,
} from '../utils/storyBreakdown'

/** 故事名可留空，详情页统一显示占位文案。 */
function displayStoryName(name: string | null | undefined): string {
  return name?.trim() || '未命名故事'
}

/**
 * 故事详情页。
 *
 * 三个 tab 共用同一份故事数据：
 * - 分镜头脚本 / 角色设定卡：拆解产物，由 Claude Code 技能一次性写回，页面可编辑；
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
      setBreakdown(await api.getBreakdown(storyId))
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }, [storyId, message])

  // 复制前统一校验：原文为空、未选画风或画风失效时给出明确原因
  const handleCopyBreakdown = async () => {
    if (!story) return
    const blockedReason = getBreakdownBlockedReason(story)
    if (blockedReason) {
      message.warning(blockedReason)
      return
    }
    try {
      await copyText(buildStoryBreakdownPrompt(story.id))
      message.success('拆解指令已复制，粘贴到 Claude Code 后会一次性生成角色卡与全部分镜并写回本页')
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
              type="primary"
              icon={<CopyOutlined />}
              onClick={() => void handleCopyBreakdown()}
            >
              复制拆解指令
            </Button>
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

      <Card className="panel">
        <Tabs
          defaultActiveKey="storyboard"
          items={[
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
                  onRefresh={refreshBreakdown}
                />
              ),
            },
            {
              key: 'post-config',
              label: '发文配置',
              children: (
                <PostConfigTab
                  story={story}
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
