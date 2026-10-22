import { useState } from 'react'
import { App, Button, Card, Input, Space, Tag, Tooltip, Typography } from 'antd'
import {
  CopyOutlined,
  EditOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import PromptOptimizerDrawer from './PromptOptimizerDrawer'
import { api, getErrorMessage } from '../api/client'
import type { SettingsData } from '../types'
import { copyText } from '../utils/clipboard'
import {
  ART_STYLE_NAME_PLACEHOLDER,
  ART_STYLE_PLACEHOLDER,
  preparePromptForCopy,
} from '../utils/promptVariables'

interface PromptEditorPanelProps {
  settings: SettingsData | null
  /** 编辑器当前内容（可能尚未保存） */
  prompt: string
  loading: boolean
  onPromptChange: (value: string) => void
  onSettingsChange: (data: SettingsData) => void
}

/** 启动提示词编辑卡片：保存 / 恢复默认 / 复制（替换画风变量）/ AI 优化入口。 */
export default function PromptEditorPanel({
  settings,
  prompt,
  loading,
  onPromptChange,
  onSettingsChange,
}: PromptEditorPanelProps) {
  const { message, modal } = App.useApp()
  const [savingPrompt, setSavingPrompt] = useState(false)
  const [optimizerOpen, setOptimizerOpen] = useState(false)

  // 右侧实时预览：把画风变量替换为当前选用的画风，用户输入时立即更新。
  // {story_name} / {story_content} 依赖具体故事，仅在生成时替换，预览中保留原样。
  const preview = preparePromptForCopy(
    prompt,
    settings?.art_styles ?? [],
    settings?.active_art_style ?? null,
  )

  const handleSavePrompt = async () => {
    if (!prompt.trim()) {
      message.warning('启动提示词不能为空')
      return
    }
    setSavingPrompt(true)
    try {
      const data = await api.savePrompt(prompt)
      onSettingsChange(data)
      onPromptChange(data.prompt)
      message.success('启动提示词已保存')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSavingPrompt(false)
    }
  }

  const handleResetPrompt = () => {
    modal.confirm({
      title: '恢复默认启动提示词？',
      content: '当前保存的自定义提示词将被默认内容替换，此操作不可撤销。',
      okText: '恢复默认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const data = await api.resetPrompt()
          onSettingsChange(data)
          onPromptChange(data.prompt)
          message.success('已恢复默认提示词')
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  const handleCopyPrompt = async () => {
    if (!prompt.trim()) {
      message.warning('启动提示词为空，无法复制')
      return
    }

    // 复制前把画风变量替换为当前选用的画风，避免把占位符原样粘贴给豆包
    const { text, missingArtStyle } = preparePromptForCopy(
      prompt,
      settings?.art_styles ?? [],
      settings?.active_art_style ?? null,
    )
    if (missingArtStyle) {
      message.warning(
        '提示词包含画风变量，请先在下方画风列表中选用一个画风',
      )
      return
    }

    try {
      await copyText(text)
      message.success(
        settings && prompt !== settings.prompt
          ? '已复制当前编辑内容（尚未保存）'
          : '启动提示词已复制，可直接粘贴到豆包新会话',
      )
    } catch {
      message.error('复制失败，请手动选中文本后复制')
    }
  }

  return (
    <>
      <Card
        className="panel"
        loading={loading}
        title={
          <Space>
            <EditOutlined />
            启动提示词
          </Space>
        }
        extra={
          <Space>
            {settings &&
              (settings.is_default ? (
                <Tag>默认提示词</Tag>
              ) : (
                <Tag color="blue">自定义</Tag>
              ))}
            <Button
              icon={<CopyOutlined />}
              onClick={() => void handleCopyPrompt()}
              disabled={loading}
            >
              复制提示词
            </Button>
            <Tooltip
              title={
                settings && !settings.deepseek.configured
                  ? '请先在「设置」页配置 DeepSeek API Key'
                  : undefined
              }
            >
              <span>
                <Button
                  icon={<RobotOutlined />}
                  onClick={() => setOptimizerOpen(true)}
                  disabled={loading || !settings?.deepseek.configured}
                >
                  AI 优化
                </Button>
              </span>
            </Tooltip>
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          支持变量：<Typography.Text code>{'{story_name}'}</Typography.Text>
          （故事名）、
          <Typography.Text code>{'{story_content}'}</Typography.Text>
          （故事原文）、
          <Typography.Text code>{ART_STYLE_PLACEHOLDER}</Typography.Text>
          （画风描述）、
          <Typography.Text code>{ART_STYLE_NAME_PLACEHOLDER}</Typography.Text>
          （画风名称）。生成与复制时自动替换为当前选用的画风；若未使用变量，故事内容会作为用户消息单独发送。
        </Typography.Paragraph>
        <Typography.Paragraph type="secondary">
          左侧编辑原始提示词，右侧实时预览画风变量替换后的完整内容。点击右上角「复制提示词」可一键复制，粘贴到豆包等外部会话中使用；若有未保存的修改，会一并复制。
        </Typography.Paragraph>

        <div className="prompt-columns">
          <div>
            <Typography.Text type="secondary" className="prompt-column-label">
              编辑（保留变量占位符）
            </Typography.Text>
            <Input.TextArea
              value={prompt}
              onChange={(event) => onPromptChange(event.target.value)}
              rows={16}
              maxLength={10000}
              showCount
              placeholder="请输入生成小红书图文时使用的启动提示词"
              style={{ fontFamily: 'Menlo, Consolas, monospace', fontSize: 13 }}
            />
          </div>
          <div>
            <Typography.Text type="secondary" className="prompt-column-label">
              实时预览（画风变量已替换）
            </Typography.Text>
            <Input.TextArea
              className="prompt-preview-textarea"
              value={preview.text}
              readOnly
              rows={16}
              style={{ fontFamily: 'Menlo, Consolas, monospace', fontSize: 13 }}
            />
            <Typography.Text
              type={preview.missingArtStyle ? 'warning' : 'secondary'}
              className="prompt-preview-tip"
            >
              {preview.missingArtStyle
                ? '提示词包含画风变量，但尚未选用画风，预览中暂保留占位符'
                : '{story_name} / {story_content} 在生成时按所选故事替换，预览中保留占位符'}
            </Typography.Text>
          </div>
        </div>

        <div className="panel-footer">
          <Typography.Text type="secondary">
            {settings?.prompt_updated_at
              ? `最后保存：${dayjs(settings.prompt_updated_at).format(
                  'YYYY-MM-DD HH:mm:ss',
                )}`
              : '当前使用默认提示词'}
          </Typography.Text>
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleResetPrompt}
              disabled={savingPrompt}
            >
              恢复默认
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={savingPrompt}
              onClick={() => void handleSavePrompt()}
            >
              保存提示词
            </Button>
          </Space>
        </div>
      </Card>

      <PromptOptimizerDrawer
        open={optimizerOpen}
        currentPrompt={prompt}
        onClose={() => setOptimizerOpen(false)}
        onApply={(value) => onPromptChange(value)}
      />
    </>
  )
}
