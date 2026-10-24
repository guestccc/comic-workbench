import { useState } from 'react'
import { Alert, App, Button, Card, Input, Space, Tag, Typography } from 'antd'
import { CheckCircleFilled, KeyOutlined } from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'
import type { SettingsData } from '../types'

interface DeepSeekKeyPanelProps {
  settings: SettingsData | null
  loading: boolean
  /** 保存 / 清除 Key 后同步最新设置 */
  onSaved: (data: SettingsData) => void
}

/** DeepSeek API Key 配置卡片（Key 只存本机，响应中始终脱敏）。 */
export default function DeepSeekKeyPanel({
  settings,
  loading,
  onSaved,
}: DeepSeekKeyPanelProps) {
  const { message, modal } = App.useApp()
  const [apiKey, setApiKey] = useState('')
  const [savingKey, setSavingKey] = useState(false)

  const handleSaveKey = async () => {
    if (!apiKey.trim()) {
      message.warning('请输入 DeepSeek API Key')
      return
    }
    setSavingKey(true)
    try {
      const data = await api.saveDeepseekKey(apiKey.trim())
      onSaved(data)
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
          onSaved(data)
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
              description="配置后即可在故事详情的「发文配置」中按章生成标题与正文。"
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
  )
}
