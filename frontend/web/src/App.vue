<template>
  <n-config-provider :theme="theme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <div id="app" class="open-harness-web">
            <!-- 聊天界面占据整个页面 -->
            <ChatView />
          </div>
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  NNotificationProvider,
  darkTheme,
  type GlobalTheme
} from 'naive-ui'
import ChatView from './views/ChatView.vue'

// 从 localStorage 初始化主题，避免闪烁
const savedTheme = typeof localStorage !== 'undefined' ? localStorage.getItem('theme') : null
const isDarkTheme = ref(savedTheme === null ? true : savedTheme === 'dark')

// 主题配置
const theme = computed<GlobalTheme | null>(() => isDarkTheme.value ? darkTheme : null)

const themeOverrides = {
  common: {
    primaryColor: '#667eea',
    primaryColorHover: '#5568d3',
    primaryColorPressed: '#4c5fc2',
    primaryColorSuppl: '#5568d3',
    borderRadius: '8px',
    lineHeight: '1.6',
  },
  Card: {
    borderRadius: '12px',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
  },
  Button: {
    borderRadiusMedium: '8px',
    fontWeightStrong: '600',
  },
  Input: {
    borderRadius: '10px',
  }
}
</script>

<style scoped>
.open-harness-web {
  width: 100vw;
  height: 100vh;
  margin: 0;
  padding: 0;
  overflow: hidden;
  position: fixed;
  top: 0;
  left: 0;
}
</style>
