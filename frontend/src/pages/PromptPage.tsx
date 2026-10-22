import { useEffect, useState } from 'react'
import { App } from 'antd'
import PageHeader from '../components/PageHeader'
import ArtStylePanel from '../components/ArtStylePanel'
import PromptEditorPanel from '../components/PromptEditorPanel'
import { api, getErrorMessage } from '../api/client'
import type { SettingsData } from '../types'

/** 启动提示词页：提示词编辑与画风列表。DeepSeek 配置在独立的「设置」页。 */
export default function PromptPage() {
  const { message } = App.useApp()
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(true)

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

  return (
    <div>
      <PageHeader
        title="启动提示词"
        description="每次生成 AI 文案时，系统会使用这条提示词作为系统指令。"
      />

      <PromptEditorPanel
        settings={settings}
        prompt={prompt}
        loading={loading}
        onPromptChange={setPrompt}
        onSettingsChange={setSettings}
      />

      <ArtStylePanel
        styles={settings?.art_styles ?? []}
        activeId={settings?.active_art_style ?? null}
        loading={loading}
        aiEnabled={Boolean(settings?.deepseek.configured)}
        onSaved={setSettings}
      />
    </div>
  )
}
