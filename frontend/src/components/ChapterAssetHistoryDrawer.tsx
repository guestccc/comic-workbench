import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Drawer,
  Empty,
  Image,
  List,
  Popconfirm,
  Space,
  Tag,
  Typography,
} from 'antd'
import { HistoryOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

import { api, getErrorMessage } from '../api/client'
import type { ChapterAssetArchive } from '../types'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

interface ChapterAssetHistoryDrawerProps {
  open: boolean
  storyId: number
  chapterNumber: number
  kind: 'cover' | 'guide'
  onClose: () => void
  onRestored: () => void
}

/** 章节封面 / 引导卡的成品图归档历史；恢复前会自动归档当前图。 */
export default function ChapterAssetHistoryDrawer({
  open,
  storyId,
  chapterNumber,
  kind,
  onClose,
  onRestored,
}: ChapterAssetHistoryDrawerProps) {
  const { message } = App.useApp()
  const [items, setItems] = useState<ChapterAssetArchive[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    api
      .listChapterAssetArchives(storyId, chapterNumber, kind)
      .then((data) => {
        if (!cancelled) setItems(data)
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
  }, [open, storyId, chapterNumber, kind])

  const restore = async (item: ChapterAssetArchive) => {
    try {
      await api.restoreChapterAssetArchive(
        storyId,
        chapterNumber,
        kind,
        item.filename,
      )
      message.success('已恢复这张成品图')
      onRestored()
      onClose()
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  return (
    <Drawer
      title={`成品图历史 · 第${chapterNumber}章${
        kind === 'cover' ? '封面' : '引导卡'
      }`}
      open={open}
      onClose={onClose}
      width={760}
    >
      <Typography.Paragraph type="secondary">
        每次覆盖前都会自动归档当前图；恢复只替换图片，不改提示词。
      </Typography.Paragraph>
      <List
        loading={loading}
        dataSource={items}
        locale={{ emptyText: <Empty description="还没有归档图" /> }}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Popconfirm
                key="restore"
                title="恢复这张成品图？"
                description="当前图会先自动归档，可再次恢复。"
                onConfirm={() => void restore(item)}
                okText="恢复"
                cancelText="取消"
              >
                <Button size="small" icon={<HistoryOutlined />}>
                  恢复此图
                </Button>
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              avatar={
                <Image
                  src={item.url}
                  width={72}
                  height={72}
                  style={{ objectFit: 'cover', borderRadius: 6 }}
                />
              }
              title={
                <Space wrap size={4}>
                  <Typography.Text strong>
                    {dayjs(item.created_at).format('YYYY-MM-DD HH:mm:ss')}
                  </Typography.Text>
                  <Tag>{formatBytes(item.bytes)}</Tag>
                </Space>
              }
              description={
                <Typography.Text type="secondary" ellipsis>
                  {item.filename}
                </Typography.Text>
              }
            />
          </List.Item>
        )}
      />
    </Drawer>
  )
}
