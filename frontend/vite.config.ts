import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发环境将 API 与上传文件请求代理到本地 FastAPI（8123），前后端同源，无需 CORS
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8123',
      '/uploads': 'http://127.0.0.1:8123',
    },
  },
})
