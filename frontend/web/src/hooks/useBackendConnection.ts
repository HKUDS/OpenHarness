import { useEffect, useCallback, useRef } from 'react';
import { io, type Socket } from 'socket.io-client';
import { useAppStore } from '../store/useAppStore';
import type { BackendEvent, TranscriptItem, Message } from '../types';
import { setSocketInstance } from '../utils/socketManager';

export function useBackendConnection() {
  const socketRef = useRef<Socket | null>(null);
  const connectAttemptedRef = useRef(false);
  const streamingMessageRef = useRef<Message | null>(null);
  const userMessageTimestampRef = useRef<number | null>(null);
  
  // Get store actions once - these are stable
  const {
    setConnected,
    setConnecting,
    setError,
    addMessage,
    updateMessage,
    setSessionState,
    setTasks,
    setMcpServers,
    setBridgeSessions,
    setBusy,
    setCommands,
    setSubmitPrompt,
    setSkills,
    setAvailableModels,
    setCurrentModel,
    updateSettings,
    connected,
    connecting,
    error,
  } = useAppStore();
  
  const connect = useCallback(() => {
    if (socketRef.current?.connected) {
      console.log('[WS] Already connected, skipping');
      return;
    }
    
    if (connectAttemptedRef.current) {
      console.log('[WS] Connection already attempted, skipping');
      return;
    }
    
    connectAttemptedRef.current = true;

    console.log('[WS] Connecting to backend...');
    setConnecting(true);
    setError(null);

    // Use current origin - backend serves the frontend
    const connectionUrl = window.location.origin;
    console.log('[WS] Connection URL:', connectionUrl);

    const socket = io(connectionUrl, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
      path: '/socket.io',
    });

    socket.on('connect', () => {
      console.log('[WS] ✅ Connected to OpenHarness backend');
      setConnected(true);
      setConnecting(false);
      setSocketInstance(socket);
    });

    socket.on('disconnect', () => {
      console.log('[WS] ❌ Disconnected from OpenHarness backend');
      setConnected(false);
      setSocketInstance(null);
    });

    socket.on('connect_error', (err) => {
      console.error('[WS] ❌ Connection error:', err);
      setError(`Connection failed: ${err.message}`);
      setConnecting(false);
      setConnected(false);
    });

    socket.on('backend_event', (data: string) => {
      console.log('[WS] 📩 Raw event received:', data.substring(0, 200));
      try {
        // Strip protocol prefix if present
        const jsonStr = data.startsWith('OHJSON:') ? data.slice(7) : data;
        const event = JSON.parse(jsonStr) as BackendEvent;
        console.log('[WS] 📩 Event type:', event.type);
        
        // Handle event
        switch (event.type) {
          case 'ready':
            console.log('[WS] Handling ready event');
            if (event.state) {
              const state = event.state as Record<string, unknown>;
              setSessionState(state as any);
              
              // Sync settings from backend
              if (state.model) {
                setCurrentModel(state.model as string);
              }
              if (state.permission_mode) {
                updateSettings({ permissionMode: state.permission_mode as 'plan' | 'default' | 'auto' });
              }
              if (state.working_directory) {
                updateSettings({ workingDirectory: state.working_directory as string });
              }
              if (state.max_turns) {
                updateSettings({ maxTurns: state.max_turns as number });
              }
              
              // Sync skills from backend if available
              if (state.skills && Array.isArray(state.skills)) {
                setSkills(state.skills.map((s: any) => ({
                  id: s.id || s.name?.toLowerCase().replace(/\s+/g, '-'),
                  name: s.name || s.id,
                  description: s.description || '',
                  enabled: s.enabled !== false,
                })));
              }
              
              // Sync available models from backend if available
              if (state.available_models && Array.isArray(state.available_models)) {
                setAvailableModels(state.available_models);
              }
            }
            if (event.commands) {
              setCommands(event.commands);
            }
            if (event.mcp_servers) {
              setMcpServers(event.mcp_servers);
            }
            if (event.bridge_sessions) {
              setBridgeSessions(event.bridge_sessions);
            }
            if (event.tasks) {
              setTasks(event.tasks);
            }
            break;

          case 'transcript_item':
            if (event.item) {
              const item = event.item as TranscriptItem;
              const now = Date.now();
              const message: Message = {
                id: crypto.randomUUID(),
                role: item.role as any,
                content: item.text || item.output || '',
                timestamp: now,
                tool_name: item.tool_name,
                tool_input: item.tool_input,
                is_error: item.is_error,
                tokenUsage: item.token_usage,
                responseTime: item.response_time || (item.role === 'assistant' && userMessageTimestampRef.current ? now - userMessageTimestampRef.current : undefined),
              };
              // Calculate response time for assistant messages
              if (item.role === 'assistant' && userMessageTimestampRef.current && !item.response_time) {
                message.responseTime = now - userMessageTimestampRef.current;
                userMessageTimestampRef.current = null;
              }
              // Record user message timestamp for response time calculation
              if (item.role === 'user') {
                userMessageTimestampRef.current = now;
              }
              addMessage(message);
            }
            break;
          
          case 'token_usage':
            // Handle token usage event from backend
            if (event.token_usage && streamingMessageRef.current) {
              updateMessage(streamingMessageRef.current.id, {
                tokenUsage: event.token_usage,
              });
            }
            break;

          case 'assistant_delta':
            // Handle streaming assistant response
            if (event.message) {
              const now = Date.now();
              if (!streamingMessageRef.current) {
                // Start new streaming message
                streamingMessageRef.current = {
                  id: crypto.randomUUID(),
                  role: 'assistant',
                  content: event.message,
                  timestamp: now,
                  responseTime: userMessageTimestampRef.current ? now - userMessageTimestampRef.current : undefined,
                };
                addMessage(streamingMessageRef.current);
              } else {
                // Append to existing streaming message
                streamingMessageRef.current.content += event.message;
                updateMessage(streamingMessageRef.current.id, {
                  content: streamingMessageRef.current.content,
                });
              }
            }
            break;

          case 'assistant_complete':
          case 'line_complete':
            // Calculate final response time and update message
            if (streamingMessageRef.current) {
              const responseTime = userMessageTimestampRef.current 
                ? Date.now() - userMessageTimestampRef.current 
                : streamingMessageRef.current.responseTime;
              
              updateMessage(streamingMessageRef.current.id, {
                responseTime,
                // Include token usage if provided in the event
                ...(event.token_usage && { tokenUsage: event.token_usage }),
              });
              userMessageTimestampRef.current = null;
            }
            // Reset streaming message
            streamingMessageRef.current = null;
            setBusy(false);
            break;

          case 'error':
            setError(event.message || 'Unknown error');
            break;

          case 'state_snapshot':
            if (event.state) {
              setSessionState(event.state as any);
            }
            break;

          case 'tasks_snapshot':
            if (event.tasks) {
              setTasks(event.tasks);
            }
            break;

          default:
            console.log('[WS] Unhandled event type:', event.type);
        }
      } catch (err) {
        console.error('[WS] Failed to parse backend event:', err);
      }
    });

    socketRef.current = socket;
  }, [
    setConnected,
    setConnecting,
    setError,
    addMessage,
    setSessionState,
    setTasks,
    setMcpServers,
    setBridgeSessions,
    setBusy,
    setCommands,
    setSkills,
    setAvailableModels,
    setCurrentModel,
    updateSettings,
  ]);

  const sendMessage = useCallback((payload: Record<string, unknown>) => {
    if (socketRef.current?.connected) {
      console.log('[WS] Sending message:', payload);
      socketRef.current.emit('frontend_request', JSON.stringify(payload));
    } else {
      console.warn('[WS] Cannot send message - not connected');
    }
  }, []);

  const submitPrompt = useCallback((prompt: string) => {
    console.log('[WS] Submitting prompt:', prompt);
    userMessageTimestampRef.current = Date.now(); // Record when user sends message
    sendMessage({ type: 'submit_line', line: prompt });
    setBusy(true);
  }, [sendMessage, setBusy]);

  // Send configuration update to backend
  const sendConfig = useCallback((config: Record<string, unknown>) => {
    console.log('[WS] Sending config update:', config);
    sendMessage({ type: 'config_update', config });
  }, [sendMessage]);

  // Request skills refresh from backend
  const refreshSkills = useCallback(() => {
    sendMessage({ type: 'get_skills' });
  }, [sendMessage]);

  // Request settings refresh from backend
  const refreshSettings = useCallback(() => {
    sendMessage({ type: 'get_settings' });
  }, [sendMessage]);

  // Connect once on mount
  useEffect(() => {
    if (!socketRef.current) {
      connect();
    }
    
    return () => {
      // Cleanup on unmount
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
      }
      setSocketInstance(null);
      setSubmitPrompt(null);
    };
  }, []); // Empty dependency array - only run once

  // Update submitPrompt in store when connected
  useEffect(() => {
    if (connected && socketRef.current?.connected) {
      setSubmitPrompt(submitPrompt);
    }
  }, [connected, submitPrompt, setSubmitPrompt]);

  const disconnect = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.disconnect();
      socketRef.current = null;
    }
    setConnected(false);
    setSubmitPrompt(null);
    connectAttemptedRef.current = false;
  }, [setConnected, setSubmitPrompt]);

  return {
    connect,
    disconnect,
    sendMessage,
    submitPrompt,
    sendConfig,
    refreshSkills,
    refreshSettings,
    connected,
    connecting,
    error,
  };
}
