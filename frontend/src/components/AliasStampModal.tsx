import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Input,
  Modal,
  Select,
  Space,
  Typography,
} from 'antd'
import { api, getErrorMessage } from '../api/client'
import type { AliasStampResult } from '../types'

export interface AliasChapterOption {
  value: number
  label: string
  count: number
}

interface AliasStampModalProps {
  open: boolean
  storyId: number
  defaultAlias: string
  /** 章节多选；不传或空数组表示整个故事 */
  chapterOptions?: AliasChapterOption[]
  /** 打开时默认选中的章节；空数组表示整个故事 */
  defaultChapterNumbers?: number[]
  /** 没有章节选项时，用于提示的图片数量 */
  imageCount?: number
  onClose: () => void
  onDone: () => Promise<void> | void
}

const ALIAS_PATTERN = /^[一-鿿]{6,8}$/

/**
 * 批量给图片底部加【别名】。
 *
 * 后端原地覆盖封面/正文/引导卡，首次处理前自动备份原图；
 * 这里负责选择章节范围、输入别名、确认覆盖和调用恢复。
 */
export default function AliasStampModal({
  open,
  storyId,
  defaultAlias,
  chapterOptions = [],
  defaultChapterNumbers = [],
  imageCount = 0,
  onClose,
  onDone,
}: AliasStampModalProps) {
  const { message, modal } = App.useApp()
  const [alias, setAlias] = useState(defaultAlias)
  const [selectedChapters, setSelectedChapters] = useState<number[]>(
    defaultChapterNumbers,
  )
  const [busy, setBusy] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [result, setResult] = useState<AliasStampResult | null>(null)

  useEffect(() => {
    if (open) {
      setAlias(defaultAlias)
      setSelectedChapters(defaultChapterNumbers)
      setResult(null)
    }
    // defaultChapterNumbers 由打开按钮决定；只在打开时同步一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultAlias])

  const hasChapters = chapterOptions.length > 0
  const selectedOptions = hasChapters
    ? selectedChapters.length > 0
      ? chapterOptions.filter((item) =>
          selectedChapters.includes(item.value),
        )
      : chapterOptions
    : []
  const effectiveCount = hasChapters
    ? selectedOptions.reduce((sum, item) => sum + item.count, 0)
    : imageCount
  const scopeText = !hasChapters
    ? '整个故事'
    : selectedChapters.length === 0
      ? '整个故事'
      : selectedChapters.length === 1
        ? `第 ${selectedChapters[0]} 章`
        : `第 ${selectedChapters.join('、')} 章`

  const handleStamp = async () => {
    const value = alias.trim()
    if (!ALIAS_PATTERN.test(value)) {
      message.warning('别名必须是 6–8 个汉字，不能包含字母、数字、标点或空格')
      return
    }
    setBusy(true)
    try {
      const scope =
        selectedChapters.length === 1
          ? { chapter_number: selectedChapters[0] }
          : selectedChapters.length > 1
            ? { chapter_numbers: selectedChapters }
            : {}
      const data = await api.stampStoryAlias(storyId, {
        alias: value,
        ...scope,
      })
      setResult(data)
      message.success(`已处理 ${data.stamped} 张图片，失败 ${data.failed} 张`)
      await onDone()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const handleRestore = () => {
    modal.confirm({
      title: `恢复${scopeText}的原图？`,
      content: `会把${scopeText}的封面、正文页、引导卡从 alias-backups 备份恢复；没有备份的图片会跳过。`,
      okText: '恢复原图',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setRestoring(true)
        try {
          const scope =
            selectedChapters.length === 1
              ? { chapter_number: selectedChapters[0] }
              : selectedChapters.length > 1
                ? { chapter_numbers: selectedChapters }
                : {}
          const data = await api.restoreStoryAlias(storyId, scope)
          message.success(
            `已恢复 ${data.restored} 张图片，失败 ${data.failed} 张`,
          )
          setResult(null)
          await onDone()
        } catch (error) {
          message.error(getErrorMessage(error))
        } finally {
          setRestoring(false)
        }
      },
    })
  }

  return (
    <Modal
      open={open}
      title="批量给图片加别名"
      onCancel={onClose}
      width={620}
      footer={[
        <Button key="close" onClick={onClose}>
          关闭
        </Button>,
        <Button
          key="restore"
          danger
          loading={restoring}
          onClick={handleRestore}
        >
          恢复原图
        </Button>,
        <Button
          key="stamp"
          type="primary"
          loading={busy}
          disabled={effectiveCount === 0}
          onClick={() => void handleStamp()}
        >
          开始加别名
        </Button>,
      ]}
    >
      <Space direction="vertical" size={14} style={{ width: '100%' }}>
        <Alert
          type="warning"
          showIcon
          message="会原地覆盖图片"
          description={`处理${scopeText}的封面、正文页、引导卡，在底部居中写入【别名】。首次处理前自动备份原图到 alias-backups，可随时点「恢复原图」。重复执行不会叠字；如果某张图重新上传过，会以新图为准重新备份。`}
        />
        {hasChapters && (
          <div>
            <Typography.Text strong>范围</Typography.Text>
            <Select
              mode="multiple"
              allowClear
              value={selectedChapters}
              onChange={setSelectedChapters}
              placeholder="不选=整个故事；可多选章节"
              style={{ width: '100%', marginTop: 6 }}
              options={chapterOptions.map((item) => ({
                value: item.value,
                label: `${item.label}（${item.count} 张）`,
              }))}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              不选章节就是整个故事；选多个章节只处理选中的章节。
            </Typography.Text>
          </div>
        )}
        <div>
          <Typography.Text strong>别名</Typography.Text>
          <Input
            value={alias}
            onChange={(event) => setAlias(event.target.value)}
            maxLength={8}
            showCount
            placeholder="6–8 个汉字，例如：提笔写尽相思"
            style={{ marginTop: 6 }}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            图片上显示为【{alias.trim() || '别名'}】，同一故事的图片使用同一个别名。
          </Typography.Text>
        </div>
        <Typography.Text type="secondary">
          当前范围内有 {effectiveCount} 张图片可处理；角色资产图不会加字。
        </Typography.Text>
        {result && (
          <Alert
            type={result.failed > 0 ? 'warning' : 'success'}
            showIcon
            message={`本次处理 ${result.stamped} 张，失败 ${result.failed} 张`}
            description={
              result.failed > 0
                ? result.items
                    .filter((item) => !item.ok)
                    .slice(0, 5)
                    .map(
                      (item) =>
                        `${item.target === 'page' ? `第${item.page_number}页` : item.target === 'cover' ? `第${item.chapter_number}章封面` : `第${item.chapter_number}章引导卡`}：${item.error ?? '失败'}`,
                    )
                    .join('；')
                : `备份目录：${result.backup_dir}`
            }
          />
        )}
      </Space>
    </Modal>
  )
}
