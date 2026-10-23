import { useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Space,
  Tag,
  Typography,
} from 'antd'
import { CopyOutlined, EditOutlined } from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'
import type { CharacterCard, StoryBreakdown } from '../types'
import { copyText } from '../utils/clipboard'

interface CharacterCardsTabProps {
  breakdown: StoryBreakdown | null
  onRefresh: () => Promise<void>
}

/** 角色卡编辑表单：index 为 -1 时表示新卡。 */
interface CardFormValues {
  name: string
  role: string
  appearance: string
}

/** 生图提示词中的角色变量写法，例如 {{我}}。 */
function characterVariable(name: string): string {
  return `{{${name}}}`
}

/** 复制单个角色的变量绑定时使用的完整文本。 */
function characterBinding(card: CharacterCard): string {
  return `${characterVariable(card.name)}：${card.appearance}`
}

/**
 * 角色设定卡 tab。
 *
 * 角色卡的 name 同时是生图提示词里的变量名（{{角色名}}）。
 * 这里负责维护角色外形，并提供变量绑定文本，方便用户复制到外部生图 AI；
 * 参考垫图与变量绑定由用户在生图 AI 中完成，本工作台不生成、不管理垫图。
 */
export default function CharacterCardsTab({
  breakdown,
  onRefresh,
}: CharacterCardsTabProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<CardFormValues>()

  const [cardOpen, setCardOpen] = useState(false)
  // -1 表示新增；否则为要替换的卡片下标
  const [editingIndex, setEditingIndex] = useState(-1)
  const [cardSaving, setCardSaving] = useState(false)

  const openCard = (index: number) => {
    setEditingIndex(index)
    const card = index >= 0 ? breakdown?.characters[index] : undefined
    form.setFieldsValue({
      name: card?.name ?? '',
      role: card?.role ?? '',
      appearance: card?.appearance ?? '',
    })
    setCardOpen(true)
  }

  const saveCard = async () => {
    if (!breakdown) return

    let values: CardFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    const next: CharacterCard = {
      name: values.name.trim(),
      role: (values.role ?? '').trim(),
      appearance: values.appearance.trim(),
    }
    // 替换或追加，随后整体写回 characters 数组
    const characters = [...breakdown.characters]
    if (editingIndex >= 0) {
      characters[editingIndex] = next
    } else {
      characters.push(next)
    }

    setCardSaving(true)
    try {
      await api.patchBreakdown(breakdown.story_id, { characters })
      setCardOpen(false)
      message.success(editingIndex >= 0 ? '角色卡已更新' : '角色卡已新增')
      await onRefresh()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setCardSaving(false)
    }
  }

  /** 复制单个角色的变量绑定，例如「{{我}}：28岁……」。 */
  const handleCopyCharacter = async (card: CharacterCard) => {
    try {
      await copyText(characterBinding(card))
      message.success(`${characterVariable(card.name)} 的角色设定已复制`)
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  /** 一次性复制全部变量绑定，便于粘贴到外部生图 AI。 */
  const handleCopyAll = async () => {
    if (!breakdown || breakdown.characters.length === 0) {
      message.warning('还没有角色卡')
      return
    }
    try {
      await copyText(
        breakdown.characters.map((card) => characterBinding(card)).join('\n\n'),
      )
      message.success('全部角色变量已复制')
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  if (!breakdown) {
    return (
      <Empty description="还没有角色设定卡">
        <Typography.Text type="secondary">
          角色设定卡与分镜会一次性生成；在页面右上角复制拆解指令，
          粘贴到 Claude Code 中运行后会自动写回这里。
        </Typography.Text>
      </Empty>
    )
  }

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="生图变量说明"
        description={
          <>
            每页生图提示词中的 <Typography.Text code>{'{{角色名}}'}</Typography.Text>{' '}
            会引用这里的角色外形。请先在外部生图 AI 中把变量绑定到对应角色参考图，
            再复制页面提示词使用；本工作台不生成、不管理参考垫图。
          </>
        }
      />

      <div className="story-tab-toolbar">
        <Typography.Text type="secondary">
          共 {breakdown.characters.length} 个角色 · 生图提示词使用{' '}
          {'{{角色名}}'} 变量
        </Typography.Text>
        <Space size="small" wrap>
          <Button
            size="small"
            icon={<CopyOutlined />}
            disabled={breakdown.characters.length === 0}
            onClick={() => void handleCopyAll()}
          >
            复制全部变量
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            disabled={breakdown.characters.length >= 20}
            onClick={() => openCard(-1)}
          >
            新增角色卡
          </Button>
        </Space>
      </div>

      {breakdown.characters.length === 0 ? (
        <Empty description="还没有角色卡">
          <Typography.Text type="secondary">
            可以点击右上角「新增角色卡」手动补充，或重新运行拆解技能生成。
          </Typography.Text>
        </Empty>
      ) : (
        <div className="character-grid">
          {breakdown.characters.map((card, index) => (
            <Card
              key={`${card.name}-${index}`}
              size="small"
              className="character-card"
              title={
                <Space size={8} wrap>
                  <Typography.Text strong>{card.name}</Typography.Text>
                  <Tag color="geekblue">{characterVariable(card.name)}</Tag>
                  {card.role && <Tag color="magenta">{card.role}</Tag>}
                </Space>
              }
              extra={
                <Space size={0}>
                  <Button
                    type="link"
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => void handleCopyCharacter(card)}
                  >
                    复制变量
                  </Button>
                  <Button
                    type="link"
                    size="small"
                    onClick={() => openCard(index)}
                  >
                    编辑
                  </Button>
                </Space>
              }
            >
              <Typography.Paragraph className="content-preview">
                {card.appearance}
              </Typography.Paragraph>
            </Card>
          ))}
        </div>
      )}

      <Modal
        title={editingIndex >= 0 ? '编辑角色卡' : '新增角色卡'}
        open={cardOpen}
        onCancel={() => setCardOpen(false)}
        onOk={() => void saveCard()}
        confirmLoading={cardSaving}
        okText="保存"
        cancelText="取消"
        width={680}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="角色名（同时作为生图变量名）"
            rules={[{ required: true, message: '请输入角色名' }]}
            extra="第一人称主角统一用「我」，其他人使用姓名；变量写法为 {{角色名}}，保存后不要随意改名。"
          >
            <Input maxLength={50} showCount />
          </Form.Item>
          <Form.Item name="role" label="身份">
            <Input maxLength={50} showCount placeholder="如：男主、女主、小八老师" />
          </Form.Item>
          <Form.Item
            name="appearance"
            label="外形描述"
            rules={[{ required: true, message: '请输入外形描述' }]}
            extra="覆盖发型、长相、年龄感、服装、配饰与体态。生图提示词只引用变量，完整外形以这里为准。"
          >
            <Input.TextArea rows={8} maxLength={2000} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
