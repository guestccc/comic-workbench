import type { ReactNode } from 'react'
import { PUBLISH_PLATFORM_META } from '../utils/publishing'
import type { PublishPlatform } from '../types'

interface PlatformIconProps {
  platform: PublishPlatform
  /** 边长像素；只在这里定尺寸，页面不得各写像素 */
  size?: number
  className?: string
}

interface PlatformLabelProps extends PlatformIconProps {
  /** 接在平台名后，例如「图文发布」 */
  suffix?: ReactNode
}

/**
 * 平台品牌图标：纯装饰，平台名由相邻文本提供。
 * 中文名与图标路径都来自 `PUBLISH_PLATFORM_META`，不在这里重复定义。
 */
export function PlatformIcon({
  platform,
  size = 16,
  className,
}: PlatformIconProps) {
  const meta = PUBLISH_PLATFORM_META[platform]
  return (
    <img
      className={className ? `platform-icon ${className}` : 'platform-icon'}
      src={meta.icon}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      draggable={false}
    />
  )
}

/** 平台独立标识：图标 + 平台名；所有平台标注都通过它渲染。 */
export default function PlatformLabel({
  platform,
  size,
  suffix,
  className,
}: PlatformLabelProps) {
  return (
    <span className={className ? `platform-label ${className}` : 'platform-label'}>
      <PlatformIcon platform={platform} size={size} />
      <span>
        {PUBLISH_PLATFORM_META[platform].text}
        {suffix}
      </span>
    </span>
  )
}

/** 平台下拉选项：筛选与切换共用，标签直接渲染图标 + 平台名。 */
export const PLATFORM_OPTIONS = (
  Object.keys(PUBLISH_PLATFORM_META) as PublishPlatform[]
).map((platform) => ({
  value: platform,
  label: <PlatformLabel platform={platform} />,
}))
