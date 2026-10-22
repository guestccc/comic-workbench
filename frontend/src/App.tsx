import { Layout, Menu, Typography } from 'antd'
import {
  BookOutlined,
  EditOutlined,
  SendOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import PostsPage from './pages/PostsPage'
import SettingsPage from './pages/SettingsPage'
import StoriesPage from './pages/StoriesPage'

const { Sider, Content, Header } = Layout

const menuItems: MenuProps['items'] = [
  { key: '/settings', icon: <EditOutlined />, label: '启动提示词' },
  { key: '/stories', icon: <BookOutlined />, label: '故事管理' },
  { key: '/posts', icon: <SendOutlined />, label: '发文管理' },
]

const pageTitles: Record<string, string> = {
  '/settings': '启动提示词与生成配置',
  '/stories': '故事库',
  '/posts': '小红书发文',
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
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ borderInlineEnd: 'none' }}
        />
        <div className="sider-footer">本地工作台 · 数据保存在 SQLite</div>
      </Sider>

      <Layout>
        <Header className="app-header">
          <Typography.Text type="secondary">
            {pageTitles[location.pathname] ?? '条漫工作台'}
          </Typography.Text>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Navigate to="/settings" replace />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/stories" element={<StoriesPage />} />
            <Route path="/posts" element={<PostsPage />} />
            <Route path="*" element={<Navigate to="/settings" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
