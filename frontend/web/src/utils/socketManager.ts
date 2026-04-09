import type { Socket } from 'socket.io-client';

// Global socket reference for use outside of React components
let socketInstance: Socket | null = null;

export function setSocketInstance(socket: Socket | null) {
  socketInstance = socket;
}

export function getSocketInstance(): Socket | null {
  return socketInstance;
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