/**
 * 聊天状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChatMessage } from '../types'

export const useChatStore = defineStore('chat', () => {
  // State
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const currentResponse = ref('')
  const isConnected = ref(false)

  // Getters
  const messageCount = computed(() => messages.value.length)
  const lastMessage = computed(() => messages.value[messages.value.length - 1] || null)

  // Actions
  const addMessage = (message: Omit<ChatMessage, 'id' | 'timestamp'>) => {
    messages.value.push({
      id: `msg-${Date.now()}-${Math.random()}`,
      timestamp: new Date().toISOString(),
      ...message,
    })
  }

  const addUserMessage = (content: string) => {
    addMessage({
      role: 'user',
      content,
    })
  }

  const startStreaming = () => {
    isStreaming.value = true
    currentResponse.value = ''
  }

  const appendToStream = (text: string) => {
    currentResponse.value += text
  }

  const completeStream = () => {
    if (currentResponse.value) {
      addMessage({
        role: 'assistant',
        content: currentResponse.value,
      })
    }
    // 立即清空流式状态，避免重复显示
    isStreaming.value = false
    currentResponse.value = ''
  }

  const setConnectionStatus = (status: boolean) => {
    isConnected.value = status
  }

  const clearMessages = () => {
    messages.value = []
  }

  const getLastStreamingMessage = () => {
    return {
      role: 'assistant' as const,
      content: currentResponse.value,
      streaming: true,
    }
  }

  return {
    // State
    messages,
    isStreaming,
    currentResponse,
    isConnected,

    // Getters
    messageCount,
    lastMessage,

    // Actions
    addMessage,
    addUserMessage,
    startStreaming,
    appendToStream,
    completeStream,
    setConnectionStatus,
    clearMessages,
    getLastStreamingMessage,
  }
})
