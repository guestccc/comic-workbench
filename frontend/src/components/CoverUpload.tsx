import { useState } from 'react'
import { App, Upload } from 'antd'
import { LoadingOutlined, PlusOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { api, getErrorMessage } from '../api/client'

interface CoverUploadProps {
  value?: string | null
  onChange?: (value: string | null) => void
  disabled?: boolean
  /** 通知父组件当前是否正在上传，便于禁用保存按钮 */
  onUploadingChange?: (uploading: boolean) => void
}

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_SIZE = 5 * 1024 * 1024

/**
 * 受控封面上传：表单值只保存服务端返回的文件名。
 * 不使用 antd 内置上传（action），而是手动调用后端接口，以便统一错误处理。
 */
export default function CoverUpload({
  value,
  onChange,
  disabled,
  onUploadingChange,
}: CoverUploadProps) {
  const { message } = App.useApp()
  const [uploading, setUploading] = useState(false)

  const setUploadingState = (next: boolean) => {
    setUploading(next)
    onUploadingChange?.(next)
  }

  const fileList: UploadFile[] =
    value != null
      ? [
          {
            uid: value,
            name: value,
            status: 'done',
            url: `/uploads/${value}`,
          },
        ]
      : []

  const handleUpload = async (file: File) => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      message.error('仅支持 JPG、PNG、WebP 格式的图片')
      return Upload.LIST_IGNORE
    }
    if (file.size > MAX_SIZE) {
      message.error('图片大小不能超过 5MB')
      return Upload.LIST_IGNORE
    }

    setUploadingState(true)
    try {
      const result = await api.uploadCover(file)
      onChange?.(result.filename)
      message.success('封面上传成功')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setUploadingState(false)
    }
    // 阻止 antd 自动上传，列表状态由 value 派生
    return Upload.LIST_IGNORE
  }

  return (
    <Upload
      accept="image/jpeg,image/png,image/webp"
      listType="picture-card"
      maxCount={1}
      fileList={fileList}
      beforeUpload={(file) => handleUpload(file as File)}
      onRemove={() => {
        onChange?.(null)
        return false
      }}
      showUploadList={{ showPreviewIcon: false }}
      disabled={disabled || uploading}
    >
      {fileList.length === 0 && (
        <div className="cover-upload-trigger">
          {uploading ? <LoadingOutlined /> : <PlusOutlined />}
          <div className="cover-upload-text">
            {uploading ? '上传中' : '上传封面'}
          </div>
        </div>
      )}
    </Upload>
  )
}
