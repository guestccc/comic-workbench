import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Drawer,
  Empty,
  InputNumber,
  List,
  Modal,
  Space,
  Tag,
  Typography,
} from 'antd'
import { CopyOutlined, ThunderboltOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

import { api, getErrorMessage } from '../api/client'
import type { DesignRuleResult } from '../types'
import { copyText } from '../utils/clipboard'
import {
  buildDesignRulePipelinePrompt,
  buildDesignRuleReworkPrompt,
} from '../utils/designRules'

const TARGET_LABELS: Record<DesignRuleResult['target_type'], string> = {
  cover: '封面',
  body: '正文',
  guide: '引导卡',
  other: '其他',
}

interface DesignRuleResultDrawerProps {
  open: boolean
  ruleId: number
  ruleTitle: string
  onClose: () => void
}

/** 规则核验时间线：看每次通过/失败，并为失败项复制返工指令。 */
export default function DesignRuleResultDrawer({
  open,
  ruleId,
  ruleTitle,
  onClose,
}: DesignRuleResultDrawerProps) {
  const { message } = App.useApp()
  const [results, setResults] = useState<DesignRuleResult[]>([])
  const [loading, setLoading] = useState(false)
  const [pipelineResult, setPipelineResult] = useState<DesignRuleResult | null>(
    null,
  )
  const [pipelineMax, setPipelineMax] = useState(2)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    api
      .listDesignRuleResults(ruleId)
      .then((items) => {
        if (!cancelled) setResults(items)
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
  }, [open, ruleId])

  const openPipeline = (result: DesignRuleResult) => {
    if (result.target_type !== 'cover' || result.chapter_number == null) {
      message.warning('自动流水线目前只支持章节封面')
      return
    }
    setPipelineMax(2)
    setPipelineResult(result)
  }

  const confirmPipeline = async () => {
    if (!pipelineResult || pipelineResult.chapter_number == null) return
    try {
      await copyText(
        buildDesignRulePipelinePrompt(
          ruleId,
          pipelineResult.id,
          pipelineResult.story_id,
          pipelineResult.chapter_number,
          window.location.origin,
          pipelineMax,
        ),
      )
      setPipelineResult(null)
      message.success('自动流水线指令已复制')
    } catch {
      message.error('复制失败，请手动复制')
    }
  }

  const copyRework = async (result: DesignRuleResult) => {
    try {
      await copyText(
        buildDesignRuleReworkPrompt(
          ruleId,
          result.id,
          window.location.origin,
        ),
      )
      message.success('返工指令已复制，粘贴到 Claude Code 执行')
    } catch {
      message.error('复制失败，请手动复制')
    }
  }

  return (
    <Drawer
      title={`核验记录 · ${ruleTitle}`}
      open={open}
      onClose={onClose}
      width={720}
    >
      <Typography.Paragraph type="secondary">
        核验可以由提示词硬检查或生成图审片写入；失败项可复制成 Claude Code 返工指令。
      </Typography.Paragraph>
      <List
        loading={loading}
        dataSource={results}
        locale={{ emptyText: <Empty description="还没有核验记录" /> }}
        renderItem={(result) => (
          <List.Item
            actions={
              result.result === 'failed'
                ? [
                    <Button
                      key="rework"
                      size="small"
                      icon={<CopyOutlined />}
                      onClick={() => void copyRework(result)}
                    >
                      复制返工指令
                    </Button>,
                    result.target_type === 'cover' &&
                    result.chapter_number != null ? (
                      <Button
                        key="pipeline"
                        size="small"
                        icon={<ThunderboltOutlined />}
                        onClick={() => openPipeline(result)}
                      >
                        自动流水线
                      </Button>
                    ) : null,
                  ]
                : undefined
            }
          >
            <List.Item.Meta
              title={
                <Space wrap size={4}>
                  <Tag
                    color={
                      result.result === 'passed'
                        ? 'green'
                        : result.result === 'failed'
                          ? 'red'
                          : 'default'
                    }
                  >
                    {result.result === 'passed'
                      ? '通过'
                      : result.result === 'failed'
                        ? '失败'
                        : '未知'}
                  </Tag>
                  <Tag>{TARGET_LABELS[result.target_type]}</Tag>
                  {result.chapter_number != null && (
                    <Tag>第{result.chapter_number}章</Tag>
                  )}
                  {result.page_number != null && (
                    <Tag>第{result.page_number}页</Tag>
                  )}
                  <Typography.Text type="secondary">
                    {dayjs(result.created_at).format('YYYY-MM-DD HH:mm:ss')}
                  </Typography.Text>
                  <Tag>{result.reviewer === 'claude' ? 'Claude' : '人工'}</Tag>
                </Space>
              }
              description={result.message || '（无说明）'}
            />
            {result.image_url && (
              <Typography.Link href={result.image_url} target="_blank">
                查看核验图片
              </Typography.Link>
            )}
          </List.Item>
        )}
      />
      <Modal
        title="自动流水线 · 生图张数"
        open={Boolean(pipelineResult)}
        onCancel={() => setPipelineResult(null)}
        onOk={() => void confirmPipeline()}
        okText="复制指令"
        cancelText="取消"
        width={460}
      >
        <Typography.Paragraph type="secondary">
          这条指令会让 Claude Code 串起 render → 生图 → 审片 → 写核验。每张图都会消耗生图额度，到达上限必须停止。
        </Typography.Paragraph>
        <Typography.Text strong>本次最多生成</Typography.Text>
        <InputNumber
          min={1}
          max={3}
          value={pipelineMax}
          onChange={(value) => setPipelineMax(value ?? 2)}
          style={{ marginLeft: 8, width: 80 }}
        />
        <Typography.Text strong style={{ marginLeft: 8 }}>
          张
        </Typography.Text>
      </Modal>

    </Drawer>
  )
}
