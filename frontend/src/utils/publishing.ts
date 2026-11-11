import dayjs from 'dayjs'
import type { PublishJobStatus, PublishMode, PublishPlatform } from '../types'

/**
 * 发布平台的显示名与图标路径；标题、按钮、提示、筛选与图标组件共用同一份映射。
 * 图标资产见 `frontend/public/icons/`，构建后由后端静态服务提供。
 */
export const PUBLISH_PLATFORM_META: Record<
  PublishPlatform,
  { text: string; icon: string }
> = {
  douyin: { text: '抖音', icon: '/icons/douyin.png' },
  xiaohongshu: { text: '小红书', icon: '/icons/xiaohongshu.png' },
}

/** 发布方式中文名；面板、任务页与详情弹窗共用同一份映射。 */
export const PUBLISH_MODE_META: Record<PublishMode, { text: string }> = {
  scheduled: { text: '定时发布' },
  immediate: { text: '立即发布' },
}

/**
 * 旧任务或旧后端返回的载荷可能没有 mode；
 * 统一按定时发布兜底，避免展示层各自判断。
 */
export function resolvePublishMode(
  mode: PublishMode | null | undefined,
): PublishMode {
  return mode === 'immediate' ? 'immediate' : 'scheduled'
}

/** 定时发布窗口的界面边界；最终以预览返回的校验结果为准。 */
export const PUBLISH_SCHEDULE_MIN_LEAD_HOURS = 2
export const PUBLISH_SCHEDULE_MAX_DAYS = 14

/** 发布任务状态的中文名与标签颜色；展示与筛选共用同一份映射。 */
export const PUBLISH_STATUS_META: Record<
  PublishJobStatus,
  { text: string; color: string }
> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '发布中', color: 'processing' },
  scheduled: { text: '已定时', color: 'success' },
  published: { text: '已发布', color: 'success' },
  failed: { text: '失败', color: 'error' },
  unknown: { text: '待核对', color: 'warning' },
}

/**
 * 近三天的相对日期前缀，按自然日差取值。
 *
 * dayjs 的 `calendar` 插件只覆盖今天 / 昨天 / 明天，`relativeTime` 输出「2 天前」，
 * 都拿不到「前天 / 后天」，所以这里直接按天数差映射，不额外引入日期库。
 */
const RELATIVE_DAY_PREFIX: Record<number, string> = {
  [-2]: '前天',
  [-1]: '昨天',
  0: '今天',
  1: '明天',
  2: '后天',
}

/** 发布任务时间的统一展示：近三天用相对日期，超出范围用完整日期时间。 */
export function formatPublishTime(value: string | null | undefined): string {
  if (!value) return '—'
  const target = dayjs(value)
  if (!target.isValid()) return '—'
  // 按自然日比较，避免用小时差时跨零点判错（如「昨天 23:50」）
  const dayDiff = target.startOf('day').diff(dayjs().startOf('day'), 'day')
  const prefix = RELATIVE_DAY_PREFIX[dayDiff]
  return prefix
    ? `${prefix} ${target.format('HH:mm')}`
    : target.format('YYYY-MM-DD HH:mm')
}

/** 内容声明的统一展示：后端只在需要来源时给出 repost_source。 */
export function formatXhsDeclaration(
  declaration: string | null | undefined,
  repostSource: string | null | undefined,
): string {
  if (!declaration) return '不声明'
  return repostSource ? `${declaration}（${repostSource}）` : declaration
}
