import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Drawer,
  Input,
  InputNumber,
  Modal,
  List,
  Popconfirm,
  Space,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import {
  CodeOutlined,
  EyeOutlined,
  HistoryOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, getErrorMessage } from '../api/client'
import type { PromptTemplateVersion, PromptTemplatesData } from '../types'

const PLACEHOLDER_HELP: Record<string, string> = {
  art_style: '故事画风原文（自动注入）',
  content: 'Claude 写的本页 / 本章画面描述',
  character_consistency: '角色一致性说明',
  text_zone: '文字区（自动根据旁白 / 标红 / 台词生成）',
  page_number: '章内页码（仅正文）',
  cover_mode: '封面模式（默认原画风 + 冲击层）',
  negative_prompt: '负面提示词（全局默认）',
}

const BODY_PREVIEW_CONTEXT = {
  content: '火车站候车厅，白天，{{我}}站在安检机旁。',
  character_consistency: '严格遵循 {{我}} 的角色卡与参考垫图。',
  narration_main: '这一次我不等了',
  narration_sub: '我站在站台上；\n风很冷。',
  narration_highlight: '不等了',
  dialogues: ['我：走吧。'],
  page_number: 1,
}

const COVER_PREVIEW_CONTEXT = {
  content: '3:4竖版封面，{{我}}在安检口回头。',
  character_consistency: '严格遵循 {{我}} 的角色卡与参考垫图。',
  narration_main: '箱子里出现了两把枪',
  narration_sub: '拉链一开，两把枪。',
  narration_highlight: '两把枪',
  dialogues: [],
  label: '第1章 · 示例标题',
}

/** 正文 / 封面提示词模板：固定结构由后端统一渲染。 */
export default function PromptTemplatePanel() {
  const { message } = App.useApp()
  const [templates, setTemplates] = useState<PromptTemplatesData | null>(null)
  const [body, setBody] = useState('')
  const [cover, setCover] = useState('')
  const [activeTab, setActiveTab] = useState<'body' | 'cover'>('body')
  const [storyId, setStoryId] = useState<number | null>(1)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [preview, setPreview] = useState('')
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [versions, setVersions] = useState<PromptTemplateVersion[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await api.getPromptTemplates()
        if (!cancelled) {
          setTemplates(data)
          setBody(data.body)
          setCover(data.cover)
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

  const placeholders = useMemo(
    () => templates?.placeholders ?? Object.keys(PLACEHOLDER_HELP),
    [templates],
  )

  const save = async () => {
    setSaving(true)
    try {
      const data = await api.savePromptTemplates({ body, cover })
      setTemplates(data)
      setBody(data.body)
      setCover(data.cover)
      message.success('提示词模板已保存')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const openVersions = async () => {
    setVersionsOpen(true)
    setVersionsLoading(true)
    try {
      setVersions(await api.listPromptTemplateVersions(activeTab))
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setVersionsLoading(false)
    }
  }

  const restoreVersion = async (version: PromptTemplateVersion) => {
    try {
      const data = await api.restorePromptTemplateVersion(version.id)
      setTemplates(data)
      setBody(data.body)
      setCover(data.cover)
      setVersionsOpen(false)
      message.success('模板已恢复到该版本')
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const resetActive = () => {
    if (!templates) return
    if (activeTab === 'body') {
      setBody(templates.body_default)
    } else {
      setCover(templates.cover_default)
    }
    message.info('已恢复默认内容，点击「保存模板」后生效')
  }

  const runPreview = async () => {
    if (!storyId) {
      message.warning('请填写一个已有画风的故事 ID 用于预览')
      return
    }
    setPreviewing(true)
    try {
      const result = await api.renderPromptTemplate({
        template_type: activeTab,
        story_id: storyId,
        preview: true,
        context:
          activeTab === 'body' ? BODY_PREVIEW_CONTEXT : COVER_PREVIEW_CONTEXT,
      })
      setPreview(result.prompt)
      setPreviewOpen(true)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setPreviewing(false)
    }
  }

  const editor = (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="模板只影响新生成 / 重新渲染的提示词"
        description="画风原文由 {art_style} 自动注入；不要在这里复制画风文字。修改模板不会自动改写已有页面和封面。"
      />
      <Space wrap size={[6, 6]}>
        {placeholders.map((name) => (
          <Tag key={name} color="blue">
            {'{' + name + '}'}：{PLACEHOLDER_HELP[name] ?? '可用占位符'}
          </Tag>
        ))}
      </Space>
      <Input.TextArea
        className="prompt-template-editor"
        rows={18}
        value={activeTab === 'body' ? body : cover}
        onChange={(event) =>
          activeTab === 'body'
            ? setBody(event.target.value)
            : setCover(event.target.value)
        }
        spellCheck={false}
      />
      <Space wrap>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={() => void save()}
        >
          保存模板
        </Button>
        <Button icon={<ReloadOutlined />} onClick={resetActive}>
          恢复当前默认
        </Button>
        <Button icon={<HistoryOutlined />} onClick={() => void openVersions()}>
          历史版本
        </Button>
        <InputNumber
          min={1}
          value={storyId}
          onChange={setStoryId}
          placeholder="预览故事 ID"
          style={{ width: 140 }}
        />
        <Button
          icon={<EyeOutlined />}
          loading={previewing}
          onClick={() => void runPreview()}
        >
          预览渲染结果
        </Button>
      </Space>
    </Space>
  )

  return (
    <Card
      className="panel"
      loading={loading}
      title={
        <Space>
          <CodeOutlined />
          正文 / 封面提示词模板
        </Space>
      }
      extra={
        <Space size={6}>
          {templates?.body_is_default && <Tag>正文默认</Tag>}
          {templates?.cover_is_default && <Tag>封面默认</Tag>}
        </Space>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as 'body' | 'cover')}
        items={[
          {
            key: 'body',
            label: '正文模板',
            children: activeTab === 'body' ? editor : null,
          },
          {
            key: 'cover',
            label: '封面模板',
            children: activeTab === 'cover' ? editor : null,
          },
        ]}
      />
      <Typography.Text type="secondary">
        模板里的固定块由后端渲染；Claude 只提供画面内容、角色一致性和旁白字段。
      </Typography.Text>

      <Drawer
        title={`${activeTab === 'body' ? '正文' : '封面'}模板历史`}
        open={versionsOpen}
        onClose={() => setVersionsOpen(false)}
        width={760}
      >
        <List
          loading={versionsLoading}
          dataSource={versions}
          locale={{ emptyText: '还没有历史版本；保存一次模板后出现' }}
          renderItem={(version) => (
            <List.Item
              actions={[
                <Popconfirm
                  key="restore"
                  title="恢复到这个模板版本？"
                  onConfirm={() => void restoreVersion(version)}
                  okText="恢复"
                  cancelText="取消"
                >
                  <Button size="small">恢复此版</Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Typography.Text strong>
                      {dayjs(version.created_at).format('YYYY-MM-DD HH:mm:ss')}
                    </Typography.Text>
                    <Tag>{version.note}</Tag>
                  </Space>
                }
                description={
                  <Typography.Paragraph
                    type="secondary"
                    ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                    style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
                  >
                    {version.content}
                  </Typography.Paragraph>
                }
              />
            </List.Item>
          )}
        />
      </Drawer>

      <Modal
        open={previewOpen}
        title={`${activeTab === 'body' ? '正文' : '封面'}模板预览`}
        width={860}
        footer={
          <Button onClick={() => setPreviewOpen(false)}>关闭</Button>
        }
        onCancel={() => setPreviewOpen(false)}
      >
        <pre className="prompt-template-preview">{preview}</pre>
      </Modal>
    </Card>
  )
}
