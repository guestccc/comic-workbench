import { describe, expect, it } from 'vitest'

import type { CharacterCard } from '../types'
import {
  absoluteAssetUrl,
  buildCharacterReferenceBlock,
  characterVariable,
} from './characterCopy'

const ORIGIN = 'http://127.0.0.1:8123'

const cards: CharacterCard[] = [
  {
    name: '我',
    role: '主角',
    appearance: '黑色长发',
    asset_url: '/uploads/character-assets/7/me.png',
  },
  {
    name: '王晨安',
    role: '男主',
    appearance: '黑色短发',
    asset_url: '/uploads/character-assets/7/wang.png',
  },
  {
    name: '小彤',
    role: '同事',
    appearance: '栗色短发',
    asset_url: null,
  },
]

describe('characterCopy', () => {
  it('生成角色变量写法', () => {
    expect(characterVariable('我')).toBe('{{我}}')
  })

  it('把相对资源地址解析成绝对地址', () => {
    expect(absoluteAssetUrl('/uploads/a.png', ORIGIN)).toBe(
      'http://127.0.0.1:8123/uploads/a.png',
    )
  })

  it('只把已有资产图的角色放进垫图分块', () => {
    expect(buildCharacterReferenceBlock(cards, ORIGIN)).toBe(
      [
        '【角色垫图】',
        '{{我}}：http://127.0.0.1:8123/uploads/character-assets/7/me.png',
        '{{王晨安}}：http://127.0.0.1:8123/uploads/character-assets/7/wang.png',
      ].join('\n'),
    )
  })

  it('没有资产图时返回空字符串', () => {
    expect(
      buildCharacterReferenceBlock(
        [{ name: '我', role: '主角', appearance: '黑色长发', asset_url: null }],
        ORIGIN,
      ),
    ).toBe('')
  })
})
