import { Button, List, Popconfirm, Space, Tag, Tooltip, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, RobotOutlined } from '@ant-design/icons'
import type { ArtStyle } from '../types'

interface ArtStyleListProps {
  styles: ArtStyle[]
  activeId: string | null
  saving: boolean
  /** 是否已配置 DeepSeek Key，决定「AI 优化」是否可用 */
  aiEnabled: boolean
  onEdit: (style: ArtStyle) => void
  /** 打开编辑弹窗并直接展开 AI 优化抽屉 */
  onOptimize: (style: ArtStyle) => void
  onDelete: (style: ArtStyle) => void
}

/** 画风条目列表：展示名称与描述，提供编辑 / 删除操作。 */
export default function ArtStyleList({
  styles,
  activeId,
  saving,
  aiEnabled,
  onEdit,
  onOptimize,
  onDelete,
}: ArtStyleListProps) {
  if (styles.length === 0) {
    return (
      <Typography.Text type="secondary">
        还没有画风，点击右上角「新增画风」添加。
      </Typography.Text>
    )
  }

  return (
    <List
      size="small"
      bordered
      dataSource={styles}
      renderItem={(style) => (
        <List.Item
          actions={[
            <Tooltip
              key="optimize"
              title={
                aiEnabled
                  ? undefined
                  : '请先在「设置」页配置 DeepSeek API Key'
              }
            >
              <span>
                <Button
                  type="link"
                  size="small"
                  icon={<RobotOutlined />}
                  onClick={() => onOptimize(style)}
                  disabled={saving || !aiEnabled}
                >
                  AI 优化
                </Button>
              </span>
            </Tooltip>,
            <Button
              key="edit"
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => onEdit(style)}
              disabled={saving}
            >
              编辑
            </Button>,
            <Popconfirm
              key="delete"
              title="删除该画风？"
              description={
                activeId === style.id
                  ? '它当前正在被选用，删除后会取消选用。'
                  : undefined
              }
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => onDelete(style)}
            >
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={saving}
              >
                删除
              </Button>
            </Popconfirm>,
          ]}
        >
          <List.Item.Meta
            title={
              <Space>
                {style.name}
                {activeId === style.id && <Tag color="blue">当前</Tag>}
              </Space>
            }
            description={
              <Typography.Paragraph
                type="secondary"
                ellipsis={{ rows: 2 }}
                style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
              >
                {style.content}
              </Typography.Paragraph>
            }
          />
        </List.Item>
      )}
    />
  )
}
