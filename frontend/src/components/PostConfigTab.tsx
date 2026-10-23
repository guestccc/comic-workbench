import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Form,
  Input,
  Space,
  Typography,
} from 'antd'
import { SaveOutlined, ThunderboltOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, getErrorMessage } from '../api/client'
import type { Story, StoryPostConfig } from '../types'

interface PostConfigTabProps {
  story: Story
  postConfig: StoryPostConfig | null
  keyConfigured: boolean
  onSaved: (config: StoryPostConfig) => void
}

interface PostConfigFormValues {
  title: string
  content: string
}

/**
 * 发文配置 tab。
 *
 * 每个故事一份独立的小红书标题与正文，和「发文管理」中的多条 posts 互不影响。
 * 允许保存空内容，方便先占位、后补写。
 */
export default function PostConfigTab({
  story,
  postConfig,
  keyConfigured,
  onSaved,
}: PostConfigTabProps) {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<PostConfigFormValues>()
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)

  // 配置加载完成或保存后同步到表单
  useEffect(() => {
    form.setFieldsValue({
      title: postConfig?.title ?? '',
      content: postConfig?.content ?? '',
    })
  }, [postConfig, form])

  const handleSave = async () => {
    let values: PostConfigFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    setSaving(true)
    try {
      const saved = await api.savePostConfig(story.id, {
        title: values.title ?? '',
        content: values.content ?? '',
      })
      onSaved(saved)
      message.success('发文配置已保存')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const copy = await api.generateCopy(story.id)
      // 生成结果只填入表单，不自动保存，避免覆盖用户已编辑的内容
      form.setFieldsValue({ title: copy.title, content: copy.content })
      message.success('文案已生成，确认后请点击保存')
    } catch (error) {
      if (error instanceof ApiError && error.code === 'DEEPSEEK_KEY_MISSING') {
        modal.confirm({
          title: '尚未配置 DeepSeek API Key',
          content: error.message,
          okText: '去配置',
          cancelText: '取消',
          onOk: () => navigate('/settings'),
        })
      } else {
        message.error(getErrorMessage(error))
      }
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div>
      {!keyConfigured && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="尚未配置 DeepSeek API Key，暂时无法使用 AI 生成文案"
          description="仍可手动填写标题与正文并保存；如需 AI 生成，请先到「设置」页配置 Key。"
          action={
            <Button size="small" onClick={() => navigate('/settings')}>
              去配置
            </Button>
          }
        />
      )}

      <Form form={form} layout="vertical">
        <Form.Item
          name="title"
          label="小红书标题（18 字以内）"
          rules={[{ max: 18, message: '标题不能超过 18 字' }]}
          extra="用户刷到作品时，第一眼只看到标题和第 1 页封面图，正文要点进来才看得到。标题用反差、悬念、利益点或强情绪制造点击欲，不要平铺直叙地概括剧情。"
        >
          <Input
            maxLength={18}
            showCount
            placeholder="例如：相亲对象开口就问我有没有A8"
          />
        </Form.Item>

        <Form.Item
          name="content"
          label="内容介绍"
          extra="小红书正文，可包含 emoji 与话题标签；可留空，之后再补。"
        >
          <Input.TextArea
            rows={12}
            maxLength={20000}
            showCount
            placeholder="正文内容..."
          />
        </Form.Item>
      </Form>

      <div className="panel-footer">
        <Typography.Text type="secondary">
          {postConfig
            ? `最近保存：${dayjs(postConfig.updated_at).format('YYYY-MM-DD HH:mm')}`
            : '尚未保存过发文配置'}
        </Typography.Text>
        <Space wrap>
          <Button
            icon={<ThunderboltOutlined />}
            loading={generating}
            disabled={!keyConfigured}
            onClick={() => void handleGenerate()}
          >
            AI 生成文案
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            onClick={() => void handleSave()}
          >
            保存配置
          </Button>
        </Space>
      </div>
    </div>
  )
}
