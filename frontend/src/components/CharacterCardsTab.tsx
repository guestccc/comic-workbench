import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Empty,
  Form,
  Input,
  Modal,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { CopyOutlined, EditOutlined, RobotOutlined, SyncOutlined } from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'
import CharacterSyncModal from './CharacterSyncModal'
import ImageUpload from './ImageUpload'
import PromptOptimizerDrawer from './PromptOptimizerDrawer'
import type { CharacterCard, SettingsData, StoryBreakdown } from '../types'
import { CHARACTER_SYNC_INSTRUCTION } from '../utils/characterSync'
import { copyText } from '../utils/clipboard'
import { withImagePrefix } from '../utils/imagePrefix'

interface CharacterCardsTabProps {
  breakdown: StoryBreakdown | null
  /** 是否已配置 DeepSeek Key，决定「AI 优化」是否可用 */
  aiEnabled: boolean
  /** 全局生图前置提示词，复制角色卡时自动拼在开头 */
  prefixPrompt: string
  /** 当前故事的画风名称，用于替换前置提示词里的 {art_style_name} */
  artStyleName: string | null
  onPrefixSaved: (settings: SettingsData) => void
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
  aiEnabled,
  prefixPrompt,
  artStyleName,
  onPrefixSaved,
  onRefresh,
}: CharacterCardsTabProps) {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm<CardFormValues>()

  // 前置提示词编辑草稿；保存后由父组件回传的设置覆盖
  const [prefixDraft, setPrefixDraft] = useState(prefixPrompt)
  const [prefixSaving, setPrefixSaving] = useState(false)

  useEffect(() => {
    setPrefixDraft(prefixPrompt)
  }, [prefixPrompt])

  const [cardOpen, setCardOpen] = useState(false)
  // -1 表示新增；否则为要替换的卡片下标
  const [editingIndex, setEditingIndex] = useState(-1)
  const [cardSaving, setCardSaving] = useState(false)

  // AI 优化抽屉当前针对的角色卡下标；-1 表示关闭
  const [optimizerIndex, setOptimizerIndex] = useState(-1)
  // 同步角色卡弹窗
  const [syncOpen, setSyncOpen] = useState(false)
  // 替换合照后 URL 不变，用版本号参数强制浏览器重新加载
  const [photoVersion, setPhotoVersion] = useState(0)

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

    // 编辑卡片时保留已上传的资产图；删掉这行会导致每次改外形都丢图
    const existing =
      editingIndex >= 0 ? breakdown?.characters[editingIndex] : undefined
    const next: CharacterCard = {
      name: values.name.trim(),
      role: (values.role ?? '').trim(),
      appearance: values.appearance.trim(),
      asset_filename: existing?.asset_filename ?? null,
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

  /**
   * 保存全局生图前置提示词。
   * 存在设置表里而不是某个故事上，所以以后新建的故事同样自动生效。
   */
  const handleSavePrefix = async () => {
    setPrefixSaving(true)
    try {
      const data = await api.saveImagePrefixPrompt(prefixDraft)
      onPrefixSaved(data)
      setPrefixDraft(data.image_prefix_prompt)
      message.success('前置提示词已保存，所有故事复制时都会自动带在开头')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setPrefixSaving(false)
    }
  }

  /** 上传单个角色的资产图；只保存在本地，供展示与对照。 */
  const handleUploadCharacterAsset = async (index: number, file: File) => {
    if (!breakdown) return
    try {
      await api.uploadCharacterAsset(breakdown.story_id, index, file)
      message.success('角色资产图已上传')
      await onRefresh()
    } catch (error) {
      message.error(getErrorMessage(error))
      // 抛出后由 ImageUpload 复位上传中状态
      throw error
    }
  }

  /** 删除单个角色的资产图。 */
  const handleDeleteCharacterAsset = (index: number) => {
    if (!breakdown) return
    modal.confirm({
      title: '删除这个角色的资产图？',
      content: '只删除本地存档的图片，不影响角色卡与分镜。',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteCharacterAsset(breakdown.story_id, index)
          message.success('角色资产图已删除')
          await onRefresh()
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  /** 复制内容统一拼上当前输入框里的前置提示词（未保存也按所见复制）。 */
  const withPrefix = (text: string) =>
    withImagePrefix(prefixDraft, artStyleName, text)

  /** 复制单个角色的变量绑定，例如「{{我}}：28岁……」。 */
  const handleCopyCharacter = async (card: CharacterCard) => {
    try {
      await copyText(withPrefix(characterBinding(card)))
      message.success(`${characterVariable(card.name)} 的角色设定已复制`)
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  /**
   * 应用 AI 优化后的外形描述：替换对应下标的 appearance 并整体写回。
   * 与手动编辑一致，应用即保存，无需二次确认。
   */
  const applyOptimizedAppearance = async (value: string) => {
    if (!breakdown || optimizerIndex < 0) return
    const index = optimizerIndex
    const characters = breakdown.characters.map((card, cardIndex) =>
      cardIndex === index ? { ...card, appearance: value.trim() } : card,
    )
    try {
      await api.patchBreakdown(breakdown.story_id, { characters })
      await onRefresh()
    } catch (error) {
      message.error(getErrorMessage(error))
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
        withPrefix(
          breakdown.characters.map((card) => characterBinding(card)).join('\n\n'),
        ),
      )
      message.success('全部角色变量已复制')
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  /** 复制发给生图平台的角色卡更新指令，省去每次手写。 */
  const handleCopySyncInstruction = async () => {
    try {
      await copyText(CHARACTER_SYNC_INSTRUCTION)
      message.success('更新指令已复制，直接发给生图平台即可')
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  /** 上传 / 替换最终确认的人物合照；文件只保存在本地 uploads 目录。 */
  const handleUploadGroupPhoto = async (file: File) => {
    if (!breakdown) return
    try {
      await api.uploadGroupPhoto(breakdown.story_id, file)
      setPhotoVersion(Date.now())
      message.success('人物合照已上传')
      await onRefresh()
    } catch (error) {
      message.error(getErrorMessage(error))
      // 抛出后由 ImageUpload 复位上传中状态
      throw error
    }
  }

  /** 删除人物合照。 */
  const handleDeleteGroupPhoto = () => {
    if (!breakdown) return
    modal.confirm({
      title: '删除人物合照？',
      content: '图片文件会从本地删除，不影响角色卡与分镜。',
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteGroupPhoto(breakdown.story_id)
          message.success('人物合照已删除')
          await onRefresh()
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      },
    })
  }

  /** 合照地址：替换后拼上版本号参数，避免浏览器缓存旧图。 */
  const groupPhotoSrc = (): string | null => {
    const url = breakdown?.group_photo_url
    if (!url) return null
    return photoVersion ? `${url}?v=${photoVersion}` : url
  }

  // 实时预览：把 {art_style_name} 换成当前故事的画风名称；未选画风时保留占位符并提示
  const prefixMissingArtStyle =
    prefixDraft.includes('{art_style_name}') && !artStyleName
  const prefixPreview = artStyleName
    ? prefixDraft.split('{art_style_name}').join(artStyleName)
    : prefixDraft

  // 全局生图前置提示词：所有故事共用一份，保存后新故事也自动生效。
  // 即使当前故事还没有拆解结果，也要能在这里编辑。
  const prefixPanel = (
    <Collapse
      style={{ marginBottom: 16 }}
      items={[
        {
          key: 'image-prefix',
          label: '生图前置提示词（全局 · 所有故事复制时自动带在开头）',
          children: (
            <>
              <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
                复制角色卡变量时，这段内容会自动拼在最前面，开新会话时贴一次即可。
                它保存在全局设置里，不隶属于某个故事，以后新建的故事同样适用。
                支持变量：<Typography.Text code>{'{art_style_name}'}</Typography.Text>
                （当前故事的画风名称）。
              </Typography.Paragraph>

              <div className="prompt-columns">
                <div>
                  <Typography.Text type="secondary" className="prompt-column-label">
                    编辑（保留变量占位符）
                  </Typography.Text>
                  <Input.TextArea
                    value={prefixDraft}
                    onChange={(event) => setPrefixDraft(event.target.value)}
                    rows={14}
                    maxLength={8000}
                    showCount
                    placeholder="留空表示复制时不拼任何前置内容"
                    style={{ fontFamily: 'Menlo, Consolas, monospace', fontSize: 13 }}
                  />
                </div>
                <div>
                  <Typography.Text type="secondary" className="prompt-column-label">
                    实时预览（画风变量已替换）
                  </Typography.Text>
                  <Input.TextArea
                    className="prompt-preview-textarea"
                    value={prefixPreview}
                    readOnly
                    rows={14}
                    style={{ fontFamily: 'Menlo, Consolas, monospace', fontSize: 13 }}
                  />
                  <Typography.Text
                    type={prefixMissingArtStyle ? 'warning' : 'secondary'}
                    className="prompt-preview-tip"
                  >
                    {prefixMissingArtStyle
                      ? '当前故事未选择画风，预览中暂保留占位符'
                      : '复制时按当前故事的画风名称替换；未使用的变量会原样保留'}
                  </Typography.Text>
                </div>
              </div>

              <div style={{ marginTop: 12, textAlign: 'right' }}>
                <Button
                  type="primary"
                  loading={prefixSaving}
                  onClick={() => void handleSavePrefix()}
                >
                  保存前置提示词
                </Button>
              </div>
            </>
          ),
        },
      ]}
    />
  )

  if (!breakdown) {
    return (
      <div>
        {prefixPanel}
        <Empty description="还没有角色设定卡">
          <Typography.Text type="secondary">
            先复制「分镜对照指令」确认拆页顺序，再复制「分镜头脚本指令」；
            角色卡与分镜会在生成脚本时自动写回这里。
          </Typography.Text>
        </Empty>
      </div>
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
            会引用这里的角色外形。每个角色可单独上传资产图，仅作本地存档与对照，
            不参与生图；变量绑定与最终生图仍在外部生图 AI 中完成。
          </>
        }
      />

      {prefixPanel}

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
          <Tooltip title="在生图平台确认形象后，把这条指令发给平台，让它输出新版完整角色卡">
            <Button
              size="small"
              icon={<CopyOutlined />}
              onClick={() => void handleCopySyncInstruction()}
            >
              复制更新指令
            </Button>
          </Tooltip>
          <Button
            size="small"
            icon={<SyncOutlined />}
            onClick={() => setSyncOpen(true)}
          >
            同步角色卡
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
                  <Tooltip
                    title={
                      aiEnabled
                        ? undefined
                        : '请先在「设置」页配置 DeepSeek API Key'
                    }
                  >
                    <Button
                      type="link"
                      size="small"
                      icon={<RobotOutlined />}
                      disabled={!aiEnabled}
                      onClick={() => setOptimizerIndex(index)}
                    >
                      AI 优化
                    </Button>
                  </Tooltip>
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
              <div className="character-card-body">
                <div className="character-asset">
                  <ImageUpload
                    imageUrl={card.asset_url}
                    onUpload={(file) =>
                      handleUploadCharacterAsset(index, file)
                    }
                    onRemove={() => handleDeleteCharacterAsset(index)}
                    maxSizeBytes={15 * 1024 * 1024}
                    variant="asset"
                    uploadText="上传资产图"
                    replaceText="替换资产图"
                  />
                  <Typography.Text
                    type="secondary"
                    className="character-asset-caption"
                  >
                    资产图 · 本地存档
                  </Typography.Text>
                </div>
                <Typography.Paragraph className="content-preview">
                  {card.appearance}
                </Typography.Paragraph>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* 最终确认的人物合照：在生图平台确认形象后上传存档，仅保存在本地 */}
      <Card
        size="small"
        className="group-photo-card"
        title="人物合照"
        extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            在生图平台确认全部角色形象后，把最终合照上传到这里存档核对
          </Typography.Text>
        }
      >
        <ImageUpload
          imageUrl={groupPhotoSrc()}
          onUpload={handleUploadGroupPhoto}
          onRemove={handleDeleteGroupPhoto}
          maxSizeBytes={15 * 1024 * 1024}
          uploadText="上传人物合照"
          replaceText="替换合照"
        />
      </Card>

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

      {/* AI 优化抽屉：同步用户在生图平台对角色形象的调整 */}
      {optimizerIndex >= 0 && breakdown.characters[optimizerIndex] && (
        <PromptOptimizerDrawer
          open
          mode="character"
          storyId={breakdown.story_id}
          characterName={breakdown.characters[optimizerIndex].name}
          characterRole={breakdown.characters[optimizerIndex].role}
          currentPrompt={breakdown.characters[optimizerIndex].appearance}
          onClose={() => setOptimizerIndex(-1)}
          onApply={(value) => void applyOptimizedAppearance(value)}
        />
      )}

      {/* 同步生图平台返回的新版角色卡，并联动更新分镜人物回顾 */}
      <CharacterSyncModal
        storyId={breakdown.story_id}
        existingNames={breakdown.characters.map((card) => card.name)}
        open={syncOpen}
        onClose={() => setSyncOpen(false)}
        onSynced={onRefresh}
      />
    </div>
  )
}
