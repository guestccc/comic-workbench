import { useEffect, useState } from 'react'
import { App, Alert, Button, Select, Space, Typography } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'

/**
 * 发布设置：维护全局预设标签。
 *
 * 预设标签只是章节发布面板的候选项，章节实际使用的标签仍然保存在
 * story_chapter_post_configs.tags，不是第二份源数据。
 */
export default function PublishSettingsPanel() {
  const { message } = App.useApp()
  const [tags, setTags] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .getPublishTagPresets()
      .then((data) => {
        if (!cancelled) setTags(data.tags)
      })
      .catch((error) => {
        if (!cancelled) message.error(getErrorMessage(error))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [message])

  const handleSave = async () => {
    setSaving(true)
    try {
      const saved = await api.savePublishTagPresets(tags)
      setTags(saved.tags)
      message.success('预设标签已保存')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="publish-settings">
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="预设标签只作为章节发布时的候选项"
        description="在「发文配置」tab 里为每一章选择实际使用的标签；修改这里不会改动已保存的章节标签。"
      />

      <Typography.Paragraph type="secondary">
        输入常用标签后回车；最多 10 个，发布时按 #话题 追加到正文末尾。
      </Typography.Paragraph>

      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <Select
          mode="tags"
          value={tags}
          loading={loading}
          maxCount={10}
          placeholder="例如：重生、爽文、逆袭"
          tokenSeparators={[',', '，', '#']}
          style={{ width: '100%' }}
          onChange={(value: string[]) => setTags(value)}
        />
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={() => void handleSave()}
        >
          保存预设标签
        </Button>
      </Space>
    </div>
  )
}
