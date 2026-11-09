import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Input,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  CheckCircleFilled,
  ExperimentOutlined,
  KeyOutlined,
  PictureOutlined,
} from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'
import type { SettingsData } from '../types'

interface ImageProviderPanelProps {
  settings: SettingsData | null
  loading: boolean
  onSaved: (data: SettingsData) => void
}

const QUALITY_OPTIONS = [
  { value: 'auto', label: 'auto（跟随模型）' },
  { value: 'low', label: 'low' },
  { value: 'medium', label: 'medium' },
  { value: 'high', label: 'high' },
]

/** 生图服务配置卡片：Key 只存本机，响应中始终脱敏。 */
export default function ImageProviderPanel({
  settings,
  loading,
  onSaved,
}: ImageProviderPanelProps) {
  const { message, modal } = App.useApp()
  const provider = settings?.image_provider
  const [baseUrl, setBaseUrl] = useState('https://scpyx.com')
  const [model, setModel] = useState('gpt-image-2.5-sunburst')
  const [size, setSize] = useState('1024x1536')
  const [quality, setQuality] = useState('high')
  const [apiKey, setApiKey] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    if (!provider) return
    setBaseUrl(provider.base_url)
    setModel(provider.model)
    setSize(provider.size)
    setQuality(provider.quality)
  }, [provider])

  const modelOptions = Array.from(
    new Set([model, ...models, 'gpt-image-2.5-sunburst', 'gpt-image-2.5'].filter(Boolean)),
  ).map((value) => ({ value, label: value }))

  const handleTest = async () => {
    setTesting(true)
    try {
      const result = await api.testImageProvider()
      if (result.ok) {
        setModels(result.models)
        if (result.models.length && !result.models.includes(model)) {
          setModel(result.models[0])
        }
        message.success(result.message)
      } else {
        message.error(result.message || '连接失败')
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    if (!baseUrl.trim() || !model.trim() || !size.trim()) {
      message.warning('请填写接口地址、模型和尺寸')
      return
    }
    setSaving(true)
    try {
      const data = await api.saveImageProvider({
        base_url: baseUrl.trim(),
        model: model.trim(),
        size: size.trim(),
        quality: quality as 'auto' | 'low' | 'medium' | 'high',
        api_key: apiKey.trim() || undefined,
      })
      onSaved(data)
      setApiKey('')
      message.success('生图服务配置已保存')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleClearKey = () => {
    modal.confirm({
      title: '清除已保存的生图 API Key？',
      content:
        provider?.source === 'env'
          ? '当前生效的是环境变量中的 Key，清除本地 Key 后仍会使用环境变量。'
          : '清除后将无法在工作台内直接生图，需要重新配置。',
      okText: '清除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const data = await api.clearImageProviderKey()
          onSaved(data)
          message.success('已清除本地保存的生图 Key')
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  const sourceTag = provider ? (
    provider.source === 'env' ? (
      <Tag color="green" icon={<CheckCircleFilled />}>
        环境变量生效
      </Tag>
    ) : provider.source === 'db' ? (
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
          <PictureOutlined />
          生图服务
        </Space>
      }
      extra={sourceTag}
    >
      {provider && (
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <div>
            <Typography.Text>当前 Key：</Typography.Text>
            {provider.masked_key ? (
              <Typography.Text code>{provider.masked_key}</Typography.Text>
            ) : (
              <Typography.Text type="secondary">尚未配置</Typography.Text>
            )}
          </div>

          {provider.source === 'env' && (
            <Alert
              type="info"
              showIcon
              message="当前生效的是环境变量 IMAGE_PROVIDER_API_KEY"
              description="在此保存的 Key 将在移除环境变量后生效。"
            />
          )}

          {!provider.configured && (
            <Alert
              type="warning"
              showIcon
              message="尚未配置生图服务，无法在页面内直接生图"
              description="配置后可生成角色资产图与章节封面；生成结果会先进入历史，确认后才写入正式图。"
            />
          )}

          <Space.Compact style={{ width: '100%' }}>
            <Input
              prefix={<KeyOutlined />}
              placeholder="输入生图 API Key（留空保持不变）"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
            <Button onClick={handleClearKey} disabled={!provider.db_configured}>
              清除本地 Key
            </Button>
          </Space.Compact>
          <Typography.Text type="secondary">
            测试连接使用已保存的 Key；修改 Key 后请先保存再测试。
          </Typography.Text>

          <Space.Compact style={{ width: '100%' }}>
            <Input
              addonBefore="接口地址"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
            />
          </Space.Compact>

          <Space.Compact style={{ width: '100%' }}>
            <Select
              showSearch
              style={{ width: '100%' }}
              value={model}
              options={modelOptions}
              onChange={setModel}
              placeholder="模型"
            />
            <Button
              icon={<ExperimentOutlined />}
              loading={testing}
              onClick={() => void handleTest()}
            >
              测试连接
            </Button>
          </Space.Compact>
          {models.length > 0 && (
            <Typography.Text type="secondary">
              当前分组可用：{models.join('、')}
            </Typography.Text>
          )}

          <Space.Compact style={{ width: '100%' }}>
            <Input
              addonBefore="尺寸"
              value={size}
              onChange={(event) => setSize(event.target.value)}
            />
            <Select
              style={{ width: 220 }}
              value={quality}
              options={QUALITY_OPTIONS}
              onChange={setQuality}
            />
          </Space.Compact>

          <Typography.Text type="secondary">
            同步生成最长等待 600 秒；生成结果先进入历史，确认后才替换正式图。
          </Typography.Text>

          <Button type="primary" loading={saving} onClick={() => void handleSave()}>
            保存生图配置
          </Button>
        </Space>
      )}
    </Card>
  )
}
