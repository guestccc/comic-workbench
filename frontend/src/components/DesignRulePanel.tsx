import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Empty,
  Form,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  CheckCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  GlobalOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons'

import { api, getErrorMessage } from '../api/client'
import type {
  DesignRule,
  DesignRuleKind,
  DesignRuleOncePreview,
  DesignRulePriority,
  DesignRuleSlot,
  DesignRuleTarget,
  DesignRuleTemplatePreview,
  Story,
  StoryBreakdown,
} from '../types'
import DesignRuleCoverageDrawer from './DesignRuleCoverageDrawer'
import DesignRuleResultDrawer from './DesignRuleResultDrawer'
import { copyText } from '../utils/clipboard'
import {
  buildDesignRuleExtractionPrompt,
  buildDesignRulePromotionPrompt,
} from '../utils/designRules'

const KIND_LABELS: Record<DesignRuleKind, string> = {
  prompt: '正面提示词',
  negative: '负面约束',
  text: '文字要求',
  review: '审片标准',
  check: '硬检查',
}

const TARGET_LABELS: Record<DesignRuleTarget, string> = {
  cover: '封面',
  body: '正文',
  guide: '引导卡',
  all: '全部',
}

const STATUS_LABELS: Record<DesignRule['status'], string> = {
  draft: '草案',
  active: '已启用',
  disabled: '已停用',
}

const PRIORITY_LABELS: Record<DesignRulePriority, string> = {
  hard: '硬性',
  soft: '建议',
}

const SLOT_LABELS: Record<DesignRuleSlot, string> = {
  scene: '【画面】',
  cover_mode: '【封面模式】',
  text_zone: '【文字区】',
  none: '不进提示词',
}

function scopeText(rule: DesignRule): string {
  if (rule.scope_type === 'global') return '全局'
  if (rule.scope_type === 'story') {
    return `故事 · ${rule.story_name ?? `#${rule.story_id ?? '?'}`}`
  }
  const story = rule.story_name ?? `#${rule.story_id ?? '?'}`
  if (rule.scope_type === 'chapter') {
    return `第${rule.chapter_numbers.join('、')}章 · ${story}`
  }
  return `第${rule.chapter_numbers.join('、')}章第${rule.page_numbers.join(
    '、',
  )}页 · ${story}`
}

function ruleBody(rule: DesignRule): string {
  if (rule.kind === 'negative') {
    return `禁用：${rule.negative_terms.join('、') || '（未填写）'}`
  }
  if (rule.kind === 'review') {
    return rule.review_check || '（未填写检查标准）'
  }
  if (rule.kind === 'check') {
    return JSON.stringify(rule.check_spec ?? {})
  }
  return rule.requirement || '（未填写规则正文）'
}

interface DesignRulePanelProps {
  feedbackId: number
  stories: Story[]
  onChanged?: () => void
}

/** 建议详情里的规则草案面板：草案、影响预览、激活、停用、回退。 */
export default function DesignRulePanel({
  feedbackId,
  stories,
  onChanged,
}: DesignRulePanelProps) {
  const { message } = App.useApp()
  const [rules, setRules] = useState<DesignRule[]>([])
  const [loading, setLoading] = useState(false)
  const [resultRule, setResultRule] = useState<DesignRule | null>(null)
  const [coverageRule, setCoverageRule] = useState<DesignRule | null>(null)
  const [templateRule, setTemplateRule] = useState<DesignRule | null>(null)
  const [templatePreview, setTemplatePreview] =
    useState<DesignRuleTemplatePreview | null>(null)
  const [templateLoading, setTemplateLoading] = useState(false)
  const [templateApplying, setTemplateApplying] = useState(false)
  const [onceForm] = Form.useForm<{
    target_type: 'cover' | 'body'
    story_id: number
    chapter_number: number
    page_number?: number
  }>()
  const [onceRule, setOnceRule] = useState<DesignRule | null>(null)
  const [oncePreview, setOncePreview] = useState<DesignRuleOncePreview | null>(
    null,
  )
  const [onceLoading, setOnceLoading] = useState(false)
  const [onceApplying, setOnceApplying] = useState(false)
  const [onceBreakdown, setOnceBreakdown] = useState<StoryBreakdown | null>(
    null,
  )
  const onceTargetType = Form.useWatch('target_type', onceForm)
  const onceStoryId = Form.useWatch('story_id', onceForm)
  const onceChapter = Form.useWatch('chapter_number', onceForm)
  const oncePage = Form.useWatch('page_number', onceForm)

  const loadRules = async () => {
    setLoading(true)
    try {
      setRules(await api.listDesignRules(feedbackId))
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadRules()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feedbackId])

  const changeStatus = async (rule: DesignRule, active: boolean) => {
    try {
      if (active) {
        await api.activateDesignRule(rule.id)
        message.success('规则已启用')
      } else {
        await api.disableDesignRule(rule.id)
        message.success('规则已停用')
      }
      await loadRules()
      onChanged?.()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const rollback = async (rule: DesignRule) => {
    try {
      await api.rollbackDesignRule(rule.id)
      message.success('规则已回退到上一版')
      await loadRules()
      onChanged?.()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const remove = async (rule: DesignRule) => {
    try {
      await api.deleteDesignRule(rule.id)
      message.success('规则已删除')
      await loadRules()
      onChanged?.()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const openTemplatePreview = async (rule: DesignRule) => {
    setTemplateRule(rule)
    setTemplatePreview(null)
    setTemplateLoading(true)
    try {
      setTemplatePreview(await api.previewDesignRuleTemplate(rule.id))
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setTemplateLoading(false)
    }
  }

  const applyTemplate = async () => {
    if (!templateRule) return
    setTemplateApplying(true)
    try {
      await api.applyDesignRuleTemplate(templateRule.id)
      message.success('规则已写入模板，规则已停用；可在模板历史里回滚')
      setTemplateRule(null)
      setTemplatePreview(null)
      await loadRules()
      onChanged?.()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setTemplateApplying(false)
    }
  }

  const openOnce = (rule: DesignRule) => {
    setOnceRule(rule)
    setOncePreview(null)
    setOnceBreakdown(null)
    onceForm.resetFields()
    onceForm.setFieldsValue({
      target_type: 'cover',
      story_id: rule.story_id ?? stories[0]?.id,
    })
  }

  useEffect(() => {
    if (!onceRule || !onceStoryId) {
      setOnceBreakdown(null)
      return
    }
    let cancelled = false
    api
      .getBreakdown(onceStoryId)
      .then((data) => {
        if (!cancelled) setOnceBreakdown(data)
      })
      .catch(() => {
        if (!cancelled) setOnceBreakdown(null)
      })
    return () => {
      cancelled = true
    }
  }, [onceRule, onceStoryId])

  useEffect(() => {
    if (!onceRule) return
    if (!onceStoryId || !onceChapter) {
      setOncePreview(null)
      return
    }
    if (onceTargetType === 'body' && !oncePage) {
      setOncePreview(null)
      return
    }
    const timer = window.setTimeout(() => {
      setOnceLoading(true)
      api
        .previewDesignRuleOnce(onceRule.id, {
          target_type: onceTargetType ?? 'cover',
          story_id: onceStoryId,
          chapter_number: onceChapter,
          page_number: onceTargetType === 'body' ? oncePage : null,
        })
        .then((data) => setOncePreview(data))
        .catch(() => setOncePreview(null))
        .finally(() => setOnceLoading(false))
    }, 300)
    return () => window.clearTimeout(timer)
  }, [onceRule, onceTargetType, onceStoryId, onceChapter, oncePage])

  const applyOnce = async () => {
    if (!onceRule) return
    let values: {
      target_type: 'cover' | 'body'
      story_id: number
      chapter_number: number
      page_number?: number
    }
    try {
      values = await onceForm.validateFields()
    } catch {
      return
    }
    setOnceApplying(true)
    try {
      await api.applyDesignRuleOnce(onceRule.id, {
        target_type: values.target_type,
        story_id: values.story_id,
        chapter_number: values.chapter_number,
        page_number:
          values.target_type === 'body' ? values.page_number : null,
      })
      message.success('已仅本次应用，规则本身未激活')
      setOnceRule(null)
      setOncePreview(null)
      await loadRules()
      onChanged?.()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setOnceApplying(false)
    }
  }

  const copyInstruction = async () => {
    try {
      await copyText(
        buildDesignRuleExtractionPrompt(
          feedbackId,
          window.location.origin,
        ),
      )
      message.success('提炼指令已复制，粘贴到 Claude Code 执行')
    } catch {
      message.error('复制失败，请手动复制')
    }
  }

  const promotableRules = rules.filter(
    (rule) =>
      rule.status === 'active' &&
      rule.scope_type !== 'global' &&
      !rule.template_applied_at,
  )

  const copyPromotion = async () => {
    if (promotableRules.length === 0) return
    try {
      await copyText(
        buildDesignRulePromotionPrompt(
          feedbackId,
          promotableRules.map((rule) => rule.id),
          window.location.origin,
        ),
      )
      message.success('推广指令已复制，粘贴到 Claude Code 执行')
    } catch {
      message.error('复制失败，请手动复制')
    }
  }

  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        <Typography.Text strong>规则草案（{rules.length}）</Typography.Text>
        <Button size="small" icon={<CopyOutlined />} onClick={() => void copyInstruction()}>
          复制提炼指令
        </Button>
        {promotableRules.length > 0 && (
          <Popconfirm
            title="把这章的规则推广到全局？"
            description={`会复制一条指令，由 Claude Code 把 ${promotableRules.length} 条规则推广到全局，并同步技能、审片和检查脚本；不会直接改数据库。`}
            onConfirm={() => void copyPromotion()}
            okText="复制指令"
            cancelText="取消"
          >
            <Button size="small" icon={<GlobalOutlined />}>
              推广到全局
            </Button>
          </Popconfirm>
        )}
      </Space>
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        你只需要提供截图或建议原文；结构化规则、作用范围和要改的提示词由 Claude Code 提炼。这里只做审核、激活和回退。章节效果确认后，用「推广到全局」复制指令，让 Claude 把这章的做法同步到全局。
      </Typography.Paragraph>
      {loading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : rules.length === 0 ? (
        <Empty description="还没有规则；点「复制提炼指令」交给 Claude Code，规则会自动写入草案" />
      ) : (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          {rules.map((rule) => (
            <Card
              key={rule.id}
              size="small"
              title={
                <Space wrap size={4}>
                  <Typography.Text strong>{rule.title}</Typography.Text>
                  <Tag
                    color={
                      rule.status === 'active'
                        ? 'green'
                        : rule.status === 'draft'
                          ? 'gold'
                          : 'default'
                    }
                  >
                    {STATUS_LABELS[rule.status]}
                  </Tag>
                  {rule.coverage_status && (
                    <Tag
                      color={
                        rule.coverage_status === 'succeeded'
                          ? 'green'
                          : rule.coverage_status === 'failed'
                            ? 'red'
                            : rule.coverage_status === 'interrupted'
                              ? 'orange'
                              : 'blue'
                      }
                    >
                      检测 {rule.coverage_status}
                      {rule.coverage_pending > 0
                        ? ` · 待确认 ${rule.coverage_pending}`
                        : ''}
                    </Tag>
                  )}
                  <Tag color="geekblue">{KIND_LABELS[rule.kind]}</Tag>
                  <Tag>{TARGET_LABELS[rule.target]}</Tag>
                  <Tag>{scopeText(rule)}</Tag>
                  <Tag color={rule.priority === 'hard' ? 'red' : 'default'}>
                    {PRIORITY_LABELS[rule.priority]}
                  </Tag>
                  {rule.check_count > 0 && (
                    <Tag
                      color={
                        rule.latest_result === 'failed'
                          ? 'red'
                          : rule.latest_result === 'passed'
                            ? 'green'
                            : 'default'
                      }
                    >
                      核验 {rule.passed_count}/{rule.check_count}
                    </Tag>
                  )}
                </Space>
              }
              extra={
                <Space wrap size={4}>
                  {rule.template_applied_at ? (
                    <Tag color="purple">已写入模板</Tag>
                  ) : rule.status === 'active' ? (
                    <Button
                      size="small"
                      icon={<StopOutlined />}
                      onClick={() => void changeStatus(rule, false)}
                    >
                      停用
                    </Button>
                  ) : (
                    <Button
                      size="small"
                      type="primary"
                      ghost
                      icon={<CheckCircleOutlined />}
                      onClick={() => void changeStatus(rule, true)}
                    >
                      激活
                    </Button>
                  )}
                  <Button
                    size="small"
                    onClick={() => setCoverageRule(rule)}
                  >
                    检测落实
                  </Button>
                  <Button
                    size="small"
                    onClick={() => setResultRule(rule)}
                  >
                    核验{rule.check_count > 0 ? ` ${rule.passed_count}/${rule.check_count}` : ''}
                  </Button>
                  {(rule.status === 'draft' || rule.status === 'disabled') &&
                    (rule.kind === 'prompt' ||
                      rule.kind === 'negative' ||
                      rule.kind === 'text') &&
                    !rule.template_applied_at && (
                      <Button size="small" onClick={() => openOnce(rule)}>
                        仅本次
                      </Button>
                    )}
                  {rule.status === 'active' &&
                    rule.scope_type === 'global' &&
                    (rule.kind === 'prompt' ||
                      rule.kind === 'negative' ||
                      rule.kind === 'text') &&
                    rule.target !== 'guide' &&
                    !rule.template_applied_at && (
                      <Button
                        size="small"
                        onClick={() => void openTemplatePreview(rule)}
                      >
                        写入模板
                      </Button>
                    )}
                  {rule.version > 1 && (
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      onClick={() => void rollback(rule)}
                    >
                      回退
                    </Button>
                  )}
                  <Popconfirm
                    title="删除这条规则？"
                    onConfirm={() => void remove(rule)}
                    okText="删除"
                    cancelText="取消"
                  >
                    <Button size="small" danger icon={<DeleteOutlined />}>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              }
            >
              <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 4 }}>
                {ruleBody(rule)}
              </Typography.Paragraph>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                v{rule.version} · {rule.created_by === 'claude' ? 'Claude 提炼' : '手动创建'}
                {rule.slot !== 'none' ? ` · ${SLOT_LABELS[rule.slot]}` : ''}
              </Typography.Text>
            </Card>
          ))}
        </Space>
      )}

      <Modal
        title={`仅本次应用 · ${onceRule?.title ?? ''}`}
        open={Boolean(onceRule)}
        onCancel={() => {
          setOnceRule(null)
          setOncePreview(null)
        }}
        onOk={() => void applyOnce()}
        confirmLoading={onceApplying}
        okText="应用一次"
        cancelText="取消"
        okButtonProps={{ disabled: !oncePreview }}
        width={820}
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="只改这一张的提示词，不激活规则；会留下提示词快照和一条「仅本次应用」核验记录。"
        />
        <Form form={onceForm} layout="vertical" preserve={false}>
          <Space size="middle" wrap>
            <Form.Item name="target_type" label="目标" style={{ width: 140 }}>
              <Select
                options={[
                  { value: 'cover', label: '章节封面' },
                  { value: 'body', label: '正文页' },
                ]}
                onChange={() =>
                  onceForm.setFieldValue('page_number', undefined)
                }
              />
            </Form.Item>
            <Form.Item
              name="story_id"
              label="故事"
              style={{ width: 220 }}
              rules={[{ required: true, message: '请选择故事' }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                options={stories.map((story) => ({
                  value: story.id,
                  label: story.name || `未命名故事 #${story.id}`,
                }))}
                onChange={() =>
                  onceForm.setFieldValue('chapter_number', undefined)
                }
              />
            </Form.Item>
            <Form.Item
              name="chapter_number"
              label="章号"
              style={{ width: 120 }}
              rules={[{ required: true, message: '请填写章号' }]}
            >
              <InputNumber min={1} max={50} style={{ width: '100%' }} />
            </Form.Item>
            {onceTargetType === 'body' && (
              <Form.Item
                name="page_number"
                label="章内页码"
                style={{ width: 120 }}
                rules={[{ required: true, message: '请填写页码' }]}
              >
                <InputNumber min={1} max={200} style={{ width: '100%' }} />
              </Form.Item>
            )}
          </Space>
        </Form>
        {onceLoading ? (
          <Skeleton active paragraph={{ rows: 3 }} />
        ) : oncePreview ? (
          <Card size="small" title="提示词预览">
            <Typography.Text type="secondary">插入：</Typography.Text>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                background: '#fafafa',
                padding: 8,
                fontSize: 12,
              }}
            >
              {oncePreview.inserted_block}
            </pre>
            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Typography.Text type="secondary">应用前</Typography.Text>
                <pre
                  style={{
                    whiteSpace: 'pre-wrap',
                    maxHeight: 240,
                    overflow: 'auto',
                    background: '#fafafa',
                    padding: 8,
                    fontSize: 12,
                  }}
                >
                  {oncePreview.before || '（空）'}
                </pre>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Typography.Text type="secondary">应用后</Typography.Text>
                <pre
                  style={{
                    whiteSpace: 'pre-wrap',
                    maxHeight: 240,
                    overflow: 'auto',
                    background: '#fafafa',
                    padding: 8,
                    fontSize: 12,
                  }}
                >
                  {oncePreview.after}
                </pre>
              </div>
            </div>
          </Card>
        ) : (
          <Typography.Text type="secondary">
            选择目标后显示提示词预览
          </Typography.Text>
        )}
      </Modal>

      <Modal
        title="写入全局模板"
        open={Boolean(templateRule)}
        onCancel={() => {
          setTemplateRule(null)
          setTemplatePreview(null)
        }}
        onOk={() => void applyTemplate()}
        confirmLoading={templateApplying}
        okText="确认写入"
        cancelText="取消"
        okButtonProps={{ disabled: !templatePreview }}
        width={920}
        destroyOnHidden
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="写入后会修改全局模板，规则自动停用；出问题可在「提示词模板 → 历史版本」回滚。"
        />
        {templateLoading ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : (
          (templatePreview?.items ?? []).map((item) => (
            <Card
              key={item.template_type}
              size="small"
              title={
                item.template_type === 'body' ? '正文模板' : '封面模板'
              }
              style={{ marginBottom: 12 }}
            >
              <Typography.Text type="secondary">将插入：</Typography.Text>
              <pre
                style={{
                  whiteSpace: 'pre-wrap',
                  background: '#fafafa',
                  padding: 8,
                  fontSize: 12,
                }}
              >
                {item.inserted_block}
              </pre>
              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Typography.Text type="secondary">写入前</Typography.Text>
                  <pre
                    style={{
                      whiteSpace: 'pre-wrap',
                      maxHeight: 260,
                      overflow: 'auto',
                      background: '#fafafa',
                      padding: 8,
                      fontSize: 12,
                    }}
                  >
                    {item.before}
                  </pre>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Typography.Text type="secondary">写入后</Typography.Text>
                  <pre
                    style={{
                      whiteSpace: 'pre-wrap',
                      maxHeight: 260,
                      overflow: 'auto',
                      background: '#fafafa',
                      padding: 8,
                      fontSize: 12,
                    }}
                  >
                    {item.after}
                  </pre>
                </div>
              </div>
            </Card>
          ))
        )}
      </Modal>

      <DesignRuleResultDrawer
        open={Boolean(resultRule)}
        ruleId={resultRule?.id ?? 0}
        ruleTitle={resultRule?.title ?? ''}
        onClose={() => setResultRule(null)}
      />

      <DesignRuleCoverageDrawer
        open={Boolean(coverageRule)}
        rule={coverageRule}
        onClose={() => setCoverageRule(null)}
      />
    </div>
  )
}
