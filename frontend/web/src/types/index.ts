/**
 * 类型定义
 */

// WebSocket 消息类型
export interface WebSocketMessage {
  type: string
  [key: string]: any
}

export interface UserMessage extends WebSocketMessage {
  type: 'user_message'
  content: string
}

export interface AssistantDeltaEvent extends WebSocketMessage {
  type: 'assistant_delta'
  text: string
}

export interface AssistantCompleteEvent extends WebSocketMessage {
  type: 'assistant_complete'
  message: {
    role: 'assistant'
    content: string
  }
}

export interface PermissionRequestEvent extends WebSocketMessage {
  type: 'permission_request'
  request_id: string
  tool_name: string
  tool_input: any
}

export interface ReadyEvent extends WebSocketMessage {
  type: 'ready'
  data: {
    session_id: string
    message: string
  }
}

// 聊天消息类型
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  timestamp: string
  streaming?: boolean
  toolCall?: {
    name: string
    input: any
    output?: any
    isError?: boolean
  }
}

// API 响应类型
export interface ApiResponse<T = any> {
  success: boolean
  data?: T
  message?: string
}

export interface SessionInfo {
  session_id: string
  created_at: string
  model: string
  status: 'active' | 'inactive' | 'error'
  message_count?: number
}

export interface ConfigInfo {
  model: string
  provider: string
  permission_mode: string
  theme: string
  max_turns: number
  max_tokens: number
}

export interface ModelInfo {
  id: string
  name: string
  provider: string
}
