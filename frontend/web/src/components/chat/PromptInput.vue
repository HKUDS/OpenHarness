<template>
  <div class="prompt-input">
    <!-- 输入区域 -->
    <n-space vertical :size="8">
      <n-input-group>
        <n-input
          ref="inputRef"
          v-model:value="inputText"
          type="textarea"
          :placeholder="placeholder"
          :disabled="disabled || isSending"
          :autosize="{ minRows: 1, maxRows: 4 }"
          @keydown="handleKeyDown"
        />
        <n-button
          type="primary"
          :disabled="!canSend"
          @click="sendMessage"
          class="send-button"
          circle
        >
          <span v-if="!isSending" class="send-icon">➤</span>
          <span v-else class="loading-icon">⏳</span>
        </n-button>
      </n-input-group>
    </n-space>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { NInput, NButton, NSpace, NInputGroup } from 'naive-ui'

const props = defineProps<{
  disabled?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  send: [message: string]
  openHistory: []
}>()

const inputRef = ref()
const inputText = ref('')
const isSending = ref(false)

const canSend = computed(() => {
  return !props.disabled && inputText.value.trim().length > 0 && !isSending.value
})

const handleKeyDown = (event: KeyboardEvent) => {
  // Enter 直接发送消息
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
  // Shift+Enter 换行（默认行为，不需要阻止）
}

const sendMessage = async () => {
  if (!canSend.value) return

  const message = inputText.value.trim()
  if (!message) return

  isSending.value = true
  emit('send', message)

  // 清空输入框
  inputText.value = ''

  // 重新聚焦到输入框
  nextTick(() => {
    inputRef.value?.focus()
  })
}

// 重置发送状态
const resetSending = () => {
  isSending.value = false
}

// 暴露方法给父组件
defineExpose({
  focus: () => {
    inputRef.value?.focus()
  },
  resetSending
})
</script>

<style scoped>
.prompt-input {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.input-card {
  width: 100%;
  border: none;
  box-shadow: none;
  background: transparent;
  padding: 0;
}

:deep(.input-card .n-card__content) {
  padding: 0;
}

.send-button {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  vertical-align: bottom;
}

.send-icon {
  font-size: 1rem;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transform: translateX(1px);
}

.loading-icon {
  font-size: 1rem;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.1);
  }
}

.toolbar {
  display: none; /* 隐藏工具栏让输入框更紧凑 */
}

/* 深度选择器美化 */
:deep(.n-input-group) {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
}

:deep(.n-input) {
  flex: 1;
  display: flex;
  align-items: flex-end;
}

:deep(.n-input__wrapper) {
  width: 100%;
}

:deep(.n-input__textarea-el) {
  border-radius: 8px;
  font-size: 0.875rem;
  line-height: 1.5;
  padding: 0.5rem 0.75rem;
  min-height: 40px !important;
  max-height: 120px;
  box-sizing: border-box;
}

:deep(.n-input__border),
:deep(.n-input__state-border) {
  border-radius: 8px;
}

:deep(.n-button) {
  height: 40px;
  width: 40px;
  padding: 0;
  flex-shrink: 0;
  margin: 0;
}

:deep(.n-button__content) {
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
}

:deep(.n-button--primary) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
}

:deep(.n-button--primary:hover) {
  background: linear-gradient(135deg, #5568d3 0%, #65408b 100%);
  transform: scale(1.05);
}

:deep(.n-button--primary:active) {
  transform: scale(0.95);
}

:deep(.n-button--disabled) {
  opacity: 0.5;
}

:deep(.n-text) {
  font-size: 0.875rem;
}

:deep(.n-space) {
  gap: 0.5rem !important;
}
</style>
