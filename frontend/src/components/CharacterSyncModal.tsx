import { useState } from 'react'
import { Alert, App, Button, Input, Modal, Space, Tag, Typography } from 'antd'
import { api, getErrorMessage } from '../api/client'
import type { CharacterSyncItem } from '../types'
import { parseCharacterCardsText } from '../utils/characterSync'

interface CharacterSyncModalProps {
  storyId: number
  /** 现有角色名，用于在预览中区分「更新」与「新增」 */
  existingNames: string[]
  open: boolean
  onClose: () => void
  /** 同步成功后由父组件刷新拆解数据 */
  onSynced: () => Promise<void>
}

/**
 * 同步角色卡弹窗。
 *
 * 对应用户在生图平台完成形象调整后的收尾流程：
 * 粘贴平台回复的 {{角色名}}：外形 文本 → 解析预览 → 确认后一次性写回角色卡，
 * 并由后端 AI 联动重写受影响分镜页的「人物回顾」。
 */
export default function CharacterSyncModal({
  storyId,
  existingNames,
  open,
  onClose,
  onSynced,
}: CharacterSyncModalProps) {
  const { message } = App.useApp()
  const [text, setText] = useState('')
  // 解析后的待同步卡片；null 表示尚未解析
  const [parsed, setParsed] = useState<CharacterSyncItem[] | null>(null)
  const [skippedBlocks, setSkippedBlocks] = useState(0)
  const [syncing, setSyncing] = useState(false)

  const existing = new Set(existingNames)

  const handleParse = () => {
    const { cards, skippedBlocks: skipped } = parseCharacterCardsText(text)
    setSkippedBlocks(skipped)
    if (cards.length === 0) {
      setParsed(null)
      message.warning(
        '没有解析到角色卡，请确认格式为「{{角色名}}：外形描述」，多个角色之间用空行分隔',
      )
      return
    }
    setParsed(cards)
  }

  const handleSync = async () => {
    if (!parsed || parsed.length === 0) return
    setSyncing(true)
    try {
      const result = await api.syncCharacters(storyId, parsed)
      const parts = [
        result.updated_names.length > 0
          ? `更新 ${result.updated_names.length} 张角色卡`
          : '',
        result.created_names.length > 0
          ? `新增 ${result.created_names.length} 张角色卡`
          : '',
        result.review_updated_pages.length > 0
          ? `人物回顾已同步第 ${result.review_updated_pages.join('、')} 页`
          : '',
      ].filter(Boolean)
      message.success(parts.join('；') || '角色卡已同步')
      if (result.review_warning) {
        message.warning(result.review_warning)
      }
      handleClose()
      await onSynced()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSyncing(false)
    }
  }

  const handleClose = () => {
    setText('')
    setParsed(null)
    setSkippedBlocks(0)
    onClose()
  }

  // 粘贴内容变化后旧预览失效，避免用户看着 A 的预览提交 B 的内容
  const handleTextChange = (value: string) => {
    setText(value)
    setParsed(null)
    setSkippedBlocks(0)
  }

  return (
    <Modal
      title="同步角色卡"
      open={open}
      onCancel={handleClose}
      width={720}
      destroyOnHidden
      footer={
        <Space>
          <Button onClick={handleClose}>取消</Button>
          <Button onClick={handleParse} disabled={!text.trim() || syncing}>
            解析预览
          </Button>
          <Button
            type="primary"
            loading={syncing}
            disabled={!parsed || parsed.length === 0}
            onClick={() => void handleSync()}
          >
            确认同步{parsed ? `（${parsed.length} 个角色）` : ''}
          </Button>
        </Space>
      }
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
        把生图平台回复的新版角色卡完整粘贴到这里。同步后对应分镜页的「人物回顾」
        会由 AI 按新外形自动重写；生图提示词使用 {'{{角色名}}'} 变量，无需改动。
      </Typography.Paragraph>

      <Input.TextArea
        rows={8}
        value={text}
        onChange={(event) => handleTextChange(event.target.value)}
        placeholder={
          '{{我}}：28岁左右的东亚男性，黑色短发……\n\n{{小八老师}}：28岁左右的成年女性……'
        }
      />

      {skippedBlocks > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 12 }}
          message={`有 ${skippedBlocks} 段文本没有识别为角色卡，已跳过`}
        />
      )}

      {parsed && (
        <div style={{ marginTop: 16 }}>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            解析到 {parsed.length} 个角色：
          </Typography.Text>
          <div className="sync-preview-list">
            {parsed.map((card) => (
              <div className="sync-preview-item" key={card.name}>
                <Space size={8} wrap>
                  <Typography.Text strong>{card.name}</Typography.Text>
                  {existing.has(card.name) ? (
                    <Tag color="blue">更新</Tag>
                  ) : (
                    <Tag color="green">新增</Tag>
                  )}
                </Space>
                <Typography.Paragraph
                  className="content-preview"
                  ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                >
                  {card.appearance}
                </Typography.Paragraph>
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}
