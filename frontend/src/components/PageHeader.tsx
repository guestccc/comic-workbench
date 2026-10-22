import type { ReactNode } from 'react'
import { Typography } from 'antd'

interface PageHeaderProps {
  title: string
  description?: string
  extra?: ReactNode
}

/** 页面统一标题区：标题 + 说明 + 右侧操作。 */
export default function PageHeader({ title, description, extra }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {title}
        </Typography.Title>
        {description && (
          <Typography.Text type="secondary">{description}</Typography.Text>
        )}
      </div>
      {extra && <div className="page-header-extra">{extra}</div>}
    </div>
  )
}
