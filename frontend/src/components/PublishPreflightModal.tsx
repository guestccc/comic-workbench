import { useEffect, useState, type ReactNode } from 'react'
import {
  Alert,
  Button,
  Checkbox,
  Divider,
  Modal,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleFilled,
} from '@ant-design/icons'
import {
  formatPublishTime,
  formatXhsDeclaration,
  PUBLISH_MODE_META,
  resolvePublishMode,
} from '../utils/publishing'
import PlatformLabel from './PlatformIcon'
import type {
  PreflightAction,
  PreflightCheck,
  PreflightGroup,
  PublishPreview,
} from '../types'

interface PublishPreflightModalProps {
  open: boolean
  chapterNumber: number
  preview: PublishPreview | null
  submitting: boolean
  /** 正在执行的修复动作，用于按钮 loading 与防重复点击 */
  actionPending: PreflightAction | null
  onClose: () => void
  onConfirm: () => void
  onAction: (action: PreflightAction) => void
}

const GROUP_ORDER: PreflightGroup[] = [
  'content',
  'alias',
  'images',
  'account',
  'platform',
]

const GROUP_LABELS: Record<PreflightGroup, string> = {
  content: '文案',
  alias: '别名',
  images: '图片',
  account: '账号',
  platform: '平台与发布方式',
}

const STATUS_ICONS: Record<PreflightCheck['status'], ReactNode> = {
  pass: <CheckCircleFilled style={{ color: '#52c41a' }} />,
  warning: <ExclamationCircleFilled style={{ color: '#faad14' }} />,
  error: <CloseCircleFilled style={{ color: '#ff4d4f' }} />,
}

const STATUS_TAG_COLORS: Record<PreflightCheck['status'], string> = {
  pass: 'success',
  warning: 'warning',
  error: 'error',
}

/**
 * 发布前检查弹窗。
 *
 * 检查结论全部来自后端 `preview.checks`，这里只负责分组展示与确认；
 * 有 error 时禁止创建，只有 warning 时必须勾选确认。
 */
export default function PublishPreflightModal({
  open,
  chapterNumber,
  preview,
  submitting,
  actionPending,
  onClose,
  onConfirm,
  onAction,
}: PublishPreflightModalProps) {
  const [warningsConfirmed, setWarningsConfirmed] = useState(false)

  // 预览哈希变化说明内容已重新计算，旧的确认勾选必须失效
  useEffect(() => {
    setWarningsConfirmed(false)
  }, [preview?.payload_hash])

  const checks = preview?.checks ?? []
  const errors = checks.filter((check) => check.status === 'error')
  const warnings = checks.filter((check) => check.status === 'warning')
  const passes = checks.filter((check) => check.status === 'pass')
  const immediate =
    preview != null && resolvePublishMode(preview.publish_mode) === 'immediate'
  const confirmDisabled =
    preview == null ||
    errors.length > 0 ||
    (warnings.length > 0 && !warningsConfirmed)

  return (
    <Modal
      open={open}
      title={
        preview ? (
          <>
            发布前检查 · 第 {chapterNumber} 章 →{' '}
            <PlatformLabel platform={preview.platform} />
          </>
        ) : (
          '发布前检查'
        )
      }
      width={760}
      onCancel={onClose}
      maskClosable={false}
      footer={
        <div className="preflight-footer">
          <div className="preflight-confirm">
            {errors.length > 0 ? (
              <Typography.Text type="danger">
                有 {errors.length} 项阻塞问题，修正后才能创建任务
              </Typography.Text>
            ) : warnings.length > 0 ? (
              <Checkbox
                checked={warningsConfirmed}
                onChange={(event) =>
                  setWarningsConfirmed(event.target.checked)
                }
              >
                我已确认以上 {warnings.length} 项提醒
              </Checkbox>
            ) : (
              <Typography.Text type="secondary">
                全部检查通过，可以创建任务
              </Typography.Text>
            )}
          </div>
          <Space>
            <Button onClick={onClose}>取消</Button>
            <Button
              type="primary"
              danger={immediate}
              loading={submitting}
              disabled={confirmDisabled}
              onClick={onConfirm}
            >
              {immediate ? '确认立即发布' : '确认创建任务'}
            </Button>
          </Space>
        </div>
      }
    >
      {preview && (
        <div className="preflight">
          <div className="preflight-summary">
            <Typography.Text strong>{preview.title}</Typography.Text>
            <Typography.Text type="secondary">
              {preview.image_count} 张图 ·{' '}
              {preview.tags.map((tag) => `#${tag}`).join(' ') || '无标签'} ·{' '}
              {preview.account.display_name}
            </Typography.Text>
            <Typography.Text type="secondary">
              {PUBLISH_MODE_META[resolvePublishMode(preview.publish_mode)].text}
              {resolvePublishMode(preview.publish_mode) === 'scheduled'
                ? ` · ${formatPublishTime(preview.schedule_at)}`
                : ''}
            </Typography.Text>
            {preview.platform === 'xiaohongshu' && (
              <Typography.Text type="secondary">
                内容声明：
                {formatXhsDeclaration(preview.declaration, preview.repost_source)}
              </Typography.Text>
            )}
          </div>

          <Space size={8} wrap className="preflight-stats">
            <Tag color="success">通过 {passes.length}</Tag>
            <Tag color="warning">提醒 {warnings.length}</Tag>
            <Tag color="error">阻塞 {errors.length}</Tag>
          </Space>

          {immediate && (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 12 }}
              message="立即发布不可撤回"
              description="创建后马上上传并提交平台，成功即对读者可见。"
            />
          )}
          {errors.length === 0 && warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="没有阻塞问题，但有需要确认的提醒"
              description="逐项确认后勾选底部复选框，才能创建任务。"
            />
          )}

          {GROUP_ORDER.map((group) => {
            const groupChecks = checks.filter(
              (check) => check.group === group,
            )
            if (groupChecks.length === 0) return null
            return (
              <div key={group} className="preflight-group">
                <Divider titlePlacement="start" plain>
                  {GROUP_LABELS[group]}
                </Divider>
                {groupChecks.map((check) => (
                  <PreflightCheckRow
                    key={check.key}
                    check={check}
                    actionPending={actionPending}
                    onAction={onAction}
                  />
                ))}
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}

function PreflightCheckRow({
  check,
  actionPending,
  onAction,
}: {
  check: PreflightCheck
  actionPending: PreflightAction | null
  onAction: (action: PreflightAction) => void
}) {
  const action = check.action
  return (
    <div className={`preflight-check preflight-check-${check.status}`}>
      <span className="preflight-check-icon">{STATUS_ICONS[check.status]}</span>
      <div className="preflight-check-body">
        <div className="preflight-check-head">
          <Typography.Text strong>{check.label}</Typography.Text>
          {action && (
            <Button
              size="small"
              type="link"
              loading={actionPending === action}
              disabled={actionPending != null && actionPending !== action}
              onClick={() => onAction(action)}
            >
              {check.action_label ?? '去处理'}
            </Button>
          )}
        </div>
        <Typography.Text
          type={
            check.status === 'error'
              ? 'danger'
              : check.status === 'warning'
                ? 'warning'
                : 'secondary'
          }
          className="preflight-check-message"
        >
          {check.message}
        </Typography.Text>
        {check.items.length > 0 && (
          <div className="preflight-check-items">
            {check.items.map((item) => (
              <Tag
                key={item.label}
                color={STATUS_TAG_COLORS[item.status]}
                bordered={false}
              >
                {item.label}
              </Tag>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
