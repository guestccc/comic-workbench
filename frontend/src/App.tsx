import { useEffect, useState } from 'react'
import {
  App as AntdApp,
  Button,
  FloatButton,
  Layout,
  Menu,
  Tooltip,
  Typography,
} from 'antd'
import {
  BookOutlined,
  BulbOutlined,
  CodeOutlined,
  EditOutlined,
  FileTextOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SendOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, getErrorMessage } from './api/client'
import DesignFeedbacksPage from './pages/DesignFeedbacksPage'
import PromptPage from './pages/PromptPage'
import PublishJobsPage from './pages/PublishJobsPage'
import SettingsPage from './pages/SettingsPage'
import StoriesPage from './pages/StoriesPage'
import StoryDetailPage from './pages/StoryDetailPage'

const { Sider, Content, Header } = Layout

/** 侧边栏收起状态只作为当前浏览器的界面偏好，不写后端。 */
const SIDER_COLLAPSED_KEY = 'comic-workbench:sider-collapsed'

function readSiderCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDER_COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

const menuItems: MenuProps['items'] = [
  { key: '/prompt', icon: <EditOutlined />, label: '启动提示词' },
  { key: '/stories', icon: <BookOutlined />, label: '故事管理' },
  { key: '/publish-jobs', icon: <SendOutlined />, label: '发布任务' },
  { key: '/design-feedbacks', icon: <BulbOutlined />, label: '设计建议' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
  { key: 'api-docs', icon: <FileTextOutlined />, label: '接口文档' },
]

const pageTitles: Record<string, string> = {
  '/prompt': '启动提示词与画风配置',
  '/stories': '故事库',
  '/publish-jobs': '发布任务',
  '/design-feedbacks': '设计建议',
  '/settings': '应用设置',
}

const menuKeys = Object.keys(pageTitles)

/**
 * 找出当前路径对应的菜单项。
 *
 * 详情页等子路由（如 /stories/12）需要高亮父级菜单，
 * 因此按路径前缀匹配，而不是只做全等比较。
 */
function resolveMenuKey(pathname: string): string {
  return (
    menuKeys.find(
      (key) => pathname === key || pathname.startsWith(`${key}/`),
    ) ?? pathname
  )
}

/** 详情页不在 menuItems 中，单独按前缀判断标题。 */
function resolvePageTitle(pathname: string): string {
  if (pathname.startsWith('/stories/')) return '故事详情'
  return pageTitles[pathname] ?? '条漫工作台'
}

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const { message } = AntdApp.useApp()
  const [collapsed, setCollapsed] = useState(readSiderCollapsed)
  const [openingTerminal, setOpeningTerminal] = useState(false)

  useEffect(() => {
    try {
      window.localStorage.setItem(
        SIDER_COLLAPSED_KEY,
        collapsed ? '1' : '0',
      )
    } catch {
      // localStorage 不可用时忽略，仅影响记忆，不影响收起功能
    }
  }, [collapsed])

  /** 终端由本机后端创建，前端只触发固定接口，不接触 shell。 */
  const handleOpenTerminal = async () => {
    setOpeningTerminal(true)
    try {
      const result = await api.openTerminal()
      message.success(result.message)
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setOpeningTerminal(false)
    }
  }

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'api-docs') {
      // 接口文档是后端 FastAPI 自动生成的页面，直接新开标签
      window.open('/docs', '_blank', 'noopener,noreferrer')
      return
    }
    navigate(key)
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={220}
        collapsedWidth={64}
        collapsible
        collapsed={collapsed}
        trigger={null}
        theme="light"
        className="app-sider"
      >
        <div className={`brand${collapsed ? ' brand-collapsed' : ''}`}>
          <span className="brand-dot" />
          {!collapsed && (
            <div>
              <Typography.Text strong>条漫工作台</Typography.Text>
              <div className="brand-sub">Comic Studio</div>
            </div>
          )}
        </div>
        <Menu
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={[resolveMenuKey(location.pathname)]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ borderInlineEnd: 'none' }}
        />
        {!collapsed && (
          <div className="sider-footer">本地工作台 · 数据保存在 SQLite</div>
        )}
      </Sider>

      <Layout>
        <Header className="app-header">
          <Button
            type="text"
            className="sider-toggle"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          />
          <Typography.Text type="secondary">
            {resolvePageTitle(location.pathname)}
          </Typography.Text>
          <div className="app-header-actions">
            <Tooltip title="在项目根目录打开终端并启动 Claude Code">
              <Button
                type="text"
                icon={<CodeOutlined />}
                loading={openingTerminal}
                onClick={handleOpenTerminal}
              >
                终端
              </Button>
            </Tooltip>
          </div>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Navigate to="/prompt" replace />} />
            <Route path="/prompt" element={<PromptPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/stories" element={<StoriesPage />} />
            <Route path="/stories/:id" element={<StoryDetailPage />} />
            <Route path="/publish-jobs" element={<PublishJobsPage />} />
            <Route
              path="/design-feedbacks"
              element={<DesignFeedbacksPage />}
            />
            <Route path="*" element={<Navigate to="/prompt" replace />} />
          </Routes>
        </Content>
      </Layout>

      {/* 全站共用：窗口滚动超过 400px 后显示，点击回到页面顶部 */}
      <FloatButton.BackTop
        type="primary"
        visibilityHeight={400}
        showProgress
        tooltip="回到顶部"
        aria-label="回到顶部"
      />
    </Layout>
  )
}
