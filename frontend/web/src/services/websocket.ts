/**
 * WebSocket 服务 - 处理 WebSocket 连接和消息
 */

type WebSocketMessageHandler = (data: any) => void
type WebSocketErrorHandler = (error: Event) => void

export class WebSocketService {
  private ws: WebSocket | null = null
  private url: string
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 3000
  private messageHandlers: Map<string, Set<WebSocketMessageHandler>> = new Map()
  private errorHandlers: Set<WebSocketErrorHandler> = new Set()

  constructor(url: string) {
    this.url = url
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url)

        this.ws.onopen = () => {
          console.log('WebSocket connected successfully')
          this.reconnectAttempts = 0
          resolve()
        }

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            this.handleMessage(data)
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error)
          }
        }

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error)
          this.errorHandlers.forEach(handler => handler(error))
          reject(error)
        }

        this.ws.onclose = () => {
          console.log('WebSocket connection closed')
          this.attemptReconnect()
        }
      } catch (error) {
        reject(error)
      }
    })
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`)
      setTimeout(() => {
        this.connect()
      }, this.reconnectDelay)
    } else {
      console.error('Max reconnection attempts reached')
    }
  }

  send(message: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      console.error('WebSocket is not connected')
    }
  }

  on(eventType: string, handler: WebSocketMessageHandler): void {
    if (!this.messageHandlers.has(eventType)) {
      this.messageHandlers.set(eventType, new Set())
    }
    this.messageHandlers.get(eventType)!.add(handler)
  }

  off(eventType: string, handler: WebSocketMessageHandler): void {
    const handlers = this.messageHandlers.get(eventType)
    if (handlers) {
      handlers.delete(handler)
    }
  }

  onError(handler: WebSocketErrorHandler): void {
    this.errorHandlers.add(handler)
  }

  private handleMessage(data: any): void {
    const eventType = data.type || 'message'
    const handlers = this.messageHandlers.get(eventType)

    if (handlers) {
      handlers.forEach(handler => handler(data))
    }

    // Also call general message handlers
    const generalHandlers = this.messageHandlers.get('*')
    if (generalHandlers) {
      generalHandlers.forEach(handler => handler(data))
    }
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN
  }
}

// 创建全局 WebSocket 服务实例
let wsService: WebSocketService | null = null

export function useWebSocket() {
  const connect = (url: string = 'ws://localhost:8000/ws') => {
    if (!wsService) {
      wsService = new WebSocketService(url)
    }
    return wsService.connect()
  }

  const send = (message: any) => {
    if (wsService) {
      wsService.send(message)
    }
  }

  const on = (eventType: string, handler: WebSocketMessageHandler) => {
    if (wsService) {
      wsService.on(eventType, handler)
    }
  }

  const disconnect = () => {
    if (wsService) {
      wsService.disconnect()
      wsService = null
    }
  }

  const isConnected = () => {
    return wsService?.isConnected ?? false
  }

  return {
    connect,
    send,
    on,
    disconnect,
    isConnected,
  }
}
