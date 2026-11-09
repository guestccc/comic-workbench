import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Input,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import { api, getErrorMessage } from '../api/client'
import type {
  SensitiveApplyItem,
  SensitiveApplyResult,
  SensitiveScanResult,
} from '../types'

interface SensitiveWordModalProps {
  open: boolean
  text: string
  onClose: () => void
  onApply: (result: SensitiveApplyResult) => void | Promise<void>
}

/** 扫描原文 → 逐词确认替换词 → 预览 → 应用；只改传入的文本，不直接落库。 */
export default function SensitiveWordModal({
  open,
  text,
  onClose,
  onApply,
}: SensitiveWordModalProps) {
  const { message } = App.useApp()
  const [scan, setScan] = useState<SensitiveScanResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [replacements, setReplacements] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setScan(null)
    setSelected({})
    setReplacements({})
    void api
      .scanSensitiveWords(text)
      .then((data) => {
        if (cancelled) return
        setScan(data)
        const nextSelected: Record<string, boolean> = {}
        const nextReplacements: Record<string, string> = {}
        for (const match of data.matches) {
          nextSelected[match.word] = true
          nextReplacements[match.word] = match.replacement
        }
        setSelected(nextSelected)
        setReplacements(nextReplacements)
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
  }, [open, text, message])

  const selectedItems = useMemo<SensitiveApplyItem[]>(() => {
    if (!scan) return []
    const seen = new Set<string>()
    const items: SensitiveApplyItem[] = []
    for (const match of scan.matches) {
      if (!selected[match.word] || seen.has(match.word)) continue
      seen.add(match.word)
      items.push({
        word: match.word,
        replacement: replacements[match.word] ?? '',
      })
    }
    return items
  }, [scan, selected, replacements])

  const preview = useMemo(() => {
    if (!scan) return text
    const selectedWords = new Set(selectedItems.map((item) => item.word))
    const replacementMap = new Map(
      selectedItems.map((item) => [item.word, item.replacement]),
    )
    const matches = scan.matches.filter((match) => selectedWords.has(match.word))
    let result = text
    for (let index = matches.length - 1; index >= 0; index -= 1) {
      const match = matches[index]
      result =
        result.slice(0, match.start) +
        (replacementMap.get(match.word) ?? '') +
        result.slice(match.end)
    }
    return result
  }, [text, scan, selectedItems])

  const handleApply = async () => {
    if (selectedItems.length === 0) {
      message.warning('请至少选择一个要替换的词')
      return
    }
    setApplying(true)
    try {
      const result = await api.applySensitiveWords(text, selectedItems)
      await onApply(result)
      message.success(`已替换 ${result.items.reduce((sum, item) => sum + item.count, 0)} 处`)
      onClose()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setApplying(false)
    }
  }

  const rows = scan
    ? Object.entries(scan.counts).map(([word, count]) => {
        const match = scan.matches.find((item) => item.word === word)
        return {
          word,
          count,
          category: match?.category ?? '',
          replacement: replacements[word] ?? '',
        }
      })
    : []

  return (
    <Modal
      open={open}
      title="检测敏感词"
      width={760}
      onCancel={onClose}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="apply"
          type="primary"
          loading={applying}
          disabled={loading || selectedItems.length === 0}
          onClick={() => void handleApply()}
        >
          应用替换
        </Button>,
      ]}
    >
      <Space direction="vertical" size={14} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="只改当前编辑框，不会直接写数据库"
          description="应用后仍需保存故事；已拆解过的故事改原文后，优化文和对照表需要重新生成。"
        />

        {loading ? (
          <Typography.Text type="secondary">正在扫描…</Typography.Text>
        ) : !scan || scan.total === 0 ? (
          <Alert
            type="success"
            showIcon
            message="没有命中词库中的敏感词"
            description="可以到「设置 → 敏感词库」添加词条后重试。"
          />
        ) : (
          <>
            <Typography.Text>
              命中 <Tag color="red">{scan.total}</Tag> 处，涉及{' '}
              <Tag>{rows.length}</Tag> 个词。取消勾选的词不会替换。
            </Typography.Text>
            <Table
              size="small"
              rowKey="word"
              pagination={false}
              dataSource={rows}
              columns={[
                {
                  title: '处理',
                  width: 70,
                  render: (_, row) => (
                    <Switch
                      size="small"
                      checked={Boolean(selected[row.word])}
                      onChange={(checked) =>
                        setSelected((prev) => ({
                          ...prev,
                          [row.word]: checked,
                        }))
                      }
                    />
                  ),
                },
                {
                  title: '敏感词',
                  dataIndex: 'word',
                  width: 140,
                  render: (word: string, row) => (
                    <Space size={6}>
                      <Typography.Text strong delete={!selected[row.word]}>
                        {word}
                      </Typography.Text>
                      {row.category ? <Tag>{row.category}</Tag> : null}
                    </Space>
                  ),
                },
                {
                  title: '次数',
                  dataIndex: 'count',
                  width: 70,
                },
                {
                  title: '替换为',
                  dataIndex: 'replacement',
                  render: (value: string, row) => (
                    <Input
                      value={value}
                      placeholder="留空表示删除"
                      onChange={(event) =>
                        setReplacements((prev) => ({
                          ...prev,
                          [row.word]: event.target.value,
                        }))
                      }
                    />
                  ),
                },
              ]}
            />
            <div>
              <Typography.Text strong>替换后预览</Typography.Text>
              <Input.TextArea
                value={preview}
                readOnly
                autoSize={{ minRows: 4, maxRows: 10 }}
                style={{ marginTop: 6 }}
              />
            </div>
          </>
        )}
      </Space>
    </Modal>
  )
}
