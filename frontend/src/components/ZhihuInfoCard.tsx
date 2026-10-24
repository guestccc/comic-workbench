import { useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  CopyOutlined,
  EditOutlined,
  LinkOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { api, getErrorMessage } from '../api/client'
import type { Story } from '../types'
import { copyText } from '../utils/clipboard'

interface ZhihuInfoCardProps {
  story: Story
  /** 保存成功后把新的故事数据回传给详情页 */
  onUpdated: (story: Story) => void
}

interface ZhihuFormValues {
  zhihu_title: string
  zhihu_article_id: string
  zhihu_alias: string
  zhihu_aliases: string[]
}

const ALIAS_PATTERN = /^[一-鿿]{6,8}$/

/**
 * 故事级知乎推广信息卡片。
 *
 * 集中展示原文标题、原文 ID 与搜索别名，避免用户忘记三者的对应关系；
 * 别名用 DeepSeek 生成候选，但最终以用户在知乎注册的结果为准。
 */
export default function ZhihuInfoCard({
  story,
  onUpdated,
}: ZhihuInfoCardProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<ZhihuFormValues>()
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const watchedAliases =
    (Form.useWatch('zhihu_aliases', form) as string[] | undefined) ?? []

  const articleId = story.zhihu_article_id.trim()
  const articleUrl = /^\d+$/.test(articleId)
    ? `https://zhuanlan.zhihu.com/p/${articleId}`
    : null
  const storedAliases =
    story.zhihu_aliases?.length > 0
      ? story.zhihu_aliases
      : story.zhihu_alias
        ? [story.zhihu_alias]
        : []
  const aliasPrefix = story.zhihu_alias
    ? `【${story.zhihu_alias}】`
    : ''
  const invalidStoredAliases = storedAliases.filter(
    (alias) => !ALIAS_PATTERN.test(alias),
  )
  const invalidWatchedAliases = watchedAliases.filter(
    (alias) => alias.trim() && !ALIAS_PATTERN.test(alias.trim()),
  )

  const copy = async (text: string, label: string) => {
    if (!text) {
      message.warning(`${label}还没有填写`)
      return
    }
    try {
      await copyText(text)
      message.success(`${label}已复制`)
    } catch {
      message.error('复制失败，请手动选中后复制')
    }
  }

  const openEdit = () => {
    form.setFieldsValue({
      zhihu_title: story.zhihu_title,
      zhihu_article_id: story.zhihu_article_id,
      zhihu_alias: story.zhihu_alias,
      zhihu_aliases: storedAliases,
    })
    setOpen(true)
  }

  const handleGenerateAliases = async () => {
    const title = (form.getFieldValue('zhihu_title') ?? '').trim()
    if (!title) {
      message.warning('请先填写知乎原文标题，再生成别名')
      return
    }
    setGenerating(true)
    try {
      const result = await api.suggestZhihuAliases(story.id, title)
      if (result.aliases.length === 0) {
        message.warning('没有生成可用别名，请手动填写')
        return
      }
      const current =
        (form.getFieldValue('zhihu_aliases') as string[] | undefined) ?? []
      const merged = Array.from(
        new Set([...current, ...result.aliases]),
      ).slice(0, 20)
      form.setFieldValue('zhihu_aliases', merged)
      message.success(
        `已加入 ${result.aliases.length} 个候选别名，可删除不需要的；最终使用哪个请在下方标注`,
      )
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setGenerating(false)
    }
  }

  const removeInvalidAliases = () => {
    const valid = watchedAliases
      .map((alias) => alias.trim())
      .filter((alias) => ALIAS_PATTERN.test(alias))
    form.setFieldValue('zhihu_aliases', valid)
    const active = ((form.getFieldValue('zhihu_alias') ?? '') as string).trim()
    if (active && !valid.includes(active)) {
      form.setFieldValue('zhihu_alias', undefined)
    }
    message.success('已移除不符合 6–8 字规则的候选别名')
  }

  const handleSave = async () => {
    let values: ZhihuFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    setSaving(true)
    try {
      const updated = await api.updateStoryZhihu(story.id, {
        zhihu_title: (values.zhihu_title ?? '').trim(),
        zhihu_article_id: (values.zhihu_article_id ?? '').trim(),
        zhihu_alias: (values.zhihu_alias ?? '').trim(),
        zhihu_aliases: (values.zhihu_aliases ?? []).map((alias) =>
          alias.trim(),
        ),
      })
      onUpdated(updated)
      setOpen(false)
      message.success('知乎推广信息已保存；已保存的文案开头会同步别名')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Card
        size="small"
        className="zhihu-info-card"
        title="知乎推广信息"
        extra={
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={openEdit}
          >
            录入 / 编辑
          </Button>
        }
      >
        {!story.zhihu_alias && storedAliases.length === 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 10 }}
            message="还没有设置知乎别名"
            description="设置后，发文案时正文开头会自动加入【别名】，用户去知乎搜索这个别名。"
          />
        )}
        {!story.zhihu_alias && storedAliases.length > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 10 }}
            message="已有候选别名，但还没有标注最终使用哪一个"
            description="先在知乎注册这些别名，确认哪个没重名后，回来把「最终使用别名」标注上；发文案时只用最终别名。"
          />
        )}
        {invalidStoredAliases.length > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 10 }}
            message={`有 ${invalidStoredAliases.length} 个旧候选别名不符合 6–8 字规则`}
            description="点「录入 / 编辑」里的「移除不合规候选」清理，或重新生成候选。"
          />
        )}

        <div className="zhihu-info-row">
          <span className="zhihu-info-label">原文标题</span>
          <Typography.Text className="zhihu-info-value">
            {story.zhihu_title || '未填写'}
          </Typography.Text>
          <Button
            size="small"
            type="text"
            icon={<CopyOutlined />}
            onClick={() => void copy(story.zhihu_title, '原文标题')}
          />
        </div>

        <div className="zhihu-info-row">
          <span className="zhihu-info-label">原文 ID</span>
          <Typography.Text className="zhihu-info-value" code>
            {story.zhihu_article_id || '未填写'}
          </Typography.Text>
          {articleUrl && (
            <Typography.Link
              href={articleUrl}
              target="_blank"
              rel="noreferrer"
            >
              <LinkOutlined /> 打开
            </Typography.Link>
          )}
          <Button
            size="small"
            type="text"
            icon={<CopyOutlined />}
            onClick={() => void copy(story.zhihu_article_id, '原文 ID')}
          />
        </div>

        <div className="zhihu-info-row">
          <span className="zhihu-info-label">最终使用别名</span>
          {story.zhihu_alias ? (
            <Tag color="purple" className="zhihu-alias-tag">
              {story.zhihu_alias}
            </Tag>
          ) : (
            <Typography.Text type="secondary">未标注</Typography.Text>
          )}
          <Button
            size="small"
            type="text"
            icon={<CopyOutlined />}
            onClick={() => void copy(story.zhihu_alias, '最终使用别名')}
          />
        </div>

        {storedAliases.length > 0 && (
          <div className="zhihu-info-row">
            <span className="zhihu-info-label">候选别名</span>
            <Space wrap size={4}>
              {storedAliases.map((alias) => (
                <Tag
                  key={alias}
                  color={
                    alias === story.zhihu_alias
                      ? 'purple'
                      : ALIAS_PATTERN.test(alias)
                        ? 'default'
                        : 'orange'
                  }
                  className="zhihu-alias-tag"
                >
                  {alias}
                </Tag>
              ))}
            </Space>
          </div>
        )}

        {story.zhihu_alias && (
          <div className="zhihu-info-row">
            <span className="zhihu-info-label">正文开头</span>
            <Typography.Text strong className="zhihu-info-value">
              {aliasPrefix}
            </Typography.Text>
            <Button
              size="small"
              type="text"
              icon={<CopyOutlined />}
              onClick={() => void copy(aliasPrefix, '正文开头别名')}
            />
          </div>
        )}

        <Typography.Text type="secondary" className="zhihu-info-hint">
          用户在小红书正文开头看到【别名】后，去知乎搜索这个别名，进入对应原文。
          别名请先在知乎注册确认可用，再保存到这里。
        </Typography.Text>
      </Card>

      <Modal
        title="知乎推广信息"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void handleSave()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={620}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="zhihu_title"
            label="知乎原文标题"
            rules={[
              {
                validator: (_, value: string) => {
                  const title = (value ?? '').trim()
                  const alias = (
                    form.getFieldValue('zhihu_alias') ?? ''
                  ).trim()
                  const aliases =
                    (form.getFieldValue('zhihu_aliases') as
                      | string[]
                      | undefined) ?? []
                  if ((alias || aliases.length > 0) && !title) {
                    return Promise.reject(
                      new Error('填写别名时，原文标题不能为空'),
                    )
                  }
                  return Promise.resolve()
                },
              },
            ]}
            extra="别名不能连续使用这个标题里的任意两个字。"
          >
            <Input
              maxLength={300}
              showCount
              placeholder="例如：重生后我嫁给了渣男"
            />
          </Form.Item>

          <Form.Item
            name="zhihu_article_id"
            label="知乎原文 ID"
            rules={[
              {
                validator: (_, value: string) => {
                  const text = (value ?? '').trim()
                  if (text && !/^\d+$/.test(text)) {
                    return Promise.reject(
                      new Error('知乎原文 ID 只能是数字'),
                    )
                  }
                  return Promise.resolve()
                },
              },
            ]}
            extra="例如：2096656473648525790，可用来生成知乎原文链接。"
          >
            <Input maxLength={64} placeholder="2096656473648525790" />
          </Form.Item>

          {invalidWatchedAliases.length > 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message={`候选里有 ${invalidWatchedAliases.length} 个不符合 6–8 字规则`}
              action={
                <Button
                  size="small"
                  onClick={removeInvalidAliases}
                >
                  移除不合规候选
                </Button>
              }
            />
          )}

          <Form.Item
            name="zhihu_aliases"
            label="候选别名（可多选，6–8 个汉字）"
            rules={[
              {
                validator: (_, value: string[]) => {
                  const aliases = (value ?? [])
                    .map((alias) => alias.trim())
                    .filter(Boolean)
                  if (aliases.length > 20) {
                    return Promise.reject(
                      new Error('候选别名最多 20 个'),
                    )
                  }
                  if (aliases.some((alias) => !ALIAS_PATTERN.test(alias))) {
                    return Promise.reject(
                      new Error('每个别名必须是 6–8 个汉字'),
                    )
                  }
                  if (new Set(aliases).size !== aliases.length) {
                    return Promise.reject(
                      new Error('候选别名不能重复'),
                    )
                  }
                  return Promise.resolve()
                },
              },
            ]}
            extra="可以保存多个候选，方便你在知乎逐个注册；只允许中文汉字，不含字母、数字、标点、空格。"
          >
            <Select
              mode="tags"
              maxCount={20}
              tokenSeparators={[',', '，', ' ']}
              placeholder="输入别名，或点下方「生成别名候选」"
            />
          </Form.Item>

          <Space wrap size={8} style={{ marginBottom: 12 }}>
            <Button
              size="small"
              icon={<ThunderboltOutlined />}
              loading={generating}
              onClick={() => void handleGenerateAliases()}
            >
              生成别名候选
            </Button>
            <Typography.Text type="secondary">
              会追加到候选列表，可删除不需要的
            </Typography.Text>
          </Space>

          <Form.Item
            name="zhihu_alias"
            label="最终使用别名"
            rules={[
              {
                validator: (_, value: string) => {
                  const text = (value ?? '').trim()
                  if (!text) return Promise.resolve()
                  if (!ALIAS_PATTERN.test(text)) {
                    return Promise.reject(
                      new Error('最终别名必须是 6–8 个汉字'),
                    )
                  }
                  const aliases = (
                    (form.getFieldValue('zhihu_aliases') as
                      | string[]
                      | undefined) ?? []
                  ).map((alias) => alias.trim())
                  if (!aliases.includes(text)) {
                    return Promise.reject(
                      new Error('最终别名必须先从候选别名里添加'),
                    )
                  }
                  if (!(form.getFieldValue('zhihu_title') ?? '').trim()) {
                    return Promise.reject(
                      new Error('填写最终别名时，原文标题不能为空'),
                    )
                  }
                  return Promise.resolve()
                },
              },
            ]}
            extra="可以稍后再标注；只有这个最终别名会写进发文正文开头。"
          >
            <Select
              allowClear
              placeholder="先添加候选别名，再在这里标注最终使用的"
              options={watchedAliases
                .map((alias) => alias.trim())
                .filter(
                  (alias) => alias && ALIAS_PATTERN.test(alias),
                )
                .map((alias) => ({ value: alias, label: alias }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
