import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Input,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  CheckCircleFilled,
  CopyOutlined,
  EditOutlined,
  KeyOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import PageHeader from '../components/PageHeader'
import PromptOptimizerDrawer from '../components/PromptOptimizerDrawer'
import { api, getErrorMessage } from '../api/client'
import type { SettingsData } from '../types'
import { copyText } from '../utils/clipboard'

export default function SettingsPage() {
  const { message, modal } = App.useApp()
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(true)
  const [savingPrompt, setSavingPrompt] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [savingKey, setSavingKey] = useState(false)
  const [optimizerOpen, setOptimizerOpen] = useState(false)

  const load = async () => {
    try {
      const data = await api.getSettings()
      setSettings(data)
      setPrompt(data.prompt)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const handleSavePrompt = async () => {
    if (!prompt.trim()) {
      message.warning('启动提示词不能为空')
      return
    }
    setSavingPrompt(true)
    try {
      const data = await api.savePrompt(prompt)
      setSettings(data)
      setPrompt(data.prompt)
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
          setSettings(data)
          setPrompt(data.prompt)
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
    try {
      await copyText(prompt)
      message.success(
        settings && prompt !== settings.prompt
          ? '已复制当前编辑内容（尚未保存）'
          : '启动提示词已复制，可直接粘贴到豆包新会话',
      )
    } catch {
      message.error('复制失败，请手动选中文本后复制')
    }
  }

  const handleSaveKey = async () => {
    if (!apiKey.trim()) {
      message.warning('请输入 DeepSeek API Key')
      return
    }
    setSavingKey(true)
    try {
      const data = await api.saveDeepseekKey(apiKey.trim())
      setSettings(data)
      setApiKey('')
      message.success('DeepSeek API Key 已保存')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSavingKey(false)
    }
  }

  const handleClearKey = () => {
    modal.confirm({
      title: '清除已保存的 API Key？',
      content:
        settings?.deepseek.source === 'env'
          ? '当前生效的是环境变量中的 Key，清除本地 Key 后仍会使用环境变量。'
          : '清除后将无法生成 AI 文案，需要重新配置。',
      okText: '清除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const data = await api.clearDeepseekKey()
          setSettings(data)
          message.success('已清除本地保存的 Key')
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  const sourceTag = settings ? (
    settings.deepseek.source === 'env' ? (
      <Tag color="green" icon={<CheckCircleFilled />}>
        环境变量生效
      </Tag>
    ) : settings.deepseek.source === 'db' ? (
      <Tag color="blue">本地已配置</Tag>
    ) : (
      <Tag>未配置</Tag>
    )
  ) : null

  return (
    <div>
      <PageHeader
        title="启动提示词"
        description="每次生成 AI 文案时，系统会使用这条提示词作为系统指令。"
      />

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
                  ? '请先在下方配置 DeepSeek API Key'
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
          （故事原文）。生成时自动替换；若未使用变量，故事内容会作为用户消息单独发送。
        </Typography.Paragraph>
        <Typography.Paragraph type="secondary">
          点击右上角「复制提示词」可一键复制当前编辑内容，粘贴到豆包等外部会话中使用；若有未保存的修改，会一并复制。
        </Typography.Paragraph>

        <Input.TextArea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={16}
          maxLength={10000}
          showCount
          placeholder="请输入生成小红书图文时使用的启动提示词"
          style={{ fontFamily: 'Menlo, Consolas, monospace', fontSize: 13 }}
        />

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

      <Card
        className="panel"
        loading={loading}
        title={
          <Space>
            <KeyOutlined />
            DeepSeek 配置
          </Space>
        }
        extra={sourceTag}
      >
        {settings && (
          <Space direction="vertical" size={14} style={{ width: '100%' }}>
            <div>
              <Typography.Text>当前 Key：</Typography.Text>
              {settings.deepseek.masked_key ? (
                <Typography.Text code>
                  {settings.deepseek.masked_key}
                </Typography.Text>
              ) : (
                <Typography.Text type="secondary">尚未配置</Typography.Text>
              )}
            </div>

            {settings.deepseek.source === 'env' && (
              <Alert
                type="info"
                showIcon
                message="当前生效的是环境变量 DEEPSEEK_API_KEY"
                description="在此保存的 Key 将在移除环境变量后生效。"
              />
            )}

            {!settings.deepseek.configured && (
              <Alert
                type="warning"
                showIcon
                message="尚未配置 API Key，无法生成小红书文案"
                description="配置后即可在「发文管理」中根据故事一键生成标题与正文。"
              />
            )}

            <Space.Compact style={{ width: '100%' }}>
              <Input.Password
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="输入 DeepSeek API Key（sk-...）"
                autoComplete="new-password"
                onPressEnter={() => void handleSaveKey()}
              />
              <Button
                type="primary"
                loading={savingKey}
                onClick={() => void handleSaveKey()}
              >
                保存 Key
              </Button>
            </Space.Compact>

            {settings.deepseek.db_configured && (
              <div>
                <Button danger onClick={handleClearKey}>
                  清除已保存的 Key
                </Button>
              </div>
            )}

            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Key 以明文保存在本机 SQLite 中，服务仅监听
              127.0.0.1。更推荐通过环境变量 DEEPSEEK_API_KEY 配置。
            </Typography.Text>
          </Space>
        )}
      </Card>

      <PromptOptimizerDrawer
        open={optimizerOpen}
        currentPrompt={prompt}
        onClose={() => setOptimizerOpen(false)}
        onApply={(value) => setPrompt(value)}
      />
    </div>
  )
}
