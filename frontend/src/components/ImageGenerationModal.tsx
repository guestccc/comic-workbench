import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Empty,
  Image,
  Input,
  Modal,
  Popconfirm,
  Radio,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd'
import {
  CopyOutlined,
  DeleteOutlined,
  HistoryOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type {
  ImageGenerationItem,
  ImageGenerationPreview,
} from '../types'
import { copyText } from '../utils/clipboard'

interface ImageGenerationModalProps {
  open: boolean
  title: string
  loading: boolean
  preview: ImageGenerationPreview | null
  history: ImageGenerationItem[]
  historyBytes: number
  using?: boolean
  onUse: (generationId: string) => Promise<void> | void
  onRegenerate: () => void
  onClose: () => void
  onClearHistory: () => Promise<void> | void
}

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** 生图结果对比弹窗：左原图、右新图，默认选新图；下方可回选历史。 */
export default function ImageGenerationModal({
  open,
  title,
  loading,
  preview,
  history,
  historyBytes,
  using,
  onUse,
  onRegenerate,
  onClose,
  onClearHistory,
}: ImageGenerationModalProps) {
  const { message, modal } = App.useApp()
  const [selected, setSelected] = useState<'old' | 'new'>('new')
  const [elapsed, setElapsed] = useState(0)
  const [promptItem, setPromptItem] = useState<ImageGenerationItem | null>(null)

  useEffect(() => {
    if (!open || !loading) {
      setElapsed(0)
      return
    }
    const started = Date.now()
    setElapsed(0)
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [open, loading])

  useEffect(() => {
    if (preview) {
      setSelected('new')
    }
  }, [preview])

  const canUseNew = Boolean(preview)
  const useOld = selected === 'old' && Boolean(preview?.old_url)
  const historyTitle = useMemo(
    () => `历史记录（${history.length} 张 · ${formatBytes(historyBytes)}）`,
    [history.length, historyBytes],
  )

  const handleCancel = () => {
    if (!loading) {
      onClose()
      return
    }
    modal.confirm({
      title: '生成还在进行',
      content:
        '关闭弹窗不会取消服务端任务。生成完成后图片会进入历史记录，可以稍后回来选择。',
      okText: '关闭弹窗',
      cancelText: '继续等待',
      onOk: onClose,
    })
  }

  const handleUseNew = () => {
    if (useOld) {
      onClose()
      return
    }
    if (preview) {
      void onUse(preview.generation_id)
    }
  }

  const handleCopyPrompt = async () => {
    if (!promptItem?.prompt.trim()) return
    try {
      await copyText(promptItem.prompt)
      message.success('本次生图提示词已复制')
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  return (
    <>
    <Modal
      open={open}
      title={title}
      width={900}
      onCancel={handleCancel}
      maskClosable={false}
      footer={
        loading
          ? null
          : [
              <Button key="keep" onClick={onClose}>
                保留原图
              </Button>,
              <Button
                key="regen"
                icon={<ReloadOutlined />}
                onClick={onRegenerate}
              >
                重新生成
              </Button>,
              <Button
                key="use"
                type="primary"
                loading={using}
                disabled={!canUseNew}
                onClick={handleUseNew}
              >
                {useOld ? '使用原图' : '使用新图'}
              </Button>,
            ]
      }
    >
      <Space direction="vertical" size={14} style={{ width: '100%' }}>
        {loading && (
          <div className="image-generation-loading">
            <Spin size="large" />
            <div>
              <Typography.Text strong>正在生成，已等待 {elapsed} 秒</Typography.Text>
              <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                同步生成最长等待 600 秒；关闭弹窗不会取消服务端任务。
              </Typography.Paragraph>
            </div>
          </div>
        )}

        {!loading && preview && (
          <>
            <Radio.Group
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
              style={{ width: '100%' }}
            >
              <div className="image-generation-compare">
                <div className="image-generation-side">
                  <Radio value="old" disabled={!preview.old_url}>
                    原图
                  </Radio>
                  {preview.old_url ? (
                    <Image
                      src={preview.old_url}
                      alt="原图"
                      className="image-generation-preview"
                    />
                  ) : (
                    <div className="image-generation-placeholder">暂无原图</div>
                  )}
                </div>
                <div className="image-generation-side">
                  <Radio value="new">新生成</Radio>
                  <Image
                    src={preview.new_url}
                    alt="新生成"
                    className="image-generation-preview"
                  />
                </div>
              </div>
            </Radio.Group>
            <Typography.Text type="secondary">
              {preview.model} · {preview.size} · 耗时{' '}
              {(preview.elapsed_ms / 1000).toFixed(1)} 秒；默认使用新图。
            </Typography.Text>
          </>
        )}

        {!loading && !preview && (
          <Alert type="warning" showIcon message="本次没有拿到生成结果" />
        )}

        <div>
          <Space
            align="center"
            style={{ width: '100%', justifyContent: 'space-between' }}
          >
            <Space>
              <HistoryOutlined />
              <Typography.Text strong>{historyTitle}</Typography.Text>
            </Space>
            <Popconfirm
              title="清除这个目标的历史图片？"
              description="只删除历史文件与记录，当前正式图不会被删除。"
              okText="清除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => void onClearHistory()}
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={!history.length}
              >
                清除历史
              </Button>
            </Popconfirm>
          </Space>

          {history.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="还没有历史图片"
              style={{ margin: '12px 0' }}
            />
          ) : (
            <div className="image-generation-history">
              {history.map((item) => (
                <div className="image-generation-history-item" key={item.id}>
                  <Image
                    src={item.url}
                    alt="历史生成图"
                    width={110}
                    height={146}
                    style={{ objectFit: 'cover' }}
                  />
                  <div className="image-generation-history-meta">
                    <Typography.Text type="secondary">
                      {new Date(item.created_at).toLocaleString()}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      {formatBytes(item.file_bytes)}
                    </Typography.Text>
                    {item.is_current && <Tag color="blue">当前使用</Tag>}
                  </div>
                  <Button
                    size="small"
                    disabled={!item.prompt.trim()}
                    onClick={() => setPromptItem(item)}
                  >
                    提示词
                  </Button>
                  <Button
                    size="small"
                    loading={using}
                    onClick={() => void onUse(item.id)}
                  >
                    使用这张
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Space>
    </Modal>

    <Modal
      open={Boolean(promptItem)}
      title="本次生图提示词"
      width={760}
      onCancel={() => setPromptItem(null)}
      footer={[
        <Button key="close" onClick={() => setPromptItem(null)}>
          关闭
        </Button>,
        <Button
          key="copy"
          type="primary"
          icon={<CopyOutlined />}
          disabled={!promptItem?.prompt.trim()}
          onClick={() => void handleCopyPrompt()}
        >
          复制提示词
        </Button>,
      ]}
    >
      {promptItem?.reference_names.length ? (
        <Space wrap size={4} style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary">参考图：</Typography.Text>
          {promptItem.reference_names.map((name) => (
            <Tag key={name}>{name}</Tag>
          ))}
        </Space>
      ) : null}
      <Input.TextArea
        value={promptItem?.prompt ?? ''}
        readOnly
        autoSize={{ minRows: 12, maxRows: 24 }}
        style={{ fontFamily: 'Menlo, Consolas, monospace', fontSize: 13 }}
      />
    </Modal>
    </>
  )
}
