import { useState } from 'react'
import { App, Button, Card, Select, Space, Typography } from 'antd'
import { BgColorsOutlined, PlusOutlined } from '@ant-design/icons'
import ArtStyleList from './ArtStyleList'
import ArtStyleEditorModal from './ArtStyleEditorModal'
import type { ArtStyleFormValues } from './ArtStyleEditorModal'
import { api, getErrorMessage } from '../api/client'
import type { ArtStyle, SettingsData } from '../types'
import {
  ART_STYLE_NAME_PLACEHOLDER,
  ART_STYLE_PLACEHOLDER,
} from '../utils/promptVariables'

interface ArtStylePanelProps {
  styles: ArtStyle[]
  activeId: string | null
  loading: boolean
  /** 是否已配置 DeepSeek Key，决定画风描述的「AI 优化」是否可用 */
  aiEnabled: boolean
  /** 保存成功后把最新设置同步给父组件 */
  onSaved: (data: SettingsData) => void
}

const MAX_STYLES = 20

/** 生成画风条目 id；crypto.randomUUID 在非安全上下文不可用，故提供回退。 */
function nextStyleId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `style-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 画风列表：新增 / 编辑 / 删除 / 选用，保存即生效（单次全量 PUT）。 */
export default function ArtStylePanel({
  styles,
  activeId,
  loading,
  aiEnabled,
  onSaved,
}: ArtStylePanelProps) {
  const { message } = App.useApp()
  const [saving, setSaving] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  // 从列表「AI 优化」进入时，弹窗打开后自动展开优化抽屉
  const [autoOptimize, setAutoOptimize] = useState(false)

  const editingStyle = editingId
    ? (styles.find((item) => item.id === editingId) ?? null)
    : null

  const persist = async (
    nextStyles: ArtStyle[],
    nextActiveId: string | null,
    successText: string,
  ): Promise<boolean> => {
    setSaving(true)
    try {
      const data = await api.saveArtStyles({
        styles: nextStyles,
        active_id: nextActiveId,
      })
      onSaved(data)
      message.success(successText)
      return true
    } catch (error) {
      message.error(getErrorMessage(error))
      return false
    } finally {
      setSaving(false)
    }
  }

  const handleSelect = (value?: string) => {
    const nextActiveId = value ?? null
    if (nextActiveId === activeId) return
    void persist(
      styles,
      nextActiveId,
      nextActiveId ? '已切换当前画风' : '已取消选用画风',
    )
  }

  const openCreate = () => {
    setEditingId(null)
    setAutoOptimize(false)
    setEditorOpen(true)
  }

  const openEdit = (style: ArtStyle) => {
    setEditingId(style.id)
    setAutoOptimize(false)
    setEditorOpen(true)
  }

  const openOptimize = (style: ArtStyle) => {
    setEditingId(style.id)
    setAutoOptimize(true)
    setEditorOpen(true)
  }

  const closeEditor = () => {
    setAutoOptimize(false)
    setEditorOpen(false)
  }

  const handleSubmit = async (values: ArtStyleFormValues) => {
    const { name, content } = values
    if (styles.some((item) => item.name === name && item.id !== editingId)) {
      message.warning('画风名称不能重复')
      return
    }

    let nextStyles: ArtStyle[]
    let nextActiveId = activeId
    if (editingId) {
      nextStyles = styles.map((item) =>
        item.id === editingId ? { ...item, name, content } : item,
      )
    } else {
      if (styles.length >= MAX_STYLES) {
        message.warning(`最多只能保存 ${MAX_STYLES} 个画风`)
        return
      }
      const newStyle = { id: nextStyleId(), name, content }
      nextStyles = [...styles, newStyle]
      // 新增第一个画风时自动选用，省去再点一次选择的步骤
      if (nextActiveId === null) {
        nextActiveId = newStyle.id
      }
    }

    const saved = await persist(
      nextStyles,
      nextActiveId,
      editingId ? '画风已更新' : '画风已添加',
    )
    if (saved) {
      closeEditor()
    }
  }

  const handleDelete = (style: ArtStyle) => {
    const nextStyles = styles.filter((item) => item.id !== style.id)
    const nextActiveId = activeId === style.id ? null : activeId
    void persist(nextStyles, nextActiveId, '画风已删除')
  }

  return (
    <Card
      className="panel"
      loading={loading}
      title={
        <Space>
          <BgColorsOutlined />
          画风列表
        </Space>
      }
      extra={
        <Button
          icon={<PlusOutlined />}
          onClick={openCreate}
          disabled={saving || styles.length >= MAX_STYLES}
        >
          新增画风
        </Button>
      }
    >
      <Typography.Paragraph type="secondary">
        先在下方维护命名的画风；在启动提示词中使用{' '}
        <Typography.Text code>{ART_STYLE_PLACEHOLDER}</Typography.Text>
        （画风描述）或{' '}
        <Typography.Text code>{ART_STYLE_NAME_PLACEHOLDER}</Typography.Text>
        （画风名称）变量，生成与复制提示词时会自动替换为当前选用的画风。编辑画风时可点击「AI
        优化」打磨描述。
      </Typography.Paragraph>

      <Space style={{ marginBottom: 12 }} wrap>
        <Typography.Text>当前选用：</Typography.Text>
        <Select
          value={activeId ?? undefined}
          onChange={handleSelect}
          allowClear
          placeholder="未选用"
          style={{ minWidth: 220 }}
          options={styles.map((style) => ({
            value: style.id,
            label: style.name,
          }))}
          disabled={saving || styles.length === 0}
        />
      </Space>

      <ArtStyleList
        styles={styles}
        activeId={activeId}
        saving={saving}
        aiEnabled={aiEnabled}
        onEdit={openEdit}
        onOptimize={openOptimize}
        onDelete={handleDelete}
      />

      <ArtStyleEditorModal
        open={editorOpen}
        isEditing={editingId !== null}
        initialName={editingStyle?.name ?? ''}
        initialContent={editingStyle?.content ?? ''}
        saving={saving}
        aiEnabled={aiEnabled}
        autoOpenOptimizer={autoOptimize}
        onCancel={closeEditor}
        onSubmit={(values) => void handleSubmit(values)}
      />
    </Card>
  )
}
