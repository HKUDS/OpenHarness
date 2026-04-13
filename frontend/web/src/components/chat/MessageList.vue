<template>
  <div class="message-list" ref="messagesContainer">
    <div v-if="messages.length === 0" class="empty-state">
      <n-empty
        description="开始与 AI 对话吧！"
        size="large"
      >
        <template #icon>
          <span style="font-size: 3rem;">💬</span>
        </template>
      </n-empty>
    </div>

    <div v-else class="messages-container">
      <!-- 显示历史消息 -->
      <div
        v-for="message in props.messages"
        :key="message.id"
        :class="['message-item', `message-${message.role}`]"
      >
        <!-- 用户消息 -->
        <div v-if="message.role === 'user'" class="user-message">
          <div class="message-header">
            <n-tag size="small" type="info">用户</n-tag>
            <span class="message-time">{{ formatTime(message.timestamp) }}</span>
          </div>
          <div class="message-content user-content">
            {{ message.content }}
          </div>
        </div>

        <!-- AI 消息 -->
        <div v-else-if="message.role === 'assistant'" class="assistant-message">
          <div class="message-header">
            <n-space align="center" :size="8">
              <n-tag size="small" type="success" :bordered="false">AI 助手</n-tag>
            </n-space>
            <span class="message-time">{{ formatTime(message.timestamp) }}</span>
          </div>
          <div class="message-content assistant-content" :class="{ 'streaming-active': message.streaming }">
            <MarkdownText v-if="!message.streaming" :content="message.content" />
            <div v-else class="streaming-text">
              {{ message.content }}
              <span class="streaming-cursor">▌</span>
            </div>
          </div>
        </div>

        <!-- 系统消息 -->
        <div v-else-if="message.role === 'system'" class="system-message">
          <n-alert type="info" :title="message.content" size="small" />
        </div>

        <!-- 工具调用消息 -->
        <div v-else-if="message.role === 'tool'" class="tool-message">
          <div class="tool-compact">
            <div
              class="tool-compact-header"
              @click="toggleToolExpand(message.id)"
            >
              <n-space align="center" :size="8">
                <span class="expand-icon">{{ expandedToolMessages.has(message.id) ? '▼' : '▶' }}</span>
                <span class="tool-icon-small">🔧</span>
                <n-text strong style="font-size: 0.875rem;">
                  {{ message.toolCall?.name || 'Unknown Tool' }}
                </n-text>
                <n-tag
                  :type="message.toolCall?.isError ? 'error' : 'success'"
                  size="tiny"
                  bordered
                >
                  {{ message.toolCall?.isError ? '失败' : '成功' }}
                </n-tag>
              </n-space>
              <span class="message-time" style="font-size: 0.75rem;">{{ formatTime(message.timestamp) }}</span>
            </div>

            <!-- 折叠内容 -->
            <div v-show="expandedToolMessages.has(message.id)" class="tool-compact-content">
              <!-- 输入参数 -->
              <div class="tool-section-small">
                <div class="tool-section-header-small">
                  <span>📥</span>
                  <n-text style="font-size: 0.8rem;">输入参数</n-text>
                </div>
                <n-code
                  :code="formatJSON(message.toolCall?.input)"
                  language="json"
                  size="small"
                />
              </div>

              <!-- 输出结果 -->
              <div v-if="message.toolCall?.output" class="tool-section-small">
                <div class="tool-section-header-small">
                  <span>📤</span>
                  <n-text style="font-size: 0.8rem;">执行结果</n-text>
                </div>
                <n-code
                  :code="formatJSON(message.toolCall?.output)"
                  language="json"
                  size="small"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 流式回复 - 独立显示，不触发列表重新渲染 -->
      <div v-if="props.isStreaming && props.currentResponse" class="streaming-response-container">
        <div class="message-item message-assistant">
          <div class="assistant-message streaming-active">
            <div class="message-header">
              <n-space align="center" :size="8">
                <n-tag size="small" type="success" :bordered="false">AI 助手</n-tag>
              </n-space>
            </div>
            <div class="message-content assistant-content streaming-active">
              <div class="streaming-text">
                {{ props.currentResponse }}
                <span class="streaming-cursor">▌</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { NEmpty, NTag, NAlert, NSpace, NText, NCode } from 'naive-ui'
import MarkdownText from './MarkdownText.vue'
import type { ChatMessage } from '../../types'

const props = defineProps<{
  messages: ChatMessage[]
  isStreaming?: boolean
  currentResponse?: string
}>()

const emit = defineEmits<{
  scrollToEnd: []
}>()

const messagesContainer = ref<HTMLElement | null>(null)

// 工具消息展开状态
const expandedToolMessages = ref<Set<string>>(new Set())

// 切换工具消息展开状态
const toggleToolExpand = (messageId: string) => {
  if (expandedToolMessages.value.has(messageId)) {
    expandedToolMessages.value.delete(messageId)
  } else {
    expandedToolMessages.value.add(messageId)
  }
  // 触发响应式更新
  expandedToolMessages.value = new Set(expandedToolMessages.value)
}

// 自动滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 监听消息变化，自动滚动
watch(
  () => [props.messages.length, props.isStreaming, props.currentResponse],
  () => {
    scrollToBottom()
    emit('scrollToEnd')
  }
)

// 格式化时间
const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

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
</script>

<style scoped>
.message-list {
  height: 100%;
  overflow-y: auto;
  padding: 0;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.messages-container {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 0.5rem;
}

.message-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(15px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0 0.5rem;
}

.message-time {
  font-size: 0.75rem;
  opacity: 0.6;
  font-weight: 500;
}

.user-message {
  align-items: flex-end;
}

.user-content {
  background: transparent;
  color: var(--n-text-color);
  padding: 0.75rem 1rem;
  border-radius: 12px;
  max-width: 70%;
  word-break: break-word;
  border: 1px solid var(--n-border-color);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
}

.user-content:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

.assistant-message {
  align-items: flex-start;
}

.assistant-content {
  background: var(--n-card-color);
  border: 1px solid var(--n-border-color);
  padding: 1rem 1.25rem;
  border-radius: 18px 18px 18px 4px;
  max-width: 85%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
  position: relative;
}

.assistant-content:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

/* 流式回复时的样式覆盖 */
.assistant-content.streaming-active:hover {
  transform: none;
  box-shadow: 0 2px 12px rgba(102, 126, 234, 0.15);
}

.system-message {
  align-items: center;
}

.tool-message {
  align-items: flex-start;
  width: 100%;
  max-width: 90%;
}

/* 工具卡片样式 */
.tool-compact {
  background: var(--n-card-color);
  border: 1px solid var(--n-border-color);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
  animation: slideIn 0.3s ease-out;
}

.tool-compact:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(-10px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.tool-compact-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  user-select: none;
  background: rgba(102, 126, 234, 0.03);
  transition: background 0.2s ease;
}

.tool-compact-header:hover {
  background: rgba(102, 126, 234, 0.06);
}

.expand-icon {
  font-size: 0.75rem;
  color: var(--n-text-color);
  transition: transform 0.2s ease;
  margin-right: 0.25rem;
}

.tool-icon-small {
  font-size: 0.875rem;
}

.tool-compact-content {
  padding: 0.75rem;
  border-top: 1px solid var(--n-border-color);
  background: var(--n-color);
}

.tool-section-small {
  margin-bottom: 0.75rem;
}

.tool-section-small:last-child {
  margin-bottom: 0;
}

.tool-section-header-small {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
  font-size: 0.8rem;
  color: var(--n-text-color);
  opacity: 0.8;
}

/* 代码块美化 */
:deep(.n-code) {
  border-radius: 6px;
  font-size: 0.75rem;
  line-height: 1.5;
}

:deep(.n-code__content) {
  background: var(--n-code-color) !important;
  padding: 0.75rem;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
}

/* 小工具代码块 */
.tool-section-small :deep(.n-code) {
  font-size: 0.7rem;
  line-height: 1.4;
}

.tool-section-small :deep(.n-code__content) {
  padding: 0.5rem;
  max-height: 150px;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 正在回复的消息样式 */
.streaming-active {
  position: relative;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
  border-color: rgba(102, 126, 234, 0.3);
  box-shadow: 0 2px 12px rgba(102, 126, 234, 0.15);
  z-index: 1;
}

/* 流式回复容器 - 独立于消息列表，避免重新渲染 */
.streaming-response-container {
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.streaming-active::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #667eea, #764ba2, #667eea);
  background-size: 200% 100%;
  animation: shimmer 2s ease-in-out infinite;
  border-radius: 12px 12px 0 0;
}

@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

.streaming-text {
  line-height: 1.8;
  word-wrap: break-word;
  white-space: pre-wrap;
  min-height: 1.8em;
}

/* Markdown 内容美化 */
:deep(.markdown-content) {
  line-height: 1.8;
}

:deep(.markdown-content h1),
:deep(.markdown-content h2),
:deep(.markdown-content h3) {
  margin-top: 1rem;
  margin-bottom: 0.75rem;
  font-weight: 600;
}

:deep(.markdown-content p) {
  margin-bottom: 0.75rem;
}

:deep(.markdown-content code) {
  background: rgba(0, 0, 0, 0.05);
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  font-size: 0.9em;
}

:deep(.markdown-content pre) {
  background: var(--n-code-color);
  padding: 1rem;
  border-radius: 8px;
  overflow-x: auto;
  margin: 0.75rem 0;
}

/* 标签美化 */
:deep(.n-tag) {
  border-radius: 6px;
  font-weight: 500;
}

/* 滚动条美化 */
.message-list::-webkit-scrollbar {
  width: 6px;
}

.message-list::-webkit-scrollbar-track {
  background: transparent;
}

.message-list::-webkit-scrollbar-thumb {
  background: var(--n-scrollbar-color);
  border-radius: 3px;
}

.message-list::-webkit-scrollbar-thumb:hover {
  background: var(--n-scrollbar-color-hover);
}

/* 流动指示点动画 */
@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(1.2);
  }
}

.streaming-cursor {
  animation: blink 1s step-end infinite;
  margin-left: 2px;
  color: var(--n-primary-color);
}

@keyframes blink {
  0%, 50% {
    opacity: 1;
  }
  51%, 100% {
    opacity: 0;
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .tool-message {
    max-width: 95%;
  }

  .tool-card-header {
    padding: 0.75rem;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .tool-section {
    margin-bottom: 0.75rem;
  }

  .tool-section-content {
    padding: 0 0.5rem;
  }

  :deep(.n-code) {
    font-size: 0.8rem;
  }

  :deep(.n-code__content) {
    padding: 0.75rem;
  }
}
</style>
