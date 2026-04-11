export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool' | 'tool_result';
  content: string;
  timestamp: number;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  is_error?: boolean;
  responseTime?: number;  // Time in milliseconds for assistant responses
  tokenUsage?: {
    input: number;
    output: number;
    total: number;
  };
}

export interface TaskSnapshot {
  id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress?: number;
  status_note?: string;
  type: 'local_bash' | 'local_agent';
}

export interface SessionState {
  permission_mode?: string;
  model?: string;
  theme?: string;
  working_directory?: string;
  max_turns?: number;
}

export interface McpServerSnapshot {
  name: string;
  status: 'connected' | 'disconnected' | 'error';
  tools?: string[];
  config?: Record<string, unknown>;
}

export interface BridgeSessionSnapshot {
  id: string;
  name: string;
  status: string;
}

// Permission Modal Types
export interface PermissionModalRequest {
  kind: 'permission';
  request_id: string;
  tool_name: string;
  reason: string;
}

export interface QuestionModalRequest {
  kind: 'question';
  request_id: string;
  question: string;
}

export type ModalRequest = PermissionModalRequest | QuestionModalRequest;

export interface BackendEvent {
  type: 'ready' | 'state_snapshot' | 'tasks_snapshot' | 'transcript_item' | 
        'assistant_delta' | 'assistant_complete' | 'line_complete' | 
        'modal_request' | 'select_request' | 'error' | 'mcp_servers' | 
        'bridge_sessions' | 'todo_updated' | 'swarm_teammates' | 
        'swarm_notifications' | 'token_usage' | 'state_update' | 
        'permission_response_ack' | 'conversation_cleared' | 'config_saved' |
        'system' | 'status';
  state?: Record<string, unknown>;
  tasks?: TaskSnapshot[];
  item?: TranscriptItem;
  message?: string;
  commands?: string[];
  mcp_servers?: McpServerSnapshot[];
  bridge_sessions?: BridgeSessionSnapshot[];
  modal?: ModalRequest;
  select_request?: {
    title: string;
    command: string;
    options: SelectOptionPayload[];
  };
  todo_markdown?: string;
  // Token usage data
  token_usage?: {
    input: number;
    output: number;
    total: number;
  };
  message_id?: string;
  response_time?: number;
  // Permission mode update
  permission_mode?: string;
  // Permission response acknowledgment
  request_id?: string;
  success?: boolean;
  error?: string;
  // Config saved event
  settings?: Record<string, unknown>;
}

export interface TranscriptItem {
  role: 'user' | 'assistant' | 'system' | 'tool' | 'tool_result' | 'log';
  text?: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  output?: string;
  is_error?: boolean;
  token_usage?: {
    input: number;
    output: number;
    total: number;
  };
  response_time?: number;
}

export interface SelectOptionPayload {
  value: string;
  label: string;
  description?: string;
  active?: boolean;
}

export interface SwarmTeammateSnapshot {
  agent_id: string;
  name: string;
  status: string;
  task?: string;
}

export interface SwarmNotificationSnapshot {
  id: string;
  message: string;
  timestamp: number;
  type: 'info' | 'warning' | 'error';
}

export interface UploadedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  content?: string;
  status: 'pending' | 'uploading' | 'uploaded' | 'error';
  file?: File;
}

export interface ChatSession {
  id: string;
  name: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
  model?: string;
}

export interface McpServerConfig {
  name: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
}

export interface SwarmConfig {
  teamName: string;
  agents: string[];
}

export interface TodoItem {
  text: string;
  checked: boolean;
}

export interface AppSettings {
  apiKey: string;
  model: string;
  permissionMode: 'plan' | 'default' | 'full_auto';
  theme: 'dark' | 'light';
  workingDirectory: string;
  maxTurns: number;
  effort: 'low' | 'medium' | 'high';
  passes: number;
  verbose: boolean;
  vimMode: boolean;
  fastMode: boolean;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  icon?: string;
  script?: string;          // Script content (inline script)
  scriptPath?: string;      // Path to script file
  scriptType?: 'python' | 'bash' | 'javascript' | 'other';  // Script language
  author?: string;          // Author name
  version?: string;         // Version string
  source?: 'local' | 'github' | 'clawhub' | 'upload';  // Where the skill came from
  sourceUrl?: string;       // URL if imported from remote
  createdAt?: number;       // Creation timestamp
  updatedAt?: number;       // Last update timestamp
  tags?: string[];          // Tags for categorization
}

export interface MemoryItem {
  id: string;
  content: string;
  createdAt: number;
  type: 'fact' | 'preference' | 'context';
}

// Channel Configuration
export interface ChannelConfig {
  id: string;
  type: 'discord' | 'telegram';
  enabled: boolean;
  name: string;
  config: DiscordConfig | TelegramConfig;
}

export interface DiscordConfig {
  botToken: string;
  channelId: string;
  guildId?: string;
  prefix?: string;
}

export interface TelegramConfig {
  botToken: string;
  chatId: string;
  threadId?: string;
}

// OpenHarness Configuration
export interface OpenHarnessConfig {
  // Engine
  engine: {
    maxTurns: number;
    timeout: number;
    streamingEnabled: boolean;
  };
  
  // Reasoning
  reasoning: {
    effort: 'low' | 'medium' | 'high';
    passes: number;
  };
  
  // UI
  ui: {
    verbose: boolean;
    vimMode: boolean;
    fastMode: boolean;
  };
  
  // Tools
  tools: {
    enabled: string[];
    disabled: string[];
  };
  
  // Skills
  skills: {
    enabled: string[];
    autoLoad: boolean;
  };
  
  // Plugins
  plugins: {
    enabled: string[];
  };
  
  // Permissions
  permissions: {
    mode: 'default' | 'plan' | 'auto';
    allowedPaths: string[];
    deniedCommands: string[];
  };
  
  // Hooks
  hooks: {
    preToolUse: string[];
    postToolUse: string[];
  };
  
  // Commands
  commands: {
    enabled: string[];
    aliases: Record<string, string>;
  };
  
  // MCP
  mcp: {
    servers: McpServerConfig[];
    autoConnect: boolean;
  };
  
  // Memory
  memory: {
    enabled: boolean;
    persistAcrossSessions: boolean;
    maxItems: number;
  };
  
  // Tasks
  tasks: {
    maxConcurrent: number;
    autoResume: boolean;
  };
  
  // Coordinator (Multi-Agent)
  coordinator: {
    enabled: boolean;
    maxAgents: number;
    defaultTeam?: string;
  };
  
  // Prompts
  prompts: {
    systemPrompt?: string;
    contextFiles: string[];
  };
  
  // Config
  config: {
    workingDirectory: string;
    apiKey?: string;
    model: string;
    theme: 'dark' | 'light';
  };
  
  // Channels
  channels: ChannelConfig[];
}
