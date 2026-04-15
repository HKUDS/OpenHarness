import { create } from 'zustand';
import type { 
  Message, 
  SessionState, 
  TaskSnapshot, 
  McpServerSnapshot, 
  BridgeSessionSnapshot,
  SwarmTeammateSnapshot,
  SwarmNotificationSnapshot,
  UploadedFile,
  ChatSession,
  McpServerConfig,
  TodoItem,
  AppSettings,
  ChannelConfig,
  OpenHarnessConfig,
  ModalRequest,
  PermissionModalRequest,
} from '../types';

interface Skill {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  icon?: string;
  script?: string;
  scriptPath?: string;
  scriptType?: 'python' | 'bash' | 'javascript' | 'other';
  author?: string;
  version?: string;
  source?: 'local' | 'github' | 'clawhub' | 'upload';
  sourceUrl?: string;
  createdAt?: number;
  updatedAt?: number;
  tags?: string[];
}

interface MemoryItem {
  id: string;
  content: string;
  createdAt: number;
  type: 'fact' | 'preference' | 'context';
}

interface AppState {
  // Connection state
  connected: boolean;
  connecting: boolean;
  error: string | null;
  
  // Session data
  messages: Message[];
  sessionState: SessionState | null;
  tasks: TaskSnapshot[];
  mcpServers: McpServerSnapshot[];
  bridgeSessions: BridgeSessionSnapshot[];
  swarmTeammates: SwarmTeammateSnapshot[];
  swarmNotifications: SwarmNotificationSnapshot[];
  todoMarkdown: string;
  commands: string[];
  
  // Modal state for permission requests
  activeModal: ModalRequest | null;
  
  // New features state
  chatSessions: ChatSession[];
  currentChatId: string | null;
  uploadedFiles: UploadedFile[];
  availableModels: string[];
  permissionModes: { value: string; label: string }[];
  settings: AppSettings;
  mcpServerConfigs: McpServerConfig[];
  todoItems: TodoItem[];
  skills: Skill[];
  memories: MemoryItem[];
  
  // Channel configuration
  channels: ChannelConfig[];
  
  // OpenHarness configuration
  openHarnessConfig: OpenHarnessConfig | null;
  
  // UI state
  isBusy: boolean;
  sidebarOpen: boolean;
  sidebarWidth: number;
  chatSidebarWidth: number;
  timelineWidth: number;
  activePanel: 'chats' | 'tasks' | 'mcp' | 'swarm' | 'todo' | 'settings' | 'skills' | 'memory';
  terminalView: 'chat' | 'terminal';
  commandPaletteOpen: boolean;
  inputHeight: number;
  showFileUpload: boolean;
  expandedMessages: Set<string>;
  isResizingSidebar: boolean;
  isResizingInput: boolean;
  isResizingChatSidebar: boolean;
  isResizingTimeline: boolean;
  
  // Search state
  searchQuery: string;
  searchResults: { chatId: string; chatName: string; messageId: string; content: string; timestamp: number }[];
  
  // Scroll to message after search navigation
  scrollToMessageId: string | null;
  
  // Callback actions (set by hooks)
  submitPrompt: ((prompt: string, files?: UploadedFile[]) => void) | null;
  sendPermissionResponse: ((requestId: string, allowed: boolean) => void) | null;
  clearConversationCallback: (() => void) | null;
  saveSettingsCallback: ((settings: Record<string, unknown>) => Promise<void>) | null;
  
  // Actions
  setConnected: (connected: boolean) => void;
  setConnecting: (connecting: boolean) => void;
  setError: (error: string | null) => void;
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  setSessionState: (state: Partial<SessionState>) => void;
  setTasks: (tasks: TaskSnapshot[]) => void;
  setMcpServers: (servers: McpServerSnapshot[]) => void;
  setBridgeSessions: (sessions: BridgeSessionSnapshot[]) => void;
  setSwarmTeammates: (teammates: SwarmTeammateSnapshot[]) => void;
  setSwarmNotifications: (notifications: SwarmNotificationSnapshot[]) => void;
  setTodoMarkdown: (markdown: string) => void;
  setCommands: (commands: string[]) => void;
  setBusy: (busy: boolean) => void;
  setSubmitPrompt: (fn: ((prompt: string, files?: UploadedFile[]) => void) | null) => void;
  setSendPermissionResponse: (fn: ((requestId: string, allowed: boolean) => void) | null) => void;
  setClearConversationCallback: (fn: (() => void) | null) => void;
  setSaveSettingsCallback: (fn: ((settings: Record<string, unknown>) => Promise<void>) | null) => void;
  toggleSidebar: () => void;
  setActivePanel: (panel: AppState['activePanel']) => void;
  setTerminalView: (view: AppState['terminalView']) => void;
  toggleTerminalView: () => void;
  toggleCommandPalette: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  clearMessages: () => void;
  
  // Modal actions
  setActiveModal: (modal: ModalRequest | null) => void;
  respondToModal: (requestId: string, response: boolean | string) => void;
  
  // New feature actions
  setInputHeight: (height: number) => void;
  addUploadedFile: (file: UploadedFile) => void;
  removeUploadedFile: (id: string) => void;
  clearUploadedFiles: () => void;
  setShowFileUpload: (show: boolean) => void;
  setAvailableModels: (models: string[]) => void;
  setCurrentModel: (model: string) => void;
  setPermissionMode: (mode: string) => void;
  createNewChat: (name?: string) => void;
  switchChat: (chatId: string) => void;
  deleteChat: (chatId: string) => void;
  updateChatSession: (chatId: string, updates: Partial<ChatSession>) => void;
  updateSettings: (settings: Partial<AppSettings>) => void;
  addMcpServer: (config: McpServerConfig) => void;
  removeMcpServer: (name: string) => void;
  updateMcpServer: (name: string, config: Partial<McpServerConfig>) => void;
  addTodoItem: (text: string) => void;
  toggleTodoItem: (index: number) => void;
  removeTodoItem: (index: number) => void;
  updateTodoMarkdown: (markdown: string) => void;
  
  // Gemini-like features
  toggleMessageExpand: (messageId: string) => void;
  setSidebarWidth: (width: number) => void;
  setChatSidebarWidth: (width: number) => void;
  setTimelineWidth: (width: number) => void;
  setIsResizingSidebar: (resizing: boolean) => void;
  setIsResizingInput: (resizing: boolean) => void;
  setIsResizingChatSidebar: (resizing: boolean) => void;
  setIsResizingTimeline: (resizing: boolean) => void;
  
  // Search actions
  setSearchQuery: (query: string) => void;
  searchMessages: (query: string) => void;
  clearSearch: () => void;
  setScrollToMessageId: (messageId: string | null) => void;
  
  addSkill: (skill: Skill) => void;
  updateSkill: (skillId: string, updates: Partial<Skill>) => void;
  toggleSkill: (skillId: string) => void;
  removeSkill: (skillId: string) => void;
  addMemory: (memory: MemoryItem) => void;
  removeMemory: (memoryId: string) => void;
  updateMemory: (memoryId: string, content: string) => void;
  setSkills: (skills: Skill[]) => void;
  setMemories: (memories: MemoryItem[]) => void;
  
  // Channel actions
  addChannel: (channel: ChannelConfig) => void;
  updateChannel: (id: string, updates: Partial<ChannelConfig>) => void;
  removeChannel: (id: string) => void;
  toggleChannel: (id: string) => void;
  
  // OpenHarness config actions
  setOpenHarnessConfig: (config: OpenHarnessConfig) => void;
  updateOpenHarnessConfig: (updates: Partial<OpenHarnessConfig>) => void;
}

const DEFAULT_MODELS = [
  'claude-3-5-sonnet-20241022',
  'claude-3-opus-20240229',
  'claude-3-sonnet-20240229',
  'claude-3-haiku-20240307',
  'gemini-1-5-pro',
  'gemini-1-5-flash',
  'gpt-4-turbo-preview',
  'gpt-4-0125-preview',
  'gpt-3.5-turbo-0125'
];

const PERMISSION_MODES = [
  { value: 'default', label: 'Default (Auto-approve safe commands)' },
  { value: 'plan', label: 'Plan Mode (Review before execution)' },
  { value: 'full_auto', label: 'Auto (Allow all tools)' }
];

const DEFAULT_SETTINGS: AppSettings = {
  apiKey: '',
  model: 'claude-sonnet-4-6',
  permissionMode: 'default',
  theme: 'dark',
  workingDirectory: '~/workspace',
  maxTurns: 200,
  effort: 'medium',
  passes: 1,
  verbose: false,
  vimMode: false,
  fastMode: false,
};

const DEFAULT_SKILLS: Skill[] = [
  { id: 'code-review', name: 'Code Review', description: 'Review and suggest improvements for code', enabled: true },
  { id: 'debugging', name: 'Debugging', description: 'Help identify and fix bugs', enabled: true },
  { id: 'testing', name: 'Testing', description: 'Write and run tests', enabled: true },
  { id: 'documentation', name: 'Documentation', description: 'Generate documentation', enabled: false },
  { id: 'refactoring', name: 'Refactoring', description: 'Improve code structure', enabled: false },
];

// LocalStorage keys
const STORAGE_KEYS = {
  SETTINGS: 'openharness-settings',
  CHAT_SESSIONS: 'openharness-chat-sessions',
  CURRENT_CHAT_ID: 'openharness-current-chat-id',
  SKILLS: 'openharness-skills',
  MEMORIES: 'openharness-memories',
  CHANNELS: 'openharness-channels',
  AVAILABLE_MODELS: 'openharness-available-models',
  OPENHARNESS_CONFIG: 'openharness-openharness-config',
  CHAT_SIDEBAR_WIDTH: 'openharness-chat-sidebar-width',
  TIMELINE_WIDTH: 'openharness-timeline-width',
};

// Helper to load from localStorage
function loadFromStorage<T>(key: string, defaultValue: T): T {
  try {
    const stored = localStorage.getItem(key);
    if (stored) {
      return JSON.parse(stored) as T;
    }
  } catch (e) {
    console.error(`Failed to load ${key} from localStorage:`, e);
  }
  return defaultValue;
}

// Helper to get initial messages from current chat session
function getInitialMessages(): Message[] {
  const chatSessions = loadFromStorage<ChatSession[]>(STORAGE_KEYS.CHAT_SESSIONS, []);
  const currentChatId = loadFromStorage<string | null>(STORAGE_KEYS.CURRENT_CHAT_ID, null);
  
  if (currentChatId && chatSessions.length > 0) {
    const currentChat = chatSessions.find(c => c.id === currentChatId);
    if (currentChat && currentChat.messages) {
      return currentChat.messages;
    }
  }
  return [];
}

// Helper to save to localStorage
function saveToStorage<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    console.error(`Failed to save ${key} to localStorage:`, e);
  }
}

// Helper to save current messages to the current chat session
function saveMessagesToCurrentSession(
  chatSessions: ChatSession[],
  currentChatId: string | null,
  messages: Message[]
): ChatSession[] {
  if (!currentChatId) return chatSessions;
  return chatSessions.map((chat) =>
    chat.id === currentChatId
      ? { ...chat, messages, updatedAt: Date.now() }
      : chat
  );
}

export const useAppStore = create<AppState>((set) => ({
  // Initial state - load from localStorage
  connected: false,
  connecting: false,
  error: null,
  messages: getInitialMessages(),
  sessionState: null,
  tasks: [],
  mcpServers: [],
  bridgeSessions: [],
  swarmTeammates: [],
  swarmNotifications: [],
  todoMarkdown: '',
  commands: [],
  isBusy: false,
  sidebarOpen: true,
  sidebarWidth: 280,
  chatSidebarWidth: loadFromStorage<number>(STORAGE_KEYS.CHAT_SIDEBAR_WIDTH, 280),
  timelineWidth: loadFromStorage<number>(STORAGE_KEYS.TIMELINE_WIDTH, 60),
  activePanel: 'chats',
  terminalView: 'chat',
  commandPaletteOpen: false,
  inputHeight: 140,
  showFileUpload: false,
  submitPrompt: null,
  sendPermissionResponse: null,
  clearConversationCallback: null,
  saveSettingsCallback: null,
  activeModal: null,
  expandedMessages: new Set(),
  isResizingSidebar: false,
  isResizingInput: false,
  isResizingChatSidebar: false,
  isResizingTimeline: false,
  searchQuery: '',
  searchResults: [],
  scrollToMessageId: null,
  
  // New features initial state - load from localStorage
  chatSessions: loadFromStorage<ChatSession[]>(STORAGE_KEYS.CHAT_SESSIONS, []),
  currentChatId: loadFromStorage<string | null>(STORAGE_KEYS.CURRENT_CHAT_ID, null),
  uploadedFiles: [],
  availableModels: loadFromStorage<string[]>(STORAGE_KEYS.AVAILABLE_MODELS, DEFAULT_MODELS),
  permissionModes: PERMISSION_MODES,
  settings: loadFromStorage<AppSettings>(STORAGE_KEYS.SETTINGS, DEFAULT_SETTINGS),
  mcpServerConfigs: [],
  todoItems: [],
  skills: loadFromStorage<Skill[]>(STORAGE_KEYS.SKILLS, DEFAULT_SKILLS),
  memories: loadFromStorage<MemoryItem[]>(STORAGE_KEYS.MEMORIES, []),
  channels: loadFromStorage<ChannelConfig[]>(STORAGE_KEYS.CHANNELS, []),
  openHarnessConfig: loadFromStorage<OpenHarnessConfig | null>(STORAGE_KEYS.OPENHARNESS_CONFIG, null),
  
  // Actions
  setConnected: (connected) => set({ connected }),
  setConnecting: (connecting) => set({ connecting }),
  setError: (error) => set({ error }),
  
  addMessage: (message) => set((state) => {
    // Prevent adding duplicate messages by checking recent messages
    const recentMessages = state.messages.slice(-5);
    const isDuplicate = recentMessages.some(
      m => m.role === message.role && 
           m.content === message.content && 
           Math.abs(m.timestamp - message.timestamp) < 100
    );
    
    if (isDuplicate) {
      console.log('[useAppStore] Skipping duplicate message:', message.id);
      return state;
    }
    
    const newMessages = [...state.messages, message];
    
    // Save messages to the current chat session for persistence
    if (state.currentChatId) {
      const updatedSessions = saveMessagesToCurrentSession(
        state.chatSessions,
        state.currentChatId,
        newMessages
      );
      saveToStorage(STORAGE_KEYS.CHAT_SESSIONS, updatedSessions);
      return {
        messages: newMessages,
        chatSessions: updatedSessions
      };
    }
    
    return {
      messages: newMessages
    };
  }),
  
  updateMessage: (id, updates) => set((state) => {
    const newMessages = state.messages.map((msg) => 
      msg.id === id ? { ...msg, ...updates } : msg
    );
    
    // Sync updates to the current chat session for persistence
    if (state.currentChatId) {
      const updatedSessions = saveMessagesToCurrentSession(
        state.chatSessions,
        state.currentChatId,
        newMessages
      );
      saveToStorage(STORAGE_KEYS.CHAT_SESSIONS, updatedSessions);
      return {
        messages: newMessages,
        chatSessions: updatedSessions
      };
    }
    
    return {
      messages: newMessages
    };
  }),
  
  setSessionState: (state) => set((prev) => ({
    sessionState: { ...prev.sessionState, ...state }
  })),
  
  setTasks: (tasks) => set({ tasks }),
  setMcpServers: (servers) => set({ mcpServers: servers }),
  setBridgeSessions: (sessions) => set({ bridgeSessions: sessions }),
  setSwarmTeammates: (teammates) => set({ swarmTeammates: teammates }),
  setSwarmNotifications: (notifications) => set({ swarmNotifications: notifications }),
  setTodoMarkdown: (markdown) => set({ todoMarkdown: markdown }),
  setCommands: (commands) => set({ commands }),
  setBusy: (busy) => set({ isBusy: busy }),
  setSubmitPrompt: (fn) => set({ submitPrompt: fn }),
  setSendPermissionResponse: (fn) => set({ sendPermissionResponse: fn }),
  setClearConversationCallback: (fn) => set({ clearConversationCallback: fn }),
  setSaveSettingsCallback: (fn) => set({ saveSettingsCallback: fn }),
  
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setActivePanel: (panel) => set({ activePanel: panel }),
  setTerminalView: (view) => set({ terminalView: view }),
  toggleTerminalView: () => set((state) => ({ terminalView: state.terminalView === 'chat' ? 'terminal' : 'chat' })),
  toggleCommandPalette: () => set((state) => ({ commandPaletteOpen: !state.commandPaletteOpen })),
  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
  clearMessages: () => set((state) => {
    // Clear messages in the current chat session for persistence
    if (state.currentChatId) {
      const updatedSessions = saveMessagesToCurrentSession(
        state.chatSessions,
        state.currentChatId,
        []
      );
      saveToStorage(STORAGE_KEYS.CHAT_SESSIONS, updatedSessions);
      return {
        messages: [],
        chatSessions: updatedSessions
      };
    }
    return { messages: [] };
  }),
  
  // Modal actions
  setActiveModal: (modal) => set({ activeModal: modal }),
  respondToModal: (requestId, _response) => set((state) => {
    // Clear the modal when responding
    if (state.activeModal && (state.activeModal as PermissionModalRequest).request_id === requestId) {
      return { activeModal: null };
    }
    return state;
  }),
  
  // New feature actions
  setInputHeight: (height) => set({ inputHeight: height }),
  
  addUploadedFile: (file) => set((state) => ({
    uploadedFiles: [...state.uploadedFiles, file]
  })),
  
  removeUploadedFile: (id) => set((state) => ({
    uploadedFiles: state.uploadedFiles.filter(f => f.id !== id)
  })),
  
  clearUploadedFiles: () => set({ uploadedFiles: [] }),
  
  setShowFileUpload: (show) => set({ showFileUpload: show }),
  
  setAvailableModels: (models) => {
    saveToStorage(STORAGE_KEYS.AVAILABLE_MODELS, models);
    console.log('[useAppStore] Saved available models:', models);
    set({ availableModels: models });
  },
  
  setCurrentModel: (model) => set((state) => {
    const newSettings = { ...state.settings, model };
    saveToStorage(STORAGE_KEYS.SETTINGS, newSettings);
    return {
      settings: newSettings,
      sessionState: { ...state.sessionState, model }
    };
  }),
  
  setPermissionMode: (mode) => set((state) => {
    const newSettings = { ...state.settings, permissionMode: mode as 'plan' | 'default' | 'full_auto' };
    saveToStorage(STORAGE_KEYS.SETTINGS, newSettings);
    return {
      settings: newSettings,
      sessionState: { ...state.sessionState, permission_mode: mode }
    };
  }),
  
  createNewChat: (name) => set((state) => {
    // Save current messages to the current session before creating a new one
    let sessionsWithSavedMessages = state.chatSessions;
    if (state.currentChatId) {
      sessionsWithSavedMessages = saveMessagesToCurrentSession(
        state.chatSessions,
        state.currentChatId,
        state.messages
      );
    }
    
    const newChat: ChatSession = {
      id: `chat-${Date.now()}`,
      name: name || `New Chat ${state.chatSessions.length + 1}`,
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
      model: state.settings.model
    };
    const newSessions = [newChat, ...sessionsWithSavedMessages];
    saveToStorage(STORAGE_KEYS.CHAT_SESSIONS, newSessions);
    saveToStorage(STORAGE_KEYS.CURRENT_CHAT_ID, newChat.id);
    // Call backend to clear conversation history
    if (state.clearConversationCallback) {
      state.clearConversationCallback();
    }
    return {
      chatSessions: newSessions,
      currentChatId: newChat.id,
      messages: []
    };
  }),
  
  switchChat: (chatId) => set((state) => {
    const chat = state.chatSessions.find(c => c.id === chatId);
    if (!chat) return state;
    
    // Save current messages to the current session before switching
    let sessionsToSave = state.chatSessions;
    if (state.currentChatId && state.currentChatId !== chatId) {
      sessionsToSave = saveMessagesToCurrentSession(
        state.chatSessions,
        state.currentChatId,
        state.messages
      );
      saveToStorage(STORAGE_KEYS.CHAT_SESSIONS, sessionsToSave);
    }
    
    saveToStorage(STORAGE_KEYS.CURRENT_CHAT_ID, chatId);
    return {
      chatSessions: sessionsToSave,
      currentChatId: chatId,
      messages: chat.messages || []
    };
  }),
  
  deleteChat: (chatId) => set((state) => {
    // Save current messages to the current session before deleting
    let sessionsWithSavedMessages = state.chatSessions;
    if (state.currentChatId && state.currentChatId !== chatId) {
      sessionsWithSavedMessages = saveMessagesToCurrentSession(
        state.chatSessions,
        state.currentChatId,
        state.messages
      );
    }
    
    const newSessions = sessionsWithSavedMessages.filter(c => c.id !== chatId);
    const newCurrentId = state.currentChatId === chatId 
      ? (newSessions.length > 0 ? newSessions[0].id : null)
      : state.currentChatId;
    const newMessages = state.currentChatId === chatId
      ? (newSessions.length > 0 ? newSessions[0].messages || [] : [])
      : state.messages;
    saveToStorage(STORAGE_KEYS.CHAT_SESSIONS, newSessions);
    if (newCurrentId) saveToStorage(STORAGE_KEYS.CURRENT_CHAT_ID, newCurrentId);
    return {
      chatSessions: newSessions,
      currentChatId: newCurrentId,
      messages: newMessages
    };
  }),
  
  updateChatSession: (chatId, updates) => set((state) => {
    const newSessions = state.chatSessions.map(c => 
      c.id === chatId ? { ...c, ...updates, updatedAt: Date.now() } : c
    );
    saveToStorage(STORAGE_KEYS.CHAT_SESSIONS, newSessions);
    return { chatSessions: newSessions };
  }),
  
  updateSettings: (newSettings) => set((state) => {
    const updated = { ...state.settings, ...newSettings };
    saveToStorage(STORAGE_KEYS.SETTINGS, updated);
    return { settings: updated };
  }),
  
  addMcpServer: (config) => set((state) => ({
    mcpServerConfigs: [...state.mcpServerConfigs, config]
  })),
  
  removeMcpServer: (name) => set((state) => ({
    mcpServerConfigs: state.mcpServerConfigs.filter(s => s.name !== name)
  })),
  
  updateMcpServer: (name, config) => set((state) => ({
    mcpServerConfigs: state.mcpServerConfigs.map(s => 
      s.name === name ? { ...s, ...config } : s
    )
  })),
  
  addTodoItem: (text) => set((state) => ({
    todoItems: [...state.todoItems, { text, checked: false }]
  })),
  
  toggleTodoItem: (index) => set((state) => ({
    todoItems: state.todoItems.map((item, i) => 
      i === index ? { ...item, checked: !item.checked } : item
    )
  })),
  
  removeTodoItem: (index) => set((state) => ({
    todoItems: state.todoItems.filter((_, i) => i !== index)
  })),
  
  updateTodoMarkdown: (markdown) => set({ todoMarkdown: markdown }),
  
  // Gemini-like features
  toggleMessageExpand: (messageId) => set((state) => {
    const newExpanded = new Set(state.expandedMessages);
    if (newExpanded.has(messageId)) {
      newExpanded.delete(messageId);
    } else {
      newExpanded.add(messageId);
    }
    return { expandedMessages: newExpanded };
  }),
  
  setSidebarWidth: (width) => set({ sidebarWidth: width }),
  setChatSidebarWidth: (width) => {
    saveToStorage(STORAGE_KEYS.CHAT_SIDEBAR_WIDTH, width);
    set({ chatSidebarWidth: width });
  },
  setTimelineWidth: (width) => {
    saveToStorage(STORAGE_KEYS.TIMELINE_WIDTH, width);
    set({ timelineWidth: width });
  },
  setIsResizingSidebar: (resizing) => set({ isResizingSidebar: resizing }),
  setIsResizingInput: (resizing) => set({ isResizingInput: resizing }),
  setIsResizingChatSidebar: (resizing) => set({ isResizingChatSidebar: resizing }),
  setIsResizingTimeline: (resizing) => set({ isResizingTimeline: resizing }),
  
  setSearchQuery: (query) => set({ searchQuery: query }),
  searchMessages: (query) => set((state) => {
    if (!query.trim()) {
      return { searchQuery: query, searchResults: [] };
    }
    
    const results: { chatId: string; chatName: string; messageId: string; content: string; timestamp: number }[] = [];
    const lowerQuery = query.toLowerCase();
    
    state.chatSessions.forEach(chat => {
      chat.messages.forEach(msg => {
        if (msg.content.toLowerCase().includes(lowerQuery)) {
          results.push({
            chatId: chat.id,
            chatName: chat.name,
            messageId: msg.id,
            content: msg.content.substring(0, 150) + (msg.content.length > 150 ? '...' : ''),
            timestamp: msg.timestamp
          });
        }
      });
    });
    
    return { searchQuery: query, searchResults: results };
  }),
  clearSearch: () => set({ searchQuery: '', searchResults: [] }),
  setScrollToMessageId: (messageId) => set({ scrollToMessageId: messageId }),
  
  addSkill: (skill) => set((state) => {
    const newSkills = [...state.skills, { ...skill, createdAt: Date.now(), updatedAt: Date.now() }];
    saveToStorage(STORAGE_KEYS.SKILLS, newSkills);
    return { skills: newSkills };
  }),
  
  updateSkill: (skillId, updates) => set((state) => {
    const newSkills = state.skills.map(s => 
      s.id === skillId ? { ...s, ...updates, updatedAt: Date.now() } : s
    );
    saveToStorage(STORAGE_KEYS.SKILLS, newSkills);
    return { skills: newSkills };
  }),
  
  toggleSkill: (skillId) => set((state) => {
    const newSkills = state.skills.map(s => 
      s.id === skillId ? { ...s, enabled: !s.enabled } : s
    );
    saveToStorage(STORAGE_KEYS.SKILLS, newSkills);
    return { skills: newSkills };
  }),
  
  removeSkill: (skillId) => set((state) => {
    const newSkills = state.skills.filter(s => s.id !== skillId);
    saveToStorage(STORAGE_KEYS.SKILLS, newSkills);
    return { skills: newSkills };
  }),
  
  addMemory: (memory) => set((state) => {
    const newMemories = [...state.memories, memory];
    saveToStorage(STORAGE_KEYS.MEMORIES, newMemories);
    return { memories: newMemories };
  }),
  
  removeMemory: (memoryId) => set((state) => {
    const newMemories = state.memories.filter(m => m.id !== memoryId);
    saveToStorage(STORAGE_KEYS.MEMORIES, newMemories);
    return { memories: newMemories };
  }),
  
  updateMemory: (memoryId, content) => set((state) => {
    const newMemories = state.memories.map(m => 
      m.id === memoryId ? { ...m, content } : m
    );
    saveToStorage(STORAGE_KEYS.MEMORIES, newMemories);
    return { memories: newMemories };
  }),
  
  setSkills: (skills) => {
    saveToStorage(STORAGE_KEYS.SKILLS, skills);
    set({ skills });
  },
  setMemories: (memories) => {
    saveToStorage(STORAGE_KEYS.MEMORIES, memories);
    set({ memories });
  },
  
  // Channel actions
  addChannel: (channel) => set((state) => {
    const newChannels = [...state.channels, channel];
    saveToStorage(STORAGE_KEYS.CHANNELS, newChannels);
    return { channels: newChannels };
  }),
  
  updateChannel: (id, updates) => set((state) => {
    const newChannels = state.channels.map(c => 
      c.id === id ? { ...c, ...updates } : c
    );
    saveToStorage(STORAGE_KEYS.CHANNELS, newChannels);
    return { channels: newChannels };
  }),
  
  removeChannel: (id) => set((state) => {
    const newChannels = state.channels.filter(c => c.id !== id);
    saveToStorage(STORAGE_KEYS.CHANNELS, newChannels);
    return { channels: newChannels };
  }),
  
  toggleChannel: (id) => set((state) => {
    const newChannels = state.channels.map(c => 
      c.id === id ? { ...c, enabled: !c.enabled } : c
    );
    saveToStorage(STORAGE_KEYS.CHANNELS, newChannels);
    return { channels: newChannels };
  }),
  
  // OpenHarness config actions
  setOpenHarnessConfig: (config) => {
    saveToStorage(STORAGE_KEYS.OPENHARNESS_CONFIG, config);
    set({ openHarnessConfig: config });
  },
  
  updateOpenHarnessConfig: (updates) => set((state) => {
    if (!state.openHarnessConfig) return state;
    const newConfig = { ...state.openHarnessConfig, ...updates };
    saveToStorage(STORAGE_KEYS.OPENHARNESS_CONFIG, newConfig);
    return { openHarnessConfig: newConfig };
  }),
}));