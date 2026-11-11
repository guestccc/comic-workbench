import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  formatPublishTime,
  formatXhsDeclaration,
  resolvePublishMode,
} from './publishing'

describe('resolvePublishMode', () => {
  it('保留立即发布', () => {
    expect(resolvePublishMode('immediate')).toBe('immediate')
  })

  it('旧任务缺少 mode 时按定时发布兜底', () => {
    expect(resolvePublishMode(undefined)).toBe('scheduled')
    expect(resolvePublishMode(null)).toBe('scheduled')
    expect(resolvePublishMode('scheduled')).toBe('scheduled')
  })
})

describe('formatXhsDeclaration', () => {
  it('未声明时显示不声明', () => {
    expect(formatXhsDeclaration(null, null)).toBe('不声明')
    expect(formatXhsDeclaration('', '')).toBe('不声明')
  })

  it('直接选项原样展示', () => {
    expect(formatXhsDeclaration('笔记含AI合成内容', null)).toBe(
      '笔记含AI合成内容',
    )
  })

  it('有来源媒体名时带在括号里', () => {
    expect(formatXhsDeclaration('来源转载', '某媒体')).toBe(
      '来源转载（某媒体）',
    )
  })
})

describe('formatPublishTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-10T10:00:00'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('当天显示今天 + 时分', () => {
    expect(formatPublishTime('2026-11-10T09:59:00')).toBe('今天 09:59')
    expect(formatPublishTime('2026-11-10T23:30:00')).toBe('今天 23:30')
  })

  it('前三天显示前天 / 昨天', () => {
    expect(formatPublishTime('2026-11-09T22:05:00')).toBe('昨天 22:05')
    expect(formatPublishTime('2026-11-08T00:10:00')).toBe('前天 00:10')
  })

  it('未来三天显示明天 / 后天', () => {
    expect(formatPublishTime('2026-11-11T18:00:00')).toBe('明天 18:00')
    expect(formatPublishTime('2026-11-12T09:00:00')).toBe('后天 09:00')
  })

  it('超出前后三天显示完整日期时间', () => {
    expect(formatPublishTime('2026-11-07T08:00:00')).toBe('2026-11-07 08:00')
    expect(formatPublishTime('2026-11-13T08:00:00')).toBe('2026-11-13 08:00')
  })

  it('空值与非法日期显示占位符', () => {
    expect(formatPublishTime(null)).toBe('—')
    expect(formatPublishTime(undefined)).toBe('—')
    expect(formatPublishTime('')).toBe('—')
    expect(formatPublishTime('not-a-date')).toBe('—')
  })
})
