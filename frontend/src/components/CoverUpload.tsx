import { App } from 'antd'
import ImageUpload from './ImageUpload'
import { api, getErrorMessage } from '../api/client'

interface CoverUploadProps {
  value?: string | null
  onChange?: (value: string | null) => void
  disabled?: boolean
  /** 通知父组件当前是否正在上传，便于禁用保存按钮 */
  onUploadingChange?: (uploading: boolean) => void
}

/**
 * 故事封面上传：表单值只保存服务端返回的文件名。
 * 交互与校验统一由 ImageUpload 提供（点击选择或 Ctrl+V 粘贴截图）。
 */
export default function CoverUpload({
  value,
  onChange,
  disabled,
  onUploadingChange,
}: CoverUploadProps) {
  const { message } = App.useApp()

  return (
    <ImageUpload
      variant="card"
      imageUrl={value ? `/uploads/${value}` : null}
      uploadText="上传封面"
      disabled={disabled}
      onUploadingChange={onUploadingChange}
      onUpload={async (file) => {
        try {
          const result = await api.uploadCover(file)
          onChange?.(result.filename)
          message.success('封面上传成功')
        } catch (error) {
          message.error(getErrorMessage(error))
        }
      }}
      onRemove={() => onChange?.(null)}
    />
  )
}
