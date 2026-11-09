import { useEffect, useRef, useState } from 'react'
import type { ClipboardEvent } from 'react'
import { Alert, App, Button, Image, Modal, Space, Typography, Upload } from 'antd'
import {
  DeleteOutlined,
  LoadingOutlined,
  PictureOutlined,
  PlusOutlined,
  UploadOutlined,
} from '@ant-design/icons'

/** 全站统一的图片类型白名单（与后端保持一致）。 */
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

interface ImageUploadProps {
  /** 已有图片地址；有值时展示缩略图 */
  imageUrl?: string | null
  /**
   * 上传实现（调用后端接口）。
   * 组件内部只负责校验与状态复位，成功提示与错误提示由调用方处理。
   */
  onUpload: (file: File) => Promise<void>
  /** 删除已有图片；不传则不显示删除入口 */
  onRemove?: () => void
  disabled?: boolean
  /** 大小上限（字节），默认 5MB；分镜成品图传 15MB */
  maxSizeBytes?: number
  /** card：封面小卡片；thumb：大缩略图 + 侧边按钮；button：仅紧凑按钮；asset：竖版缩略图 + 下方按钮 */
  variant?: 'card' | 'thumb' | 'button' | 'asset'
  /** 无图时的按钮文案 */
  uploadText?: string
  /** 有图时的替换按钮文案（thumb 形态） */
  replaceText?: string
  /** 上传中状态变化回调，便于外层禁用保存按钮 */
  onUploadingChange?: (uploading: boolean) => void
}

/**
 * 统一的图片上传组件。
 *
 * 交互：点击占位图/按钮弹出上传弹窗，弹窗内可「选择本地文件」，
 * 也可以点击粘贴区后直接 Ctrl+V 粘贴剪贴板截图（浏览器要求先聚焦才能接收粘贴事件）。
 * 上传成功后弹窗保持打开，展示刚上传的图片；点击遮罩或关闭按钮即可关闭。
 * 所有上传入口共用这一行为，不提供逐处开关（见 C-11）。
 */
export default function ImageUpload({
  imageUrl,
  onUpload,
  onRemove,
  disabled,
  maxSizeBytes = 5 * 1024 * 1024,
  variant = 'thumb',
  uploadText = '上传图片',
  replaceText = '替换图片',
  onUploadingChange,
}: ImageUploadProps) {
  const { message } = App.useApp()
  const [uploading, setUploading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [uploaded, setUploaded] = useState(false)
  const [uploadedPreviewUrl, setUploadedPreviewUrl] = useState<string | null>(
    null,
  )
  const uploadedPreviewRef = useRef<string | null>(null)
  // 粘贴区引用：弹窗打开后自动聚焦，用户无需再点击即可直接 Ctrl+V
  const pasteZoneRef = useRef<HTMLDivElement>(null)

  const clearUploadedPreview = () => {
    if (uploadedPreviewRef.current) {
      URL.revokeObjectURL(uploadedPreviewRef.current)
      uploadedPreviewRef.current = null
    }
    setUploadedPreviewUrl(null)
  }

  const closeModal = () => {
    setModalOpen(false)
    setUploaded(false)
    clearUploadedPreview()
  }

  useEffect(
    () => () => {
      if (uploadedPreviewRef.current) {
        URL.revokeObjectURL(uploadedPreviewRef.current)
      }
    },
    [],
  )

  const setUploadingState = (next: boolean) => {
    setUploading(next)
    onUploadingChange?.(next)
  }

  /** 校验并上传；成功后保持弹窗打开，展示本次上传结果。 */
  const doUpload = async (file: File) => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      message.error('仅支持 JPG、PNG、WebP 格式的图片')
      return
    }
    if (file.size > maxSizeBytes) {
      message.error(
        `图片大小不能超过 ${Math.round(maxSizeBytes / 1024 / 1024)}MB`,
      )
      return
    }

    setUploaded(false)
    setUploadingState(true)
    try {
      await onUpload(file)
      setUploaded(true)
      clearUploadedPreview()
      const previewUrl = URL.createObjectURL(file)
      uploadedPreviewRef.current = previewUrl
      setUploadedPreviewUrl(previewUrl)
    } catch {
      // 错误提示由调用方负责，这里只复位状态
    } finally {
      setUploadingState(false)
    }
  }

  /** 读取剪贴板中的图片文件并上传；纯文本粘贴不拦截。 */
  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    if (disabled || uploading) return
    const file = Array.from(event.clipboardData?.files ?? []).find((item) =>
      item.type.startsWith('image/'),
    )
    if (!file) return
    event.preventDefault()
    void doUpload(file)
  }

  const openModal = () => {
    if (disabled || uploading) return
    setUploaded(false)
    clearUploadedPreview()
    setModalOpen(true)
  }

  const previewSrc = uploadedPreviewUrl

  const uploadModal = (
    <Modal
      open={modalOpen}
      title={uploaded ? '确认上传的图片' : imageUrl ? replaceText : uploadText}
      footer={null}
      maskClosable={!uploading}
      keyboard={!uploading}
      onCancel={() => {
        if (!uploading) closeModal()
      }}
      afterOpenChange={(open) => {
        // 打开动画结束后再把焦点交给粘贴区，否则会被弹窗自身的焦点管理覆盖
        if (open) pasteZoneRef.current?.focus()
      }}
      width={520}
      styles={{ body: { maxHeight: '70vh', overflowY: 'auto' } }}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {uploaded && (
          <Alert
            type="success"
            showIcon
            message="上传成功，请确认图片是否正确"
            description="确认无误后点击遮罩即可关闭；如果图片不对，可在本弹窗内重新选择或粘贴。"
          />
        )}
        {previewSrc ? (
          <Image
            src={previewSrc}
            alt="待确认图片"
            className="image-upload-confirm-preview"
            style={{ width: '100%', maxHeight: 360, objectFit: 'contain' }}
          />
        ) : null}
        {/* 粘贴区：tabIndex 让其可点击聚焦，聚焦后浏览器才会派发粘贴事件 */}
        <div
          ref={pasteZoneRef}
          className="image-upload-paste-zone"
          tabIndex={uploading ? undefined : 0}
          onPaste={handlePaste}
        >
          {uploading ? (
            <LoadingOutlined className="image-upload-paste-icon" />
          ) : (
            <PictureOutlined className="image-upload-paste-icon" />
          )}
          <div className="image-upload-paste-text">
            {uploading ? '上传中…' : '点击此区域，然后 Ctrl+V 粘贴截图'}
          </div>
          <Typography.Text type="secondary" className="image-upload-hint">
            区域边框变红表示已可粘贴
          </Typography.Text>
        </div>
        <Upload
          accept="image/jpeg,image/png,image/webp"
          showUploadList={false}
          disabled={uploading}
          beforeUpload={(file) => {
            void doUpload(file as File)
            return Upload.LIST_IGNORE
          }}
        >
          <Button block icon={<UploadOutlined />} loading={uploading}>
            选择本地文件
          </Button>
        </Upload>
        <Typography.Text type="secondary" className="image-upload-hint">
          支持 JPG、PNG、WebP，不超过{' '}
          {Math.round(maxSizeBytes / 1024 / 1024)}MB
        </Typography.Text>
      </Space>
    </Modal>
  )

  return (
    <div className={`image-upload image-upload-${variant}`}>
      {variant === 'button' ? (
        // 紧凑按钮：点击打开统一的上传弹窗（选择文件 / Ctrl+V 粘贴）
        <Button
          size="small"
          type={imageUrl ? 'default' : 'primary'}
          ghost={!imageUrl}
          icon={<UploadOutlined />}
          loading={uploading}
          disabled={disabled}
          onClick={openModal}
        >
          {imageUrl ? replaceText : uploadText}
        </Button>
      ) : variant === 'card' ? (
        <Space align="start" size={8}>
          {imageUrl ? (
            <img
              className="cover-thumb image-upload-card-trigger"
              src={imageUrl}
              alt="封面预览"
              onClick={openModal}
            />
          ) : (
            <div
              className="cover-placeholder image-upload-card-trigger"
              onClick={openModal}
            >
              {uploading ? <LoadingOutlined /> : <PlusOutlined />}
              <div className="cover-upload-text">
                {uploading ? '上传中' : uploadText}
              </div>
            </div>
          )}
          {imageUrl && onRemove && (
            <Button
              size="small"
              type="text"
              danger
              icon={<DeleteOutlined />}
              onClick={onRemove}
            />
          )}
        </Space>
      ) : variant === 'asset' ? (
        // 角色资产图：竖版缩略图 + 下方「上传 / 替换 / 删除」
        <div>
          {imageUrl ? (
            <Image
              src={imageUrl}
              className="image-upload-asset-image"
              alt="角色资产图预览"
            />
          ) : (
            <div
              className="image-upload-asset-placeholder"
              onClick={openModal}
            >
              {uploading ? <LoadingOutlined /> : <PictureOutlined />}
              <div className="cover-upload-text">
                {uploading ? '上传中' : uploadText}
              </div>
            </div>
          )}
          <Space size={4} style={{ marginTop: 6 }}>
            <Button
              size="small"
              icon={<UploadOutlined />}
              loading={uploading}
              disabled={disabled}
              onClick={openModal}
            >
              {imageUrl ? replaceText : uploadText}
            </Button>
            {imageUrl && onRemove && (
              <Button
                size="small"
                type="text"
                danger
                icon={<DeleteOutlined />}
                onClick={onRemove}
                disabled={uploading}
              />
            )}
          </Space>
        </div>
      ) : imageUrl ? (
        <Space align="start" size={12}>
          <Image
            src={imageUrl}
            width={120}
            className="page-image-thumb"
            alt="图片预览"
          />
          <Space direction="vertical" size={4}>
            <Button
              size="small"
              icon={<UploadOutlined />}
              loading={uploading}
              onClick={openModal}
            >
              {replaceText}
            </Button>
            {onRemove && (
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={onRemove}
                disabled={uploading}
              >
                删除图片
              </Button>
            )}
          </Space>
        </Space>
      ) : (
        <Button
          size="small"
          type="primary"
          ghost
          icon={<UploadOutlined />}
          loading={uploading}
          onClick={openModal}
        >
          {uploadText}
        </Button>
      )}
      {uploadModal}
    </div>
  )
}
