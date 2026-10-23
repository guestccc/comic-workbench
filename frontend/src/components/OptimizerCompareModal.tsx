import { Modal, Space, Typography } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import ReactDiffViewer, {
  DiffMethod,
  type ReactDiffViewerStylesOverride,
} from 'react-diff-viewer-continued'

interface OptimizerCompareModalProps {
  open: boolean
  /** AI 优化前的当前内容 */
  original: string
  /** AI 生成的新版内容（已去掉代码围栏） */
  optimized: string
  onClose: () => void
  /** 用户确认后应用新版内容 */
  onApply: (content: string) => void
}

/** 中文文本以字符级对比更准确；长文本计算稍慢，但由组件的 Web Worker 异步完成。 */
const DIFF_STYLES: ReactDiffViewerStylesOverride = {
  contentText: {
    fontFamily: 'Menlo, Consolas, monospace',
    fontSize: 12,
    lineHeight: 1.6,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    // 标题栏里的 <pre> 默认带 1em 边距，会把标题顶出固定高度的标题块
    margin: 0,
  },
  // 标题块默认固定 2.4em 高并裁切溢出内容，行高稍大就会把标题切掉一半
  titleBlock: {
    height: 'auto',
    minHeight: '2.4em',
    overflow: 'visible',
  },
}

/** AI 优化结果的逐行对比：左原版、右新版，确认后才允许应用。 */
export default function OptimizerCompareModal({
  open,
  original,
  optimized,
  onClose,
  onApply,
}: OptimizerCompareModalProps) {
  return (
    <Modal
      title="对比修改"
      open={open}
      onCancel={onClose}
      onOk={() => onApply(optimized)}
      okText="确认并应用"
      cancelText="取消"
      okButtonProps={{ icon: <CheckOutlined /> }}
      width={1080}
      zIndex={1300}
      destroyOnHidden
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Typography.Text type="secondary">
          左侧为原版，右侧为 AI 优化版；深色块标出字符级改动。确认后将替换当前编辑内容，仍需手动保存。
        </Typography.Text>
        <Space size={16} wrap>
          <Typography.Text>
            原版 <Typography.Text strong>{original.length}</Typography.Text> 字
          </Typography.Text>
          <Typography.Text>
            新版 <Typography.Text strong>{optimized.length}</Typography.Text> 字
          </Typography.Text>
        </Space>

        <div className="compare-body">
          <ReactDiffViewer
            oldValue={original}
            newValue={optimized}
            splitView
            compareMethod={DiffMethod.CHARS}
            leftTitle="原版"
            rightTitle="AI 优化版"
            showDiffOnly={false}
            hideSummary
            useDarkTheme={false}
            styles={DIFF_STYLES}
            loadingElement={() => (
              <Typography.Text type="secondary">
                正在计算差异…
              </Typography.Text>
            )}
          />
        </div>
      </Space>
    </Modal>
  )
}
