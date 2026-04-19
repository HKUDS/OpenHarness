import { useEffect, useCallback, useRef } from 'react';
import { useAppStore } from '../store/useAppStore';
import type { BackendEvent, TranscriptItem, Message, ModalRequest, UploadedFile } from '../types';
import {
  getSocketInstance,
  createSocket,
  disconnectSocket,
  isConnectionAttempted,
} from '../utils/socketManager';

// ----------------------------------------------------------------------
// 🚨 GLOBAL MODULE LOCKS 🚨
// Moving these OUTSIDE the hook prevents multiple hook instances 
// (e.g. App.tsx and SettingsPanel.tsx) from bypassing each other's locks.
// ----------------------------------------------------------------------
let globalIsProcessingServerEvent = false;
let globalLastManualSave = 0;
let globalListenersSetup = false;

// Time window to consider a config_saved event as our own save
// This prevents updating localStorage from saves initiated by other clients
const SAVE_TIME_WINDOW_MS = 5000;

export function useBackendConnection() {
  const streamingMessageRef = useRef<Message | null>(null);
  const userMessageTimestampRef = useRef<number | null>(null);
  const processedMessageIdsRef = useRef<Set<string>>(new Set());
  const lastTranscriptTimestampRef = useRef<number>(0);
  // Track the chat session that initiated the current request
  const activeChatSessionRef = useRef<string | null>(null);

  // Granular selectors to prevent hook from re-rendering on EVERY store change.
  const setConnected = useAppStore((s) => s.setConnected);
  const setConnecting = useAppStore((s) => s.setConnecting);
  const setError = useAppStore((s) => s.setError);
  const addMessage = useAppStore((s) => s.addMessage);
  const addMessageToChat = useAppStore((s) => s.addMessageToChat);
  const updateMessage = useAppStore((s) => s.updateMessage);
  const updateMessageInChat = useAppStore((s) => s.updateMessageInChat);
  const setSessionState = useAppStore((s) => s.setSessionState);
  const setTasks = useAppStore((s) => s.setTasks);
  const setMcpServers = useAppStore((s) => s.setMcpServers);
  const setBridgeSessions = useAppStore((s) => s.setBridgeSessions);
  const setBusy = useAppStore((s) => s.setBusy);
  const setCommands = useAppStore((s) => s.setCommands);
  const setSubmitPrompt = useAppStore((s) => s.setSubmitPrompt);
  const setSendPermissionResponse = useAppStore((s) => s.setSendPermissionResponse);
  const setClearConversationCallback = useAppStore((s) => s.setClearConversationCallback);
  const setSaveSettingsCallback = useAppStore((s) => s.setSaveSettingsCallback);
  const setSkills = useAppStore((s) => s.setSkills);
  const setAvailableModels = useAppStore((s) => s.setAvailableModels);
  const setCurrentModel = useAppStore((s) => s.setCurrentModel);
  const updateSettings = useAppStore((s) => s.updateSettings);
  const setActiveModal = useAppStore((s) => s.setActiveModal);
  const setCronJobs = useAppStore((s) => s.setCronJobs);
  const setCreateCronJobCallback = useAppStore((s) => s.setCreateCronJobCallback);
  const setDeleteCronJobCallback = useAppStore((s) => s.setDeleteCronJobCallback);
  const setToggleCronJobCallback = useAppStore((s) => s.setToggleCronJobCallback);
  const setTriggerCronJobCallback = useAppStore((s) => s.setTriggerCronJobCallback);
  
  const connected = useAppStore((s) => s.connected);
  const connecting = useAppStore((s) => s.connecting);
  const error = useAppStore((s) => s.error);
  const currentChatId = useAppStore((s) => s.currentChatId);

  const handleBackendEvent = useCallback((data: string) => {
    // 🔒 LOCK ON: Prevent store changes from triggering outgoing saves
    globalIsProcessingServerEvent = true;
    
    try {
      const jsonStr = data.startsWith('OHJSON:') ? data.slice(7) : data;
      const event = JSON.parse(jsonStr) as BackendEvent;
      
      switch (event.type) {
        case 'ready':
          processedMessageIdsRef.current.clear();
          lastTranscriptTimestampRef.current = 0;
          streamingMessageRef.current = null;
          
          if (event.state) {
            const state = event.state as Record<string, unknown>;
            setSessionState(state as any);
            // Update sessionState model, but don't overwrite localStorage settings
            // The settings.model should come from localStorage or user interaction
            if (state.model) {
              // Only update sessionState, not localStorage settings
              setSessionState({ model: state.model as string });
            }
            
            // Don't update settings from backend state - preserve localStorage preferences
            // Settings should only be updated when user explicitly changes them in UI
            // or when saving to backend via API
            
            if (state.skills && Array.isArray(state.skills)) {
              setSkills(state.skills.map((s: any) => ({
                id: s.id || s.name?.toLowerCase().replace(/\s+/g, '-'),
                name: s.name || s.id,
                description: s.description || '',
                enabled: s.enabled !== false,
              })));
            }
            if (state.available_models && Array.isArray(state.available_models)) {
              setAvailableModels(state.available_models);
            }
          }
          if (event.commands) setCommands(event.commands);
          if (event.mcp_servers) setMcpServers(event.mcp_servers);
          if (event.bridge_sessions) setBridgeSessions(event.bridge_sessions);
          if (event.tasks) setTasks(event.tasks);
          if (event.cron_jobs) setCronJobs(event.cron_jobs);
          break;

        case 'cron_snapshot':
          if (event.cron_jobs) setCronJobs(event.cron_jobs);
          break;

        case 'transcript_item':
          if (event.item) {
            const item = event.item as TranscriptItem;
            const now = Date.now();
            
            // Skip user messages - they are added immediately on submit
            if (item.role === 'user') break;
            
            if (item.role === 'assistant' && streamingMessageRef.current) break;
            
            const itemContent = item.text || item.output || '';
            const itemKey = `${item.role}-${itemContent.length}-${item.tool_name || 'none'}-${itemContent.substring(0, 50)}`;
            
            if (processedMessageIdsRef.current.has(itemKey)) break;
            
            processedMessageIdsRef.current.add(itemKey);
            lastTranscriptTimestampRef.current = now;
            
            if (processedMessageIdsRef.current.size > 500) {
              const entries = Array.from(processedMessageIdsRef.current);
              processedMessageIdsRef.current = new Set(entries.slice(-250));
            }
            
            const message: Message = {
              id: crypto.randomUUID(),
              role: item.role as any,
              content: itemContent,
              timestamp: now,
              tool_name: item.tool_name,
              tool_input: item.tool_input,
              is_error: item.is_error,
              tokenUsage: item.token_usage,
              responseTime: item.response_time || (item.role === 'assistant' && userMessageTimestampRef.current ? now - userMessageTimestampRef.current : undefined),
            };
            
            if (item.role === 'assistant' && userMessageTimestampRef.current && !item.response_time) {
              message.responseTime = now - userMessageTimestampRef.current;
              userMessageTimestampRef.current = null;
            }
            
            // Add message to the active chat session (not necessarily the current one)
            const targetChatId = activeChatSessionRef.current;
            if (targetChatId) {
              addMessageToChat(targetChatId, message);
            } else {
              addMessage(message);
            }
          }
          break;
        
        case 'token_usage':
          if (event.token_usage && streamingMessageRef.current) {
            const targetChatId = activeChatSessionRef.current;
            if (targetChatId) {
              updateMessageInChat(targetChatId, streamingMessageRef.current.id, { tokenUsage: event.token_usage });
            } else {
              updateMessage(streamingMessageRef.current.id, { tokenUsage: event.token_usage });
            }
          }
          break;

        case 'assistant_delta':
          if (event.message) {
            const now = Date.now();
            const targetChatId = activeChatSessionRef.current;
            if (!streamingMessageRef.current) {
              streamingMessageRef.current = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: event.message,
                timestamp: now,
                responseTime: userMessageTimestampRef.current ? now - userMessageTimestampRef.current : undefined,
              };
              // Add message to the active chat session (not necessarily the current one)
              if (targetChatId) {
                addMessageToChat(targetChatId, streamingMessageRef.current);
              } else {
                addMessage(streamingMessageRef.current);
              }
            } else {
              streamingMessageRef.current.content += event.message;
              // Update message in the correct chat session
              if (targetChatId) {
                updateMessageInChat(targetChatId, streamingMessageRef.current.id, {
                  content: streamingMessageRef.current.content,
                });
              } else {
                updateMessage(streamingMessageRef.current.id, {
                  content: streamingMessageRef.current.content,
                });
              }
            }
          }
          break;

        case 'assistant_complete':
        case 'line_complete':
          if (streamingMessageRef.current) {
            const responseTime = userMessageTimestampRef.current 
              ? Date.now() - userMessageTimestampRef.current 
              : streamingMessageRef.current.responseTime;
            
            const targetChatId = activeChatSessionRef.current;
            // Update message with final content from the complete event and metadata
            const updates: Partial<Message> = {
              responseTime,
              ...(event.message && { content: event.message }),
              ...(event.token_usage && { tokenUsage: event.token_usage }),
            };
            // Update message in the correct chat session
            if (targetChatId) {
              updateMessageInChat(targetChatId, streamingMessageRef.current.id, updates);
            } else {
              updateMessage(streamingMessageRef.current.id, updates);
            }
            userMessageTimestampRef.current = null;
          }
          streamingMessageRef.current = null;
          // Clear the active session ref when response is complete
          activeChatSessionRef.current = null;
          setBusy(false);
          break;

        case 'error':
          const errorMsg = event.message || 'Unknown error';
          const errorType = event.error_type || 'unknown';
          const stackTrace = event.stack_trace || null;
          const debugInfo = event.debug_info || null;
          const recoverable = event.recoverable ?? true;
          
          // Map error types to human-readable labels
          const errorTypeLabels: Record<string, string> = {
            authentication: 'Authentication Error',
            rate_limit: 'Rate Limit Exceeded',
            network: 'Network Error',
            api: 'API Error',
            unknown: 'Error',
          };
          
          // Build detailed error message with helpful formatting
          let detailedErrorMsg = errorMsg;
          const typeLabel = errorTypeLabels[errorType] || errorType;
          if (errorType !== 'unknown' && !errorMsg.toLowerCase().includes(typeLabel.toLowerCase())) {
            detailedErrorMsg = `${typeLabel}: ${errorMsg}`;
          }
          
          // Add recovery hint if the error is recoverable
          if (recoverable) {
            detailedErrorMsg += '\n\nYou can try again or continue with a different request.';
          }
          if (stackTrace) {
            detailedErrorMsg += `\n\nStack Trace:\n${stackTrace}`;
          }
          if (debugInfo) {
            detailedErrorMsg += `\n\nDebug Info: ${JSON.stringify(debugInfo, null, 2)}`;
          }
          
          setError(detailedErrorMsg);
          // Also display error in chat for visibility with full details
          const errorMessage: Message = {
            id: crypto.randomUUID(),
            role: 'system',
            content: detailedErrorMsg,
            timestamp: Date.now(),
            is_error: true,
            tool_name: errorType,
          };
          addMessage(errorMessage);
          setBusy(false);
          break;

        case 'system':
          // Handle system messages from slash commands
          if (event.message) {
            const now = Date.now();
            const systemMessage: Message = {
              id: crypto.randomUUID(),
              role: 'system',
              content: event.message,
              timestamp: now,
            };
            addMessage(systemMessage);
            // Mark as not busy after system message (command completed)
            setBusy(false);
          }
          break;

        case 'state_snapshot':
        case 'state_update':
          if (event.state) {
            const state = event.state as Record<string, unknown>;
            setSessionState(state as any);
            // Update sessionState model, but don't overwrite localStorage settings
            if (state.model && typeof state.model === 'string') {
              setSessionState({ model: state.model });
            }
          }
          // Don't update settings from backend state - preserve localStorage preferences
          // Settings should only be updated when user explicitly changes them in UI
          break;

        case 'tasks_snapshot':
          if (event.tasks) setTasks(event.tasks);
          break;

        case 'modal_request':
          if (event.modal) setActiveModal(event.modal as ModalRequest);
          break;

        case 'permission_response_ack':
          if (!event.success) console.error('[WS] Permission response failed:', event.error);
          break;

        case 'config_saved':
          if (event.settings) {
            const savedSettings = event.settings as Record<string, unknown>;
            
            // Only update localStorage if this save was initiated by this frontend
            // Check if we recently triggered a manual save (within the time window)
            const now = Date.now();
            const isOurSave = (now - globalLastManualSave) < SAVE_TIME_WINDOW_MS;
            
            if (isOurSave) {
              // This was our save - update localStorage to confirm
              if (savedSettings.model) setCurrentModel(savedSettings.model as string);
              
              const batchedSettings: Record<string, any> = {};
              if (savedSettings.permission_mode) {
                batchedSettings.permissionMode = savedSettings.permission_mode === 'auto' ? 'full_auto' : savedSettings.permission_mode;
              }
              if (savedSettings.theme) batchedSettings.theme = savedSettings.theme;
              if (savedSettings.effort) batchedSettings.effort = savedSettings.effort;
              if (savedSettings.passes) batchedSettings.passes = savedSettings.passes;
              if (savedSettings.max_turns) batchedSettings.maxTurns = savedSettings.max_turns;
              if (savedSettings.vim_mode !== undefined) batchedSettings.vimMode = savedSettings.vim_mode;
              if (savedSettings.voice_mode !== undefined) batchedSettings.fastMode = savedSettings.voice_mode;
              
              if (Object.keys(batchedSettings).length > 0) updateSettings(batchedSettings);
            } else {
              // This save was initiated by another client or the backend itself
              // Don't update localStorage - preserve user's preferences
              console.log('[useBackendConnection] Received config_saved from external source, preserving localStorage settings');
            }
          }
          break;
      }
    } catch (err) {
      console.error('[WS] Failed to parse backend event:', err);
    } finally {
      // 🔓 LOCK OFF: Delay release slightly to let React finish rendering the new state
      setTimeout(() => {
        globalIsProcessingServerEvent = false;
      }, 150);
    }
  }, [
    setSessionState, setCurrentModel, updateSettings, setSkills, setAvailableModels,
    setCommands, setMcpServers, setBridgeSessions, setTasks, setBusy, setError,
    setActiveModal, addMessage, updateMessage
  ]);

  const setupListeners = useCallback((socket: ReturnType<typeof getSocketInstance>) => {
    if (!socket) return;
    
    // Always clear old listeners to prevent multiple triggers per event
    socket.off('connect');
    socket.off('disconnect');
    socket.off('connect_error');
    socket.off('backend_event');
    
    socket.on('connect', () => {
      setConnected(true);
      setConnecting(false);
    });

    socket.on('disconnect', () => {
      setConnected(false);
    });

    socket.on('connect_error', (err: Error & { message?: string; description?: string }) => {
      // Build detailed connection error message
      let detailedError = `Connection failed: ${err.message || 'Unknown error'}`;
      if (err.description) {
        detailedError += `\nDetails: ${err.description}`;
      }
      if (err.stack) {
        detailedError += `\n\nStack: ${err.stack}`;
      }
      
      setError(detailedError);
      setConnecting(false);
      setConnected(false);
      
      // Also show in chat for visibility
      addMessage({
        id: crypto.randomUUID(),
        role: 'system',
        content: detailedError,
        timestamp: Date.now(),
        is_error: true,
        tool_name: 'ConnectionError',
      });
    });

    socket.on('backend_event', handleBackendEvent);
    globalListenersSetup = true;
  }, [handleBackendEvent, setConnected, setConnecting, setError]);

  const connect = useCallback(() => {
    const existingSocket = getSocketInstance();
    if (existingSocket?.connected) return;
    
    if (isConnectionAttempted() && existingSocket) {
      if (!existingSocket.connected) setConnecting(true);
      return;
    }
    
    setConnecting(true);
    setError(null);

    const connectionUrl = window.location.origin;
    const socket = createSocket(connectionUrl);
    setupListeners(socket);
  }, [setupListeners, setConnecting, setError]);

  const sendMessage = useCallback((payload: Record<string, unknown>) => {
    const socket = getSocketInstance();
    if (socket?.connected) {
      socket.emit('frontend_request', JSON.stringify(payload));
    }
  }, []);

  const submitPrompt = useCallback((prompt: string, files?: UploadedFile[]) => {
    const now = Date.now();
    userMessageTimestampRef.current = now;
    streamingMessageRef.current = null;
    
    // Store the current chat session ID so responses go to the correct session
    // even if the user switches chats while waiting for a response
    activeChatSessionRef.current = currentChatId;
    
    // Add user message immediately to chat history
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: prompt,
      timestamp: now,
    };
    addMessage(userMessage);
    
    const socket = getSocketInstance();
    if (socket?.connected) {
      // Handle file uploads if present
      if (files && files.length > 0) {
        // Send files first via HTTP POST, then send the prompt
        const uploadFiles = async () => {
          try {
            const formData = new FormData();
            formData.append('prompt', prompt);
            
            // Convert uploaded files to blobs and append
            for (const file of files) {
              if ('file' in file && file.file instanceof File) {
                formData.append('files', file.file);
              } else if (file.type.startsWith('image/')) {
                // For already uploaded files, we might need to fetch them
                // For now, we'll just send metadata
                formData.append('file_metadata', JSON.stringify({
                  name: file.name,
                  type: file.type,
                  size: file.size,
                }));
              }
            }
            
            const response = await fetch('/api/upload', {
              method: 'POST',
              body: formData,
            });
            
            if (response.ok) {
              const result = await response.json();
              socket.emit('frontend_request', JSON.stringify({ 
                type: 'submit_line', 
                line: prompt,
                uploaded_files: result.files,
              }));
            } else {
              // Try to get error details from response
              let errorText = `Upload failed with status ${response.status}`;
              try {
                const errorData = await response.json();
                errorText = errorData.message || errorData.error || errorText;
              } catch {
                // Response is not JSON, use status text
                errorText = response.statusText || errorText;
              }
              
              console.error('File upload failed:', errorText);
              setError(`File upload failed: ${errorText}`);
              addMessage({
                id: crypto.randomUUID(),
                role: 'system',
                content: `File upload error: ${errorText}`,
                timestamp: Date.now(),
                is_error: true,
              });
              
              // Fallback: send without files
              socket.emit('frontend_request', JSON.stringify({ type: 'submit_line', line: prompt }));
            }
          } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown upload error';
            console.error('File upload failed:', err);
            setError(`File upload failed: ${errorMessage}`);
            addMessage({
              id: crypto.randomUUID(),
              role: 'system',
              content: `File upload error: ${errorMessage}`,
              timestamp: Date.now(),
              is_error: true,
            });
            // Fallback: send without files
            socket.emit('frontend_request', JSON.stringify({ type: 'submit_line', line: prompt }));
          }
        };
        
        uploadFiles();
      } else {
        // No files, send normally
        socket.emit('frontend_request', JSON.stringify({ type: 'submit_line', line: prompt }));
      }
      setBusy(true);
    } else {
      // Handle connection error
      setError('Not connected to backend. Please reconnect.');
      // Add error message to chat
      const errorMessage: Message = {
        id: crypto.randomUUID(),
        role: 'system',
        content: 'Error: Not connected to backend. Please check your connection and try again.',
        timestamp: Date.now(),
        is_error: true,
      };
      addMessage(errorMessage);
    }
  }, [sendMessage, setBusy, addMessage, setError]);

  const sendPermissionResponse = useCallback((requestId: string, allowed: boolean) => {
    sendMessage({ type: 'permission_response', request_id: requestId, allowed });
  }, [sendMessage]);

  const sendQuestionResponse = useCallback((requestId: string, answer: string) => {
    sendMessage({ type: 'question_response', request_id: requestId, answer });
  }, [sendMessage]);

  const sendConfig = useCallback((config: Record<string, unknown>) => {
    sendMessage({ type: 'config_update', config });
  }, [sendMessage]);

  const clearConversation = useCallback(() => {
    sendMessage({ type: 'clear_conversation' });
  }, [sendMessage]);

  const refreshSkills = useCallback(() => {
    sendMessage({ type: 'get_skills' });
  }, [sendMessage]);

  const refreshSettings = useCallback(() => {
    sendMessage({ type: 'get_settings' });
  }, [sendMessage]);

  const createCronJob = useCallback((name: string, schedule: string, command: string, cwd?: string, enabled?: boolean) => {
    sendMessage({ 
      type: 'create_cron_job', 
      cron_name: name,
      cron_schedule: schedule,
      cron_command: command,
      cron_cwd: cwd,
      cron_enabled: enabled,
    });
  }, [sendMessage]);

  const deleteCronJob = useCallback((name: string) => {
    sendMessage({ type: 'delete_cron_job', cron_name: name });
  }, [sendMessage]);

  const toggleCronJob = useCallback((name: string, enabled: boolean) => {
    sendMessage({ type: 'toggle_cron_job', cron_name: name, cron_enabled: enabled });
  }, [sendMessage]);

  const triggerCronJob = useCallback((name: string) => {
    sendMessage({ type: 'trigger_cron_job', cron_name: name });
  }, [sendMessage]);

  const fetchSettingsFromBackend = useCallback(async () => {
    try {
      const response = await fetch('/api/config');
      if (response.ok) {
        const config = await response.json();
        
        // DO NOT update localStorage settings from backend config
        // The user's localStorage preferences should be preserved and synced to backend
        // instead of being overwritten by backend state.
        // Only return the config for informational purposes.
        
        return config;
      }
      
      // Handle error responses
      if (response.status === 400) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.message || errorData.error || 'Invalid configuration';
        setError(`Bad request: ${errorMsg}`);
        console.error('[WS] Bad request when fetching config:', errorMsg);
      } else if (response.status >= 400) {
        setError(`Server error: ${response.status}`);
        console.error('[WS] Error fetching config:', response.status);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(`Network error: ${errorMsg}`);
      console.error('[WS] Failed to fetch config from backend:', err);
    }
    return null;
  }, [updateSettings, setError]);

  const saveSettingsToBackend = useCallback(async (settings: Record<string, unknown>) => {
    // 1. THE ANTI-LOOP: If this save was triggered directly/indirectly by an incoming 
    // WebSocket event, block it. The global lock catches ALL hook instances.
    if (globalIsProcessingServerEvent) {
      console.warn('🚫 [ANTI-LOOP] Blocked save triggered by websocket update.');
      return null;
    }
    
    // 2. GLOBAL CIRCUIT BREAKER: Block rapid consecutive calls across ALL components
    const now = Date.now();
    if (now - globalLastManualSave < 1000) {
      console.warn('🚫 [CIRCUIT BREAKER] Blocked spam request across instances.');
      return null;
    }
    globalLastManualSave = now;

    try {
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      
      if (response.ok) {
        return await response.json();
      }
      
      // Handle error responses
      if (response.status === 400) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.message || errorData.error || 'Invalid settings';
        setError(`Bad request: ${errorMsg}`);
        console.error('[WS] Bad request when saving settings:', errorMsg);
      } else if (response.status >= 400) {
        setError(`Server error: ${response.status}`);
        console.error('[WS] Error saving settings:', response.status);
      }
      
      return null;
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(`Network error: ${errorMsg}`);
      console.error('[WS] Error saving settings to backend:', err);
      return null;
    }
  }, []);

  useEffect(() => {
    if (!isConnectionAttempted()) connect();
    
    const socket = getSocketInstance();
    if (socket && !globalListenersSetup) {
      setupListeners(socket);
    }
  }, [connect, setupListeners]);

  useEffect(() => {
    if (connected) {
      setSubmitPrompt(submitPrompt);
      setSendPermissionResponse(sendPermissionResponse);
      setClearConversationCallback(clearConversation);
      setSaveSettingsCallback(saveSettingsToBackend);
      setCreateCronJobCallback(createCronJob);
      setDeleteCronJobCallback(deleteCronJob);
      setToggleCronJobCallback(toggleCronJob);
      setTriggerCronJobCallback(triggerCronJob);
      
      // Sync frontend localStorage settings to backend on connection
      // This ensures user's preferences are applied to the backend
      const settings = useAppStore.getState().settings;
      const sessionState = useAppStore.getState().sessionState;
      
      // Only sync if frontend has different values than backend
      const configToSend: Record<string, unknown> = {};
      
      // Sync model if frontend has a preference different from backend
      if (settings.model && settings.model !== sessionState?.model) {
        configToSend['model'] = settings.model;
      }
      
      // Sync permission mode if frontend has a preference different from backend
      if (settings.permissionMode && settings.permissionMode !== sessionState?.permission_mode) {
        configToSend['permission_mode'] = settings.permissionMode;
      }
      
      // Send config to backend if there are differences
      if (Object.keys(configToSend).length > 0) {
        console.log('[useBackendConnection] Syncing frontend settings to backend:', configToSend);
        sendConfig(configToSend);
      }
    }
  }, [
    connected, submitPrompt, sendPermissionResponse, clearConversation, 
    saveSettingsToBackend, setSubmitPrompt, setSendPermissionResponse, 
    setClearConversationCallback, setSaveSettingsCallback, sendConfig,
    createCronJob, deleteCronJob, toggleCronJob,
    setCreateCronJobCallback, setDeleteCronJobCallback, setToggleCronJobCallback
  ]);

  const disconnect = useCallback(() => {
    disconnectSocket();
    setConnected(false);
    globalListenersSetup = false;
  }, [setConnected]);

  return {
    connect,
    disconnect,
    connected,
    connecting,
    error,
    sendMessage,
    submitPrompt,
    sendPermissionResponse,
    sendQuestionResponse,
    sendConfig,
    clearConversation,
    refreshSkills,
    refreshSettings,
    fetchSettingsFromBackend,
    saveSettingsToBackend,
    createCronJob,
    deleteCronJob,
    toggleCronJob,
  };
}