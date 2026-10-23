import { Layout, Menu, Typography } from 'antd'
import {
  BookOutlined,
  EditOutlined,
  SendOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import PostsPage from './pages/PostsPage'
import PromptPage from './pages/PromptPage'
import SettingsPage from './pages/SettingsPage'
import StoriesPage from './pages/StoriesPage'
import StoryDetailPage from './pages/StoryDetailPage'

const { Sider, Content, Header } = Layout

const menuItems: MenuProps['items'] = [
  { key: '/prompt', icon: <EditOutlined />, label: '启动提示词' },
  { key: '/stories', icon: <BookOutlined />, label: '故事管理' },
  { key: '/posts', icon: <SendOutlined />, label: '发文管理' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

const pageTitles: Record<string, string> = {
  '/prompt': '启动提示词与画风配置',
  '/stories': '故事库',
  '/posts': '小红书发文',
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

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key)
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="light" className="app-sider">
        <div className="brand">
          <span className="brand-dot" />
          <div>
            <Typography.Text strong>条漫工作台</Typography.Text>
            <div className="brand-sub">Comic Studio</div>
          </div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[resolveMenuKey(location.pathname)]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ borderInlineEnd: 'none' }}
        />
        <div className="sider-footer">本地工作台 · 数据保存在 SQLite</div>
      </Sider>

      <Layout>
        <Header className="app-header">
          <Typography.Text type="secondary">
            {resolvePageTitle(location.pathname)}
          </Typography.Text>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Navigate to="/prompt" replace />} />
            <Route path="/prompt" element={<PromptPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/stories" element={<StoriesPage />} />
            <Route path="/stories/:id" element={<StoryDetailPage />} />
            <Route path="/posts" element={<PostsPage />} />
            <Route path="*" element={<Navigate to="/prompt" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
