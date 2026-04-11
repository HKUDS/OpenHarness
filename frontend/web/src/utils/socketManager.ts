import type { Socket } from 'socket.io-client';
import { io } from 'socket.io-client';

// Global socket reference for use outside of React components
let socketInstance: Socket | null = null;
let connectionAttempted = false;
let connectionListeners: Array<{
  event: string;
  handler: (...args: unknown[]) => void;
}> = [];

export function setSocketInstance(socket: Socket | null) {
  socketInstance = socket;
}

export function getSocketInstance(): Socket | null {
  return socketInstance;
}

export function isConnectionAttempted(): boolean {
  return connectionAttempted;
}

export function setConnectionAttempted(attempted: boolean) {
  connectionAttempted = attempted;
}

export function createSocket(connectionUrl: string): Socket {
  const socket = io(connectionUrl, {
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: Infinity,
    timeout: 20000,
    path: '/socket.io',
    autoConnect: true,
    forceNew: false,
  });
  
  // Enhanced error handling and reconnection
  socket.on('reconnect_attempt', (attemptNumber: number) => {
    console.log(`[WebSocket] Reconnection attempt ${attemptNumber}`);
  });
  
  socket.on('reconnect_error', (error: Error) => {
    console.error('[WebSocket] Reconnection error:', error);
  });
  
  socket.on('reconnect_failed', () => {
    console.error('[WebSocket] Reconnection failed after all attempts');
  });
  
  socket.on('disconnect', (reason: string) => {
    console.log('[WebSocket] Disconnected:', reason);
    // Auto-reconnect on transport errors
    if (reason === 'transport error' || reason === 'transport close') {
      console.log('[WebSocket] Attempting to reconnect due to transport issue');
    }
  });
  
  socket.on('connect_error', (error: Error) => {
    console.error('[WebSocket] Connection error:', error.message);
  });
  
  socketInstance = socket;
  connectionAttempted = true;
  return socket;
}

export function disconnectSocket(): void {
  if (socketInstance) {
    socketInstance.disconnect();
    socketInstance = null;
  }
  connectionAttempted = false;
  connectionListeners = [];
}

export function addSocketListener(event: string, handler: (...args: unknown[]) => void): void {
  if (socketInstance) {
    socketInstance.on(event, handler);
    connectionListeners.push({ event, handler });
  }
}

export function removeSocketListener(event: string, handler?: (...args: unknown[]) => void): void {
  if (socketInstance) {
    if (handler) {
      socketInstance.off(event, handler);
      connectionListeners = connectionListeners.filter(
        l => l.event !== event || l.handler !== handler
      );
    } else {
      socketInstance.off(event);
      connectionListeners = connectionListeners.filter(l => l.event !== event);
    }
  }
}

export function removeAllSocketListeners(): void {
  if (socketInstance) {
    for (const { event, handler } of connectionListeners) {
      socketInstance.off(event, handler);
    }
    connectionListeners = [];
  }
}

export function emitSocketEvent(event: string, data: unknown): void {
  if (socketInstance?.connected) {
    socketInstance.emit(event, data);
  }
}

export function sendToBackend(type: string, data: Record<string, unknown>): boolean {
  if (socketInstance?.connected) {
    console.log('[SocketManager] Sending to backend:', { type, ...data });
    socketInstance.emit('frontend_request', JSON.stringify({ type, ...data }));
    return true;
  }
  console.warn('[SocketManager] Cannot send - socket not connected');
  return false;
}

export function sendConfigUpdate(config: Record<string, unknown>): boolean {
  return sendToBackend('config_update', config);
}

export function sendModelChange(model: string): boolean {
  return sendToBackend('set_model', { model });
}