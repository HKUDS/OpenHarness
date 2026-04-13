/**
 * 聊天专用的 WebSocket 集成 - 单例模式
 */

import { ref } from 'vue'
import { useWebSocket as useWebSocketService } from '../services/websocket'
import { useChatStore } from '../stores/chat'
import { showPermissionDialog } from './usePermissionDialog'

// 单例状态
const isConnected = ref(false)
const isConnecting = ref(false)
const error = ref<string | null>(null)

export function useChatWebSocket() {
  const chatStore = useChatStore()

  // WebSocket 事件处理
  const setupEventHandlers = () => {
    const { on } = useWebSocketService()

    // 连接就绪事件
    on('ready', (data: any) => {
      console.log('WebSocket ready:', data)
      isConnected.value = true
      isConnecting.value = false
      chatStore.setConnectionStatus(true)
    })

    // 用户消息确认响应
    on('transcript_item', (data: any) => {
      console.log('后端->前端:', data)
    })

    // 流式响应
    on('assistant_delta', (data: any) => {
    console.log('接收WebSocket消息,assistant_delta:' + JSON.stringify(data))
      if (!chatStore.isStreaming) {
        chatStore.startStreaming()
      }
      chatStore.appendToStream(data.text)
    })

    // 响应完成
    on('assistant_complete', (data: any) => {
      console.log('接收WebSocket消息,assistant_complete:' + JSON.stringify(data)) 
      chatStore.completeStream()
    })

    // 工具调用开始
    on('tool_started', (data: any) => { 
      console.log('接收WebSocket消息,tool_started:' + JSON.stringify(data)) 
      // 暂时不添加消息，等待完成后再添加
    })

    // 工具调用完成
    on('tool_completed', (data: any) => {
      console.log('Tool completed:', data.tool_name, data)
      console.log('接收WebSocket消息,tool_completed:' + JSON.stringify(data)) 
      // 添加工具调用完成消息
      chatStore.addMessage({
        role: 'tool',
        content: `工具${data.is_error ? '执行失败' : '执行成功'}: ${data.tool_name}`,
        toolCall: {
          name: data.tool_name,
          input: data.tool_input || {},
          output: data.output,
          isError: data.is_error || false
        }
      })
    })

    // 权限请求
    on('permission_request', (data: any) => {
      console.log('Permission request:', data.tool_name)
      console.log('接收WebSocket消息,permission_request:' + JSON.stringify(data)) 
      handlePermissionRequest(data)
    })

    // 错误事件
    on('error', (data: any) => {
      console.error('WebSocket error:', data.message)
      error.value = data.message
    })

    // Pong 响应
    on('pong', () => {
      console.log('Pong received')
    })
  }

  // 处理权限请求
  const handlePermissionRequest = async (data: any) => {
    const { tool_name, tool_input, request_id } = data

    // 使用动态导入来避免循环依赖
    const { showPermissionDialog } = await import('./usePermissionDialog')
    const confirmed = await showPermissionDialog(request_id, tool_name, tool_input)

    // 发送权限（弹窗确认结果）
    const { send } = useWebSocketService()
    send({
      type: 'permission_response',
      request_id: request_id,
      allowed: confirmed
    })
  }

  // 连接到 WebSocket
  const connect = async (url: string = '/ws') => {
    try {
      isConnecting.value = true
      error.value = null

      // 使用代理路径
      const wsUrl = url.startsWith('ws://') ? url : `ws://localhost:8000${url}`

      await useWebSocketService().connect(wsUrl)
      setupEventHandlers()

    } catch (err) {
      console.error('WebSocket connection failed:', err)
      isConnecting.value = false
      isConnected.value = false
      error.value = '连接失败'
      chatStore.setConnectionStatus(false)
    }
  }

  // 发送用户消息
  const sendMessage = async (content: string) => {
    if (!isConnected.value) {
      error.value = '未连接到后端服务'
      return
    }

    try {
      // 添加用户消息到界面
      chatStore.addUserMessage(content)

      // 发送到 WebSocket
      const { send } = useWebSocketService()
      send({
        type: 'submit_line',
        content: content
      })

      error.value = null
    } catch (err) {
      console.error('Send message failed:', err)
      error.value = '发送消息失败'
    }
  }

  // 断开连接
  const disconnect = () => {
    useWebSocketService().disconnect()
    isConnected.value = false
    chatStore.setConnectionStatus(false)
  }

  // 重新连接
  const reconnect = () => {
    disconnect()
    connect()
  }

  return {
    isConnected,
    isConnecting,
    error,
    connect,
    sendMessage,
    disconnect,
    reconnect
  }
}
