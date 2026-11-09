import { useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  Card,
  Input,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'
import type { SensitiveWord } from '../types'

const EMPTY_ROW: SensitiveWord = {
  word: '',
  replacement: '',
  category: '',
  enabled: true,
}

interface EditableWord extends SensitiveWord {
  _key: string
}

let rowKeySeed = 0

function withKey(item: SensitiveWord): EditableWord {
  rowKeySeed += 1
  return { ...item, _key: `word-${rowKeySeed}` }
}

function withoutKey(item: EditableWord): SensitiveWord {
  return {
    word: item.word,
    replacement: item.replacement,
    category: item.category,
    enabled: item.enabled,
  }
}

type StatusFilter = 'enabled' | 'disabled'

/** 全局敏感词库：本地编辑后统一保存；支持筛选、JSON / CSV 导入导出。 */
export default function SensitiveWordsPanel() {
  const { message } = App.useApp()
  const [words, setWords] = useState<EditableWord[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>()
  const [page, setPage] = useState(1)

  useEffect(() => {
    let cancelled = false
    void api
      .getSensitiveWords()
      .then((data) => {
        if (!cancelled) setWords(data.words.map(withKey))
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
  }, [message])

  useEffect(() => {
    setPage(1)
  }, [keyword, categoryFilter, statusFilter])

  const categories = useMemo(() => {
    const values = new Set(
      words.map((item) => item.category.trim()).filter(Boolean),
    )
    return Array.from(values).sort((left, right) =>
      left.localeCompare(right, 'zh-CN'),
    )
  }, [words])

  const filteredWords = useMemo(() => {
    const query = keyword.trim().toLowerCase()
    return words.filter((item) => {
      if (categoryFilter && item.category.trim() !== categoryFilter) return false
      if (statusFilter === 'enabled' && !item.enabled) return false
      if (statusFilter === 'disabled' && item.enabled) return false
      if (!query) return true
      return [item.word, item.replacement, item.category].some((value) =>
        value.toLowerCase().includes(query),
      )
    })
  }, [words, keyword, categoryFilter, statusFilter])

  const updateWord = (row: EditableWord, patch: Partial<SensitiveWord>) => {
    setWords((previous) =>
      previous.map((item) =>
        item._key === row._key ? { ...item, ...patch } : item,
      ),
    )
  }

  const removeWord = (row: EditableWord) => {
    setWords((previous) => previous.filter((item) => item._key !== row._key))
  }

  const addWord = () => {
    setWords((previous) => [
      ...previous,
      withKey({ ...EMPTY_ROW, category: categoryFilter ?? '' }),
    ])
    // 清掉会挡住新行的筛选，但保留当前分类，方便连续补同一类词
    setKeyword('')
    setStatusFilter(undefined)
    setPage(1)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const cleaned = words
        .filter((item) => item.word.trim())
        .map(withoutKey)
      const data = await api.saveSensitiveWords(cleaned)
      setWords(data.words.map(withKey))
      message.success(`已保存 ${data.words.length} 条敏感词`)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const parseImport = (raw: string): SensitiveWord[] => {
    const text = raw.trim()
    if (!text) return []
    if (text.startsWith('[') || text.startsWith('{')) {
      const parsed = JSON.parse(text)
      const list = Array.isArray(parsed) ? parsed : parsed.words
      if (!Array.isArray(list)) throw new Error('JSON 里没有 words 数组')
      return list.map((item: Partial<SensitiveWord>) => ({
        word: String(item.word ?? '').trim(),
        replacement: String(item.replacement ?? ''),
        category: String(item.category ?? '').trim(),
        enabled: item.enabled !== false,
      }))
    }
    return text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [word, replacement = '', category = '', enabled = '1'] = line
          .split(',')
          .map((part) => part.trim())
        return {
          word,
          replacement,
          category,
          enabled: !['0', 'false', '否', '停用'].includes(enabled.toLowerCase()),
        }
      })
      .filter((item) => item.word && item.word !== 'word')
  }

  const handleImport = async (file: File) => {
    try {
      const imported = parseImport(await file.text())
      if (imported.length === 0) {
        message.warning('文件里没有可导入的词条')
        return false
      }
      setWords(imported.map(withKey))
      setKeyword('')
      setCategoryFilter(undefined)
      setStatusFilter(undefined)
      setPage(1)
      message.info(`已载入 ${imported.length} 条，点「保存词库」后生效`)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导入失败')
    }
    return false
  }

  const handleExport = () => {
    const blob = new Blob(
      [JSON.stringify(words.map(withoutKey), null, 2)],
      { type: 'application/json;charset=utf-8' },
    )
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'sensitive-words.json'
    link.click()
    URL.revokeObjectURL(url)
  }

  /** 只合并缺失的默认词；不删除、不覆盖用户已有词条。 */
  const handleLoadDefaults = async () => {
    try {
      const data = await api.getDefaultSensitiveWords()
      const current = words.filter((item) => item.word.trim())
      const existing = new Set(
        current.map((item) => item.word.trim().toLowerCase()),
      )
      const additions = data.words.filter(
        (item) => !existing.has(item.word.toLowerCase()),
      )
      setWords([...current, ...additions.map(withKey)])
      message.info(
        additions.length > 0
          ? `已载入 ${additions.length} 条默认词，点「保存词库」后生效`
          : '默认词已全部在词库中',
      )
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const clearFilters = () => {
    setKeyword('')
    setCategoryFilter(undefined)
    setStatusFilter(undefined)
  }

  const hasFilters = Boolean(keyword || categoryFilter || statusFilter)

  return (
    <Card
      className="panel"
      title={
        <Space>
          敏感词库
          <Tag>{words.filter((item) => item.word.trim()).length} 条</Tag>
        </Space>
      }
      extra={
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void handleLoadDefaults()}>
            载入默认词库
          </Button>
          <Upload
            accept=".json,.csv,text/plain"
            showUploadList={false}
            beforeUpload={(file) => {
              void handleImport(file)
              return false
            }}
          >
            <Button icon={<UploadOutlined />}>导入 JSON / CSV</Button>
          </Upload>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>
            导出 JSON
          </Button>
          <Button
            type="primary"
            loading={saving}
            onClick={() => void handleSave()}
          >
            保存词库
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Typography.Text type="secondary">
          扫描只做精确匹配，按词长优先；替换词留空表示删除。词库只保存在本机数据库。
          默认词库覆盖广告法、虚假宣传、医疗功效、金融理财、教育培训、站外导流等商业违规词；
          宽泛词默认停用，避免误伤正文，需要时手动打开。
        </Typography.Text>

        <Space wrap>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索敏感词 / 替换词 / 分类"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            style={{ width: 280 }}
          />
          <Select
            allowClear
            placeholder="分类"
            options={categories.map((category) => ({
              value: category,
              label: category,
            }))}
            value={categoryFilter}
            onChange={setCategoryFilter}
            style={{ width: 180 }}
          />
          <Select<StatusFilter>
            allowClear
            placeholder="状态"
            options={[
              { value: 'enabled', label: '已启用' },
              { value: 'disabled', label: '已停用' },
            ]}
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 120 }}
          />
          {hasFilters && (
            <Button type="link" onClick={clearFilters}>
              清空筛选
            </Button>
          )}
          <Typography.Text type="secondary">
            显示 {filteredWords.length} / {words.length} 条
          </Typography.Text>
        </Space>

        <Table
          size="small"
          rowKey="_key"
          loading={loading}
          dataSource={filteredWords}
          locale={{
            emptyText: hasFilters
              ? '没有匹配的敏感词'
              : '还没有敏感词，点下方「添加词条」或「载入默认词库」',
          }}
          pagination={{
            current: page,
            pageSize: 20,
            onChange: setPage,
            hideOnSinglePage: true,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 条`,
          }}
          columns={[
            {
              title: '敏感词',
              dataIndex: 'word',
              width: 180,
              render: (value: string, row: EditableWord) => (
                <Input
                  value={value}
                  placeholder="必填"
                  onChange={(event) =>
                    updateWord(row, { word: event.target.value })
                  }
                />
              ),
            },
            {
              title: '替换为',
              dataIndex: 'replacement',
              render: (value: string, row: EditableWord) => (
                <Input
                  value={value}
                  placeholder="留空表示删除"
                  onChange={(event) =>
                    updateWord(row, { replacement: event.target.value })
                  }
                />
              ),
            },
            {
              title: '分类',
              dataIndex: 'category',
              width: 160,
              render: (value: string, row: EditableWord) => (
                <Input
                  value={value}
                  placeholder="可选"
                  onChange={(event) =>
                    updateWord(row, { category: event.target.value })
                  }
                />
              ),
            },
            {
              title: '启用',
              dataIndex: 'enabled',
              width: 80,
              render: (value: boolean, row: EditableWord) => (
                <Switch
                  size="small"
                  checked={value}
                  onChange={(checked) =>
                    updateWord(row, { enabled: checked })
                  }
                />
              ),
            },
            {
              title: '',
              width: 56,
              render: (_value, row: EditableWord) => (
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => removeWord(row)}
                />
              ),
            },
          ]}
          footer={() => (
            <Button
              type="dashed"
              block
              icon={<PlusOutlined />}
              onClick={addWord}
            >
              添加词条
            </Button>
          )}
        />
      </Space>
    </Card>
  )
}
