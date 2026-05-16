import type { Socket } from 'socket.io-client';
import { io } from 'socket.io-client';

// Global socket reference for use outside of React components
let socketInstance: Socket | null = null;
let connectionAttempted = false;
let connectionListeners: Array<{
  event: string;
  handler: (...args: unknown[]) => void;
}> = [];
let heartbeatInterval: ReturnType<typeof setInterval> | null = null;
let lastPongTime: number = 0;
const MAX_RECONNECT_ATTEMPTS = 50;
const HEARTBEAT_INTERVAL = 30000; // 30 seconds
const HEARTBEAT_TIMEOUT = 10000; // 10 seconds to wait for pong

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

// Heartbeat mechanism to detect dead connections
function startHeartbeat(socket: Socket) {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
  }
  
  lastPongTime = Date.now();
  
  heartbeatInterval = setInterval(() => {
    if (!socket.connected) {
      return;
    }
    
    // Check if we received a pong recently
    const now = Date.now();
    if (now - lastPongTime > HEARTBEAT_INTERVAL + HEARTBEAT_TIMEOUT) {
      console.warn('[WebSocket] Heartbeat timeout - connection may be dead');
      // Force reconnect
      socket.disconnect();
      socket.connect();
      return;
    }
    
    // Send ping
    socket.emit('ping');
  }, HEARTBEAT_INTERVAL);
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
  }
}

export function createSocket(connectionUrl: string): Socket {
  const socket = io(connectionUrl, {
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: MAX_RECONNECT_ATTEMPTS,
    timeout: 60000,
    path: '/socket.io',
    autoConnect: true,
    forceNew: false,
  });
  
  // Handle pong responses for heartbeat
  socket.on('pong', () => {
    lastPongTime = Date.now();
  });
  
  // Enhanced connection handling
  socket.on('connect', () => {
    console.log('[WebSocket] Connected successfully');
    lastPongTime = Date.now();
    startHeartbeat(socket);
  });
  
  socket.on('reconnect', (attemptNumber: number) => {
    console.log(`[WebSocket] Reconnected after ${attemptNumber} attempts`);
    startHeartbeat(socket);
  });
  
  socket.on('reconnect_attempt', (attemptNumber: number) => {
    console.log(`[WebSocket] Reconnection attempt ${attemptNumber}/${MAX_RECONNECT_ATTEMPTS}`);
  });
  
  socket.on('reconnect_error', (error: Error) => {
    console.error('[WebSocket] Reconnection error:', error.message);
  });
  
  socket.on('reconnect_failed', () => {
    console.error('[WebSocket] Reconnection failed after maximum attempts');
    stopHeartbeat();
    // Schedule manual reconnect attempt after a delay
    setTimeout(() => {
      if (socketInstance && !socketInstance.connected) {
        console.log('[WebSocket] Attempting manual reconnect...');
        socketInstance.connect();
      }
    }, 5000);
  });
  
  socket.on('disconnect', (reason: string) => {
    console.log('[WebSocket] Disconnected:', reason);
    stopHeartbeat();
    
    // Handle different disconnect reasons
    if (reason === 'io server disconnect') {
      // Server initiated disconnect - wait a bit then reconnect
      console.log('[WebSocket] Server initiated disconnect, will reconnect...');
      setTimeout(() => {
        if (socketInstance) {
          socketInstance.connect();
        }
      }, 2000);
    } else if (reason === 'transport error' || reason === 'transport close') {
      // Transport issues - socket.io will auto-reconnect
      console.log('[WebSocket] Transport issue, auto-reconnect enabled');
    } else if (reason === 'ping timeout') {
      // Ping timeout - connection was idle too long
      console.log('[WebSocket] Ping timeout, reconnecting...');
      socket.connect();
    }
  });
  
  socket.on('connect_error', (error: Error) => {
    console.error('[WebSocket] Connection error:', error.message);
    // Don't stop heartbeat on connect_error - socket.io will retry
  });
  
  socketInstance = socket;
  connectionAttempted = true;
  return socket;
}

export function disconnectSocket(): void {
  stopHeartbeat();
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

// Check if socket is healthy
export function isSocketHealthy(): boolean {
  if (!socketInstance || !socketInstance.connected) {
    return false;
  }
  // Check if we received a pong recently
  const now = Date.now();
  return now - lastPongTime < HEARTBEAT_INTERVAL + HEARTBEAT_TIMEOUT;
}

// Force reconnect if needed
export function forceReconnect(): void {
  if (socketInstance) {
    console.log('[WebSocket] Force reconnecting...');
    stopHeartbeat();
    socketInstance.disconnect();
    setTimeout(() => {
      socketInstance?.connect();
    }, 500);
  }
}