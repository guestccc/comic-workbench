import { useEffect, useState } from 'react'
import { App, Tabs } from 'antd'
import PageHeader from '../components/PageHeader'
import DeepSeekKeyPanel from '../components/DeepSeekKeyPanel'
import ImageProviderPanel from '../components/ImageProviderPanel'
import PromptTemplatePanel from '../components/PromptTemplatePanel'
import SensitiveWordsPanel from '../components/SensitiveWordsPanel'
import { api, getErrorMessage } from '../api/client'
import type { SettingsData } from '../types'

const SETTINGS_TAB_KEY = 'comic-workbench-settings-tab'
const SETTINGS_TABS = ['deepseek', 'image', 'templates', 'sensitive'] as const
type SettingsTabKey = (typeof SETTINGS_TABS)[number]

function readStoredTab(): SettingsTabKey {
  try {
    const stored = window.localStorage.getItem(SETTINGS_TAB_KEY)
    if (stored && (SETTINGS_TABS as readonly string[]).includes(stored)) {
      return stored as SettingsTabKey
    }
  } catch {
    // localStorage 不可用时只回退默认标签，不影响设置功能
  }
  return 'deepseek'
}

/** 设置页：按标签管理 DeepSeek、生图、提示词模板与敏感词库。 */
export default function SettingsPage() {
  const { message } = App.useApp()
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<SettingsTabKey>(readStoredTab)

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

  const handleTabChange = (key: string) => {
    if (!(SETTINGS_TABS as readonly string[]).includes(key)) return
    setActiveTab(key as SettingsTabKey)
    try {
      window.localStorage.setItem(SETTINGS_TAB_KEY, key)
    } catch {
      // 只影响下次默认标签，不影响当前设置
    }
  }

  return (
    <div>
      <PageHeader
        title="设置"
        description="按标签配置 DeepSeek、生图服务、提示词模板与敏感词库。"
      />

      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={[
          {
            key: 'deepseek',
            label: 'DeepSeek 服务',
            children: (
              <DeepSeekKeyPanel
                settings={settings}
                loading={loading}
                onSaved={setSettings}
              />
            ),
          },
          {
            key: 'image',
            label: '生图服务',
            children: (
              <ImageProviderPanel
                settings={settings}
                loading={loading}
                onSaved={setSettings}
              />
            ),
          },
          {
            key: 'templates',
            label: '提示词模板',
            children: <PromptTemplatePanel />,
          },
          {
            key: 'sensitive',
            label: '敏感词库',
            children: <SensitiveWordsPanel />,
          },
        ]}
      />
    </div>
  )
}
