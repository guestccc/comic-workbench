import { useEffect, useState } from 'react'
import { Button, Form, Input, Modal, Space, Tooltip } from 'antd'
import { RobotOutlined } from '@ant-design/icons'
import PromptOptimizerDrawer from './PromptOptimizerDrawer'
import {
  ART_STYLE_NAME_PLACEHOLDER,
  ART_STYLE_PLACEHOLDER,
} from '../utils/promptVariables'

export interface ArtStyleFormValues {
  name: string
  content: string
}

interface ArtStyleEditorModalProps {
  open: boolean
  /** 编辑时传入现有值；新增时为空字符串 */
  isEditing: boolean
  initialName: string
  initialContent: string
  saving: boolean
  /** 是否已配置 DeepSeek Key，决定「AI 优化」是否可用 */
  aiEnabled: boolean
  /** 从列表的「AI 优化」进入时，打开弹窗后自动展开优化抽屉 */
  autoOpenOptimizer?: boolean
  onCancel: () => void
  onSubmit: (values: ArtStyleFormValues) => void
}

/** 画风新增 / 编辑弹窗，只负责表单校验，重复名称等业务规则由父组件处理。 */
export default function ArtStyleEditorModal({
  open,
  isEditing,
  initialName,
  initialContent,
  saving,
  aiEnabled,
  autoOpenOptimizer = false,
  onCancel,
  onSubmit,
}: ArtStyleEditorModalProps) {
  const [form] = Form.useForm<ArtStyleFormValues>()
  const [optimizerOpen, setOptimizerOpen] = useState(false)
  // 监听描述输入，供 AI 优化抽屉读取当前内容
  const content = Form.useWatch('content', form) ?? ''

  // 每次打开时重置校验状态并同步当前值；依赖均为原始类型，输入过程中不会重置表单
  useEffect(() => {
    if (!open) return
    form.resetFields()
    form.setFieldsValue({ name: initialName, content: initialContent })
  }, [open, initialName, initialContent, form])

  // 从列表「AI 优化」进入时自动展开抽屉；描述为空或未配置 Key 时不展开
  useEffect(() => {
    if (open && autoOpenOptimizer && aiEnabled && initialContent.trim()) {
      setOptimizerOpen(true)
    }
  }, [open, autoOpenOptimizer, aiEnabled, initialContent])

  // 编辑弹窗关闭时一并收起优化抽屉，避免留下无归属的浮层
  useEffect(() => {
    if (!open) {
      setOptimizerOpen(false)
    }
  }, [open])

  const handleOk = async () => {
    try {
      const values = await form.validateFields()
      onSubmit({
        name: values.name.trim(),
        content: values.content.trim(),
      })
    } catch {
      // 校验失败时保留弹窗，错误信息由表单展示
    }
  }

  const aiTip = !aiEnabled
    ? '请先在「设置」页配置 DeepSeek API Key'
    : !content.trim()
      ? '请先填写画风描述'
      : undefined

  return (
    <>
      <Modal
        title={isEditing ? '编辑画风' : '新增画风'}
        open={open}
        onCancel={onCancel}
        onOk={() => void handleOk()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
      <Form form={form} layout="vertical" requiredMark={false}>
        <Form.Item
          name="name"
          label="画风名称"
          rules={[{ required: true, whitespace: true, message: '请输入画风名称' }]}
          extra={`这段名称会替换启动提示词中的 ${ART_STYLE_NAME_PLACEHOLDER} 变量`}
        >
          <Input
            maxLength={50}
            showCount
            placeholder="例如：日系赛璐璐、厚涂写实"
          />
        </Form.Item>
        <Form.Item
          name="content"
          label={
            <Space size={8}>
              <span>画风描述</span>
              <Tooltip title={aiTip}>
                <span>
                  <Button
                    type="link"
                    size="small"
                    icon={<RobotOutlined />}
                    disabled={!aiEnabled || !content.trim()}
                    onClick={() => setOptimizerOpen(true)}
                    style={{ padding: 0, height: 'auto' }}
                  >
                    AI 优化
                  </Button>
                </span>
              </Tooltip>
            </Space>
          }
          rules={[
            { required: true, whitespace: true, message: '请输入画风描述' },
          ]}
          extra={`这段描述会替换启动提示词中的 ${ART_STYLE_PLACEHOLDER} 变量`}
        >
          <Input.TextArea
            rows={5}
            maxLength={2000}
            showCount
            placeholder="描述线条、上色、光影、质感等视觉特征…"
          />
        </Form.Item>
      </Form>
      </Modal>

      <PromptOptimizerDrawer
        open={optimizerOpen}
        mode="art_style"
        currentPrompt={content}
        onClose={() => setOptimizerOpen(false)}
        onApply={(value) => form.setFieldsValue({ content: value })}
      />
    </>
  )
}
