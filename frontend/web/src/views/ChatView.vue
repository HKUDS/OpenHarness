<template>
  <div class="chat-view">
    <!-- 主要聊天区域 -->
    <div class="chat-content">
      <n-layout has-sider class="main-layout">
        <!-- 侧边栏 -->
        <n-layout-sider
          :collapsed-width="0"
          :width="280"
          :collapsed="sidebarCollapsed"
          show-trigger="arrow-circle"
          collapse-mode="width"
          bordered
          class="chat-sidebar"
          @collapse="sidebarCollapsed = true"
          @expand="sidebarCollapsed = false"
        >
          <div class="sidebar-content">
            <!-- Logo 和标题 -->
            <div class="sidebar-header">
              <div class="logo-section">
                <span class="logo-icon">🤖</span>
                <n-text strong style="font-size: 1.1rem;">
                  OpenHarness
                </n-text>
              </div>
            </div>

            <n-divider />

            <!-- 新建对话按钮 -->
            <n-space vertical size="large" style="width: 100%;">
              <n-button
                type="primary"
                size="large"
                @click="createNewChat"
                block
                strong
              >
                <template #icon>
                  <span style="font-size: 1.1rem;">➕</span>
                </template>
                新建对话
              </n-button>
            </n-space>

            <n-divider />

            <!-- 最近对话 -->
            <div class="recent-chats">
              <n-text depth="3" style="font-size: 0.85rem; margin-bottom: 0.75rem;">
                最近对话
              </n-text>
              <n-scrollbar style="max-height: calc(100vh - 350px);">
                <n-list>
                  <n-list-item
                    v-for="chat in recentChats"
                    :key="chat.id"
                    clickable
                    :class="{ 'active-chat': chat.id === sessionId }"
                    @click="switchChat(chat.id)"
                  >
                    <n-space align="center" justify="space-between">
                      <n-space align="center">
                        <span class="chat-icon">💬</span>
                        <n-text>{{ chat.title }}</n-text>
                      </n-space>
                      <n-text depth="3" style="font-size: 0.75rem;">
                        {{ chat.time }}
                      </n-text>
                    </n-space>
                  </n-list-item>
                </n-list>
              </n-scrollbar>
            </div>
          </div>
        </n-layout-sider>

        <!-- 聊天主区域 -->
        <n-layout-content class="chat-main-layout">
          <!-- 侧边栏展开按钮（当侧边栏收起时显示） -->
          <div v-if="sidebarCollapsed" class="sidebar-expand-button" @click="sidebarCollapsed = false">
            <span class="expand-icon">▶</span>
          </div>

          <div class="chat-messages">
            <!-- 消息列表 -->
            <MessageList
              :messages="messages"
              :is-streaming="isStreaming"
              :current-response="currentResponse"
            />
          </div>
        </n-layout-content>

        <!-- 悬浮输入区域 -->
        <div class="chat-input-floating">
          <div class="input-container">
            <PromptInput
              ref="promptInputRef"
              placeholder="输入你的消息... (Enter 发送，Shift+Enter 换行)"
              @send="handleSendMessage"
              @open-history="showHistory = true"
            />
          </div>
        </div>
      </n-layout>
    </div>

    <!-- 工具权限确认对话框 -->
    <n-modal
      v-model:show="permissionDialog.dialogVisible.value"
      preset="card"
      title="工具执行权限请求"
      :bordered="false"
      :closable="false"
      :mask-closable="false"
      style="width: 600px; max-width: 90vw;"
    >
      <div v-if="permissionDialog.currentPermissionRequest.value" class="permission-dialog">
        <!-- 工具信息 -->
        <div class="permission-header">
          <n-space align="center">
            <span class="tool-icon">🔧</span>
            <n-text strong style="font-size: 1.1rem;">
              {{ permissionDialog.currentPermissionRequest.value.tool_name }}
            </n-text>
            <n-tag type="warning" size="small">请求执行权限</n-tag>
          </n-space>
        </div>

        <n-divider />

        <!-- 输入参数 -->
        <div class="permission-content">
          <n-space vertical size="large">
            <div>
              <n-text strong style="display: block; margin-bottom: 0.5rem;">
                📋 输入参数
              </n-text>
              <n-card size="small" embedded>
                <n-code
                  :code="formatJSON(permissionDialog.currentPermissionRequest.value.tool_input)"
                  language="json"
                />
              </n-card>
            </div>

            <!-- 安全提示 -->
            <n-alert type="warning" :show-icon="true">
              <template #header>
                <n-text strong>⚠️ 安全提示</n-text>
              </template>
              请仔细检查工具的输入参数，确认此操作的安全性。
              恶意或错误的参数可能导致系统安全问题或数据损坏。
            </n-alert>
          </n-space>
        </div>

        <!-- 操作按钮 -->
        <div class="permission-actions">
          <n-space justify="end">
            <n-button
              size="large"
              @click="handlePermissionDialog(false)"
              style="border-radius: 8px;"
            >
              ❌ 拒绝执行
            </n-button>
            <n-button
              type="primary"
              size="large"
              @click="handlePermissionDialog(true)"
              style="border-radius: 8px;"
            >
              ✅ 允许执行
            </n-button>
          </n-space>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import {
  NLayout,
  NLayoutSider,
  NLayoutContent,
  NSpace,
  NText,
  NButton,
  NModal,
  NDivider,
  NTag,
  NList,
  NListItem,
  NScrollbar,
  NCard,
  NCode,
  NAlert
} from 'naive-ui'
import MessageList from '../components/chat/MessageList.vue'
import PromptInput from '../components/chat/PromptInput.vue'
import { useChatWebSocket } from '../composables/useChatWebSocket'
import { useChatStore } from '../stores/chat'
import { getCurrentPermissionDialog } from '../composables/usePermissionDialog'

// WebSocket 状态
const wsState = useChatWebSocket()
const chatStore = useChatStore()

// 权限对话框
const permissionDialog = getCurrentPermissionDialog()

// 格式化 JSON 显示
const formatJSON = (data: any) => {
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data)
      return JSON.stringify(parsed, null, 2)
    } catch {
      return data
    }
  }
  return JSON.stringify(data, null, 2)
}

// 处理权限对话框响应
const handlePermissionDialog = (confirmed: boolean) => {
  permissionDialog.handlePermissionResponse(confirmed)
}

// 组件引用
const promptInputRef = ref()

// UI 状态
const sidebarCollapsed = ref(false)

// 最近对话数据
const recentChats = ref([
  {
    id: 'session-1',
    title: 'AI 编程助手',
    time: '2分钟前'
  },
  {
    id: 'session-2',
    title: '代码审查',
    time: '1小时前'
  },
  {
    id: 'session-3',
    title: '架构设计讨论',
    time: '昨天'
  }
])

// 计算属性
const messages = computed(() => chatStore.messages)
const isStreaming = computed(() => chatStore.isStreaming)
const currentResponse = computed(() => chatStore.currentResponse)
const sessionId = ref('session-' + Date.now().toString(36))

// 监听流式回复状态变化
watch(isStreaming, (newValue, oldValue) => {
  // 当从正在回复变为回复完成时，重置发送按钮状态
  if (oldValue === true && newValue === false) {
    promptInputRef.value?.resetSending()
  }
})

// 方法
const handleSendMessage = async (message: string) => {
  console.log('Sending message:', message)
  await wsState.sendMessage(message)
  // 自动聚焦回输入框
  promptInputRef.value?.focus()
}

const createNewChat = () => {
  // 清空当前对话
  chatStore.clearMessages()
  // 生成新的会话ID
  sessionId.value = 'session-' + Date.now().toString(36)
  console.log('Created new chat:', sessionId.value)
}

const switchChat = (chatId: string) => {
  console.log('Switching to chat:', chatId)
  // TODO: 实现对话切换逻辑
  sessionId.value = chatId
}

// 删除不需要的处理器，已经通过内联处理

// 生命周期
onMounted(async () => {
  console.log('ChatView mounted, connecting to WebSocket...')
  await wsState.connect()
})

onUnmounted(() => {
  wsState.disconnect()
})
</script>

<style scoped>
.chat-view {
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--n-color);
  margin: 0;
  padding: 0;
  overflow: hidden;
  position: fixed;
  top: 0;
  left: 0;
}

.chat-header {
  padding: 1.25rem 1.5rem;
  background: var(--n-card-color);
  border-bottom: 1px solid var(--n-border-color);
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.header-left h2 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.chat-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.main-layout {
  height: 100% !important;
  display: flex !important;
  min-height: 0;
}

.chat-sidebar {
  height: 100%;
  overflow-y: auto;
  background: var(--n-color);
  border-right: 1px solid var(--n-border-color);
}

.sidebar-content {
  padding: 1.25rem;
  height: 100%;
}

.chat-main-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--n-color);
  position: relative;
  min-height: 0;
}

/* 侧边栏展开按钮 */
.sidebar-expand-button {
  position: fixed;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  width: 40px;
  height: 40px;
  background: var(--n-card-color);
  border: 1px solid var(--n-border-color);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;
}

.sidebar-expand-button:hover {
  background: var(--n-color);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transform: translateY(-50%) scale(1.05);
}

.sidebar-expand-button:active {
  transform: translateY(-50%) scale(0.95);
}

.sidebar-expand-button .expand-icon {
  font-size: 1rem;
  color: var(--n-text-color);
  font-weight: 600;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 1.5rem;
  background: var(--n-color);
  min-height: 0;
  padding-bottom: 140px; /* 为悬浮输入框留出空间 */
}

/* 悬浮输入框容器 */
.chat-input-floating {
  position: fixed;
  bottom: 2rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  width: 90%;
  max-width: 700px;
}

.input-container {
  background: rgba(var(--n-card-color), 0.95);
  border: 1px solid var(--n-border-color);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(10px);
  padding: 0.75rem;
  transition: all 0.3s ease;
}

.input-container:hover {
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  transform: translateY(-2px);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .chat-input-floating {
    width: 95%;
    bottom: 1rem;
  }

  .chat-messages {
    padding-bottom: 120px;
  }

  .sidebar-expand-button {
    left: 8px;
    width: 36px;
    height: 36px;
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .chat-header {
    padding: 1rem;
  }

  .chat-header .header-left h2 {
    font-size: 1.25rem;
  }

  .chat-messages {
    padding: 1rem;
  }

  .header-right {
    display: none;
  }
}

/* 卡片美化 */
:deep(.n-card) {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  transition: all 0.3s ease;
}

:deep(.n-card:hover) {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

/* 按钮美化 */
:deep(.n-button) {
  border-radius: 8px;
  font-weight: 500;
  transition: all 0.2s ease;
}

:deep(.n-button:hover) {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

:deep(.n-button:active) {
  transform: translateY(0);
}

/* 输入框美化 */
:deep(.n-input) {
  border-radius: 10px;
}

:deep(.n-input__textarea) {
  border-radius: 10px;
}

/* 确保布局容器正确填充 */
:deep(.n-layout) {
  height: 100% !important;
  display: flex !important;
  min-height: 0 !important;
}

:deep(.n-layout-content) {
  flex: 1 !important;
  display: flex !important;
  flex-direction: column !important;
  overflow: hidden !important;
  padding: 0 !important;
  height: auto !important;
  min-height: 0 !important;
}

:deep(.n-layout-sider) {
  height: 100% !important;
  overflow: auto !important;
  min-height: 0 !important;
}

/* 移除所有可能的默认间距 */
:deep(.n-layout > *) {
  margin: 0 !important;
}

:deep(.n-layout-content > *) {
  margin: 0 !important;
}

/* 主布局特别处理 */
.main-layout :deep(.n-layout-content) {
  display: flex !important;
  flex-direction: column !important;
  height: auto !important;
  flex: 1 !important;
  min-height: 0 !important;
}

.chat-main-layout :deep(.chat-messages) {
  flex: 1 !important;
  overflow-y: auto !important;
  min-height: 0 !important;
}

.chat-main-layout :deep(.chat-input) {
  flex-shrink: 0 !important;
}

/* 空间优化 */
:deep(.n-space) {
  gap: 0.75rem !important;
}

/* 标签美化 */
:deep(.n-tag) {
  border-radius: 6px;
  font-weight: 500;
}

/* 统计数字美化 */
:deep(.n-statistic__label) {
  font-size: 0.875rem;
  font-weight: 500;
}

:deep(.n-statistic__value) {
  font-weight: 600;
}

/* 权限对话框样式 */
.permission-dialog {
  padding: 0.5rem 0;
}

.permission-header {
  padding: 1rem;
  background: linear-gradient(135deg, #f6f8fc 0%, #e9ecef 100%);
  border-radius: 8px;
  margin-bottom: 1rem;
}

.tool-icon {
  font-size: 1.5rem;
  margin-right: 0.5rem;
}

.permission-content {
  padding: 0 0.5rem;
}

.permission-actions {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--n-border-color);
}

/* 代码块美化 */
:deep(.n-code) {
  border-radius: 8px;
  font-size: 0.875rem;
  line-height: 1.6;
}

:deep(.n-code__content) {
  background: var(--n-code-color) !important;
  padding: 1rem;
  border-radius: 8px;
  max-height: 300px;
  overflow-y: auto;
}

/* 警告框美化 */
:deep(.n-alert) {
  border-radius: 8px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  :deep(.n-code__content) {
    max-height: 200px;
    font-size: 0.8rem;
    padding: 0.75rem;
  }
}
</style>
