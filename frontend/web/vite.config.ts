import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // WebSocket 代理
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true
      },
      // REST API 代理
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // 健康检查端点代理
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // 根路径端点代理
      '^/(docs|openapi.json)': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
