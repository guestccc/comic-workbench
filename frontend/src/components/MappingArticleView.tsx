import { Tooltip } from 'antd'
import type { StoryboardMappingItem } from '../types'

interface MappingArticleViewProps {
  mapping: StoryboardMappingItem[]
  /** 已勾选要生成脚本的对照段号；不传表示全部选中 */
  selectedPages?: number[]
}

/**
 * 优化文连续阅读：按对照表顺序拼接原文，每段前标出对照段号。
 *
 * 鼠标悬浮任意一段可看该段简述；未勾选的段会淡化显示。
 */
export default function MappingArticleView({
  mapping,
  selectedPages,
}: MappingArticleViewProps) {
  const selectedSet = selectedPages ? new Set(selectedPages) : null

  return (
    <div className="article-map-body">
      {mapping.map((item) => {
        const dimmed =
          selectedSet !== null && !selectedSet.has(item.page_number)
        return (
          <Tooltip
            key={item.page_number}
            title={
              item.excluded
                ? `对照第${item.page_number}段（已弃用）`
                : item.summary
                  ? `对照第${item.page_number}段：${item.summary}`
                  : `对照第${item.page_number}段`
            }
            placement="top"
          >
            <span
              className={`article-map-segment${
                dimmed ? ' article-map-segment-off' : ''
              }${item.excluded ? ' article-map-segment-excluded' : ''}`}
            >
              <span className="article-map-badge">{item.page_number}</span>
              {item.source_text}
              {item.excluded && (
                <span className="article-map-excluded-tag">已弃用</span>
              )}
            </span>
          </Tooltip>
        )
      })}
    </div>
  )
}
