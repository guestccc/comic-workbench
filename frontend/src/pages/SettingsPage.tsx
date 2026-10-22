import { useEffect, useState } from 'react'
import { App } from 'antd'
import PageHeader from '../components/PageHeader'
import DeepSeekKeyPanel from '../components/DeepSeekKeyPanel'
import { api, getErrorMessage } from '../api/client'
import type { SettingsData } from '../types'

/** 设置页：独立管理 DeepSeek 服务配置。 */
export default function SettingsPage() {
  const { message } = App.useApp()
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const data = await api.getSettings()
        if (!cancelled) {
          setSettings(data)
        }
      } catch (error) {
        if (!cancelled) {
          message.error(getErrorMessage(error))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [message])

  return (
    <div>
      <PageHeader
        title="设置"
        description="配置 DeepSeek 服务后，即可使用 AI 生成文案与优化提示词。"
      />

      <DeepSeekKeyPanel
        settings={settings}
        loading={loading}
        onSaved={setSettings}
      />
    </div>
  )
}
