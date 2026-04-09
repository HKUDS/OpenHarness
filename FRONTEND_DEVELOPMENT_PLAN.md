# OpenHarness Web 前端开发规划

## 📋 项目概述

基于当前完成的 Web API，开发一个现代化的 Web 前端界面，提供完整的 AI Agent 交互体验。

## 🎯 技术栈确定

### **核心技术栈**
```json
{
  "框架": "Vue 3.4+ (Composition API)",
  "运行时": "Bun 1.1+",
  "语言": "TypeScript 5.3+",
  "状态管理": "Pinia 2.1+",
  "路由": "Vue Router 4.2+",
  "UI组件": "Naive UI (推荐) / Element Plus",
  "样式": "UnoCSS",
  "HTTP客户端": "ofetch",
  "WebSocket": "原生 WebSocket API + 封装",
  "代码高亮": "Shiki",
  "Markdown": "markdown-it + highlight.js"
}
```

### **选择理由**

| 技术 | 理由 | 优势 |
|------|------|------|
| **Bun** | 超快性能，内置工具链 | 3-4x Node.js 性能，一体化开发体验 |
| **Vue 3** | 学习曲线平缓，优秀的TS支持 | Composition API，编译时优化 |
| **Naive UI** | 现代设计，TypeScript原生 | 主题定制，Tree Shaking友好 |
| **UnoCSS** | 即时原子CSS，零运行时 | 类Tailwind，但更快速 |
| **ofetch** | 基于fetch，更简洁 | 更好的API，自动JSON处理 |

## 🏗️ 项目架构设计

### **前端目录结构**
```
src/openharness/ui/web/frontend/
├── src/
│   ├── main.ts                    # 应用入口
│   ├── App.vue                    # 根组件
│   │
│   ├── views/                     # 页面视图
│   │   ├── ChatView.vue           # 主聊天页面
│   │   ├── SettingsView.vue       # 设置页面
│   │   ├── HistoryView.vue        # 历史会话
│   │   └── TasksView.vue          # 任务管理
│   │
│   ├── components/                # 组件库
│   │   ├── chat/
│   │   │   ├── MessageList.vue    # 消息列表容器
│   │   │   ├── MessageItem.vue    # 单条消息
│   │   │   ├── UserMessage.vue    # 用户消息组件
│   │   │   ├── AssistantMessage.vue # AI消息组件
│   │   │   ├── ToolCallMessage.vue # 工具调用消息
│   │   │   ├── PromptInput.vue    # 输入框
│   │   │   ├── SendButton.vue     # 发送按钮
│   │   │   └── PermissionModal.vue # 权限确认弹窗
│   │   │
│   │   ├── layout/
│   │   │   ├── AppLayout.vue      # 主布局
│   │   │   ├── Sidebar.vue        # 侧边栏（历史会话）
│   │   │   ├── Header.vue         # 顶部栏
│   │   │   └── StatusBar.vue      # 状态栏
│   │   │
│   │   ├── panels/
│   │   │   ├── SessionInfo.vue    # 会话信息面板
│   │   │   ├── TaskList.vue       # 任务列表面板
│   │   │   └── ConfigPanel.vue    # 配置面板
│   │   │
│   │   └── common/
│   │       ├── CodeBlock.vue      # 代码块
│   │       ├── MarkdownText.vue   # Markdown渲染
│   │       ├── LoadingSpinner.vue # 加载动画
│   │       ├── ErrorAlert.vue     # 错误提示
│   │       └── ConfirmDialog.vue  # 确认对话框
│   │
│   ├── composables/               # 组合式函数
│   │   ├── useWebSocket.ts        # WebSocket连接管理
│   │   ├── useChat.ts             # 聊天逻辑
│   │   ├── useSession.ts          # 会话管理
│   │   ├── useConfig.ts           # 配置管理
│   │   ├── useTasks.ts            # 任务管理
│   │   ├── useTheme.ts            # 主题管理
│   │   └── useDebounce.ts        # 工具函数
│   │
│   ├── stores/                    # Pinia状态管理
│   │   ├── chat.ts                # 聊天状态
│   │   ├── session.ts             # 会话状态
│   │   ├── config.ts              # 配置状态
│   │   ├── ui.ts                  # UI状态
│   │   └── tasks.ts               # 任务状态
│   │
│   ├── services/                  # API服务层
│   │   ├── api.ts                 # REST API客户端
│   │   ├── websocket.ts           # WebSocket服务
│   │   ├── types.ts               # 类型定义
│   │   └── config.ts              # API配置
│   │
│   ├── types/                     # TypeScript类型
│   │   ├── api.ts                 # API响应类型
│   │   ├── chat.ts                # 聊天相关类型
│   │   ├── config.ts              # 配置类型
│   │   └── events.ts              # WebSocket事件类型
│   │
│   ├── utils/                     # 工具函数
│   │   ├── format.ts              # 格式化函数
│   │   ├── validation.ts          # 验证函数
│   │   ├── storage.ts             # 本地存储
│   │   └── constants.ts           # 常量定义
│   │
│   ├── assets/                    # 静态资源
│   │   ├── styles/
│   │   │   ├── main.css           # 主样式
│   │   │   └── theme.css          # 主题样式
│   │   └── icons/                 # 图标
│   │
│   └── router/                    # 路由配置
│       └── index.ts               # 路由定义
│
├── public/                        # 公共资源
│   └── favicon.ico
│
├── package.json                   # 项目配置
├── bun.lockb                      # 依赖锁定
├── tsconfig.json                  # TypeScript配置
├── bunfig.toml                    # Bun配置
└── index.html                     # HTML入口
```

## 🎨 UI/UX设计原则

### **设计风格**
- **简洁现代**: 扁平化设计，清晰的视觉层次
- **暗色主题优先**: 开发者友好的暗色调界面
- **响应式布局**: 支持不同屏幕尺寸
- **可访问性**: 键盘导航，屏幕阅读器支持

### **核心界面布局**
```
┌─────────────────────────────────────────────────┐
│ Header: Logo | 搜索 | 设置 | 用户信息            │
├──────────┬──────────────────────────────────────┤
│          │                                      │
│ Sidebar  │         Main Chat Area              │
│          │  ┌────────────────────────────────┐  │
│ History  │  │        Message List            │  │  │
│ Sessions │  │    (滚动区域)                   │  │  │
│          │  ├────────────────────────────────┤  │
│ Settings │  │        Input Area              │  │  │
│ Tasks    │  │  [输入框] [发送按钮]            │  │  │
│          │  └────────────────────────────────┘  │  │
└──────────┴──────────────────────────────────────┘
```

## 🚀 开发阶段规划

### **Phase 1: 基础架构** (Week 1-2)
- [x] 项目初始化 (Bun + Vue 3 + TypeScript)
- [x] 基础UI框架搭建 (Naive UI + UnoCSS)
- [x] 路由配置
- [x] 状态管理 (Pinia stores)
- [x] API客户端封装
- [x] WebSocket服务封装

### **Phase 2: 核心聊天功能** (Week 3-4)
- [ ] 聊天主界面布局
- [ ] 消息列表组件
- [ ] 消息类型支持 (用户/AI/工具/系统)
- [ ] 输入框和发送功能
- [ ] WebSocket连接和消息处理
- [ ] 流式消息渲染
- [ ] Markdown和代码高亮
- [ ] 权限确认弹窗

### **Phase 3: 会话管理** (Week 5)
- [ ] 会话列表显示
- [ ] 创建新会话
- [ ] 切换会话
- [ ] 删除会话
- [ ] 会话信息面板

### **Phase 4: 配置和设置** (Week 6)
- [ ] 设置页面UI
- [ ] 模型选择器
- [ ] 配置参数调整
- [ ] 主题切换
- [ ] 主题自定义

### **Phase 5: 高级功能** (Week 7-8)
- [ ] 任务管理界面
- [ ] 文件上传集成
- [ ] 导出功能
- [ ] 快捷键支持
- [ ] 移动端适配

### **Phase 6: 优化和部署** (Week 9)
- [ ] 性能优化
- [ ] 错误处理完善
- [ ] 测试覆盖
- [ ] 文档编写
- [ ] 部署配置

## 📝 核心功能模块详解

### **1. WebSocket通信模块**
```typescript
// composables/useWebSocket.ts
export function useWebSocket() {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const reconnectAttempts = ref(0)

  const connect = (url: string) => {
    // WebSocket连接逻辑
  }

  const send = (message: WebSocketMessage) => {
    // 发送消息逻辑
  }

  const onMessage = (callback: (event: WebSocketEvent) => void) => {
    // 消息监听逻辑
  }

  return { connected, connect, send, onMessage }
}
```

### **2. 聊天状态管理**
```typescript
// stores/chat.ts
export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [] as Message[],
    isStreaming: false,
    currentResponse: ''
  }),

  actions: {
    addMessage(message: Message) {
      this.messages.push(message)
    },

    appendToStream(text: string) {
      this.currentResponse += text
    },

    completeStream() {
      if (this.currentResponse) {
        this.addMessage({
          role: 'assistant',
          content: this.currentResponse
        })
        this.currentResponse = ''
      }
      this.isStreaming = false
    }
  }
})
```

### **3. 消息组件设计**
```vue
<!-- components/chat/MessageItem.vue -->
<script setup lang="ts">
interface Props {
  message: Message
}

const props = defineProps<Props>()
const isStreaming = computed(() => props.message.streaming)
</script>

<template>
  <div :class="['message-item', `message-${message.role}`]">
    <div class="message-header">
      <span class="message-role">{{ message.role }}</span>
      <span class="message-time">{{ message.timestamp }}</span>
    </div>

    <div class="message-content">
      <!-- 用户消息 -->
      <template v-if="message.role === 'user'">
        <p>{{ message.content }}</p>
      </template>

      <!-- AI消息 -->
      <template v-else-if="message.role === 'assistant'">
        <MarkdownText
          :content="isStreaming ? message.content + '▌' : message.content"
          :streaming="isStreaming"
        />
      </template>

      <!-- 工具调用消息 -->
      <template v-else-if="message.role === 'tool'">
        <ToolCallMessage :tool-call="message.toolCall" />
      </template>
    </div>
  </div>
</template>
```

## 🔧 技术实现要点

### **1. 流式消息处理**
```typescript
// 处理WebSocket流式消息
const handleStreamMessage = (event: WebSocketEvent) => {
  if (event.type === 'assistant_delta') {
    // 追加文本到当前响应
    chatStore.appendToStream(event.text)
  } else if (event.type === 'assistant_complete') {
    // 完成当前响应
    chatStore.completeStream()
  }
}
```

### **2. 权限确认处理**
```typescript
// 处理工具权限请求
const handlePermissionRequest = async (event: PermissionRequestEvent) => {
  const { tool_name, tool_input, request_id } = event

  // 显示确认弹窗
  const confirmed = await showPermissionModal({
    toolName: tool_name,
    toolInput: tool_input
  })

  // 发送响应
  websocket.send({
    type: 'permission_response',
    request_id: request_id,
    allowed: confirmed
  })
}
```

### **3. 错误处理和重连**
```typescript
// WebSocket自动重连
const setupReconnect = () => {
  const reconnect = async () => {
    reconnectAttempts.value++
    if (reconnectAttempts.value <= MAX_RETRIES) {
      await delay(RECONNECT_DELAY)
      connect(url)
    }
  }

  ws.addEventListener('close', () => {
    connected.value = false
    reconnect()
  })
}
```

## 📊 性能优化策略

### **1. 消息虚拟化**
```typescript
// 使用虚拟滚动处理大量消息
import { useVirtualList } from '@vueuse/core'

const { list: virtualMessages, containerProps, wrapperProps } = useVirtualList(
  messages,
  { itemHeight: 100, overscan: 10 }
)
```

### **2. 代码分割**
```typescript
// 路由懒加载
const routes = [
  {
    path: '/chat',
    component: () => import('./views/ChatView.vue')
  },
  {
    path: '/settings',
    component: () => import('./views/SettingsView.vue')
  }
]
```

### **3. 状态持久化**
```typescript
// 本地存储重要状态
watch(() => chatStore.messages, (messages) => {
  localStorage.setItem('chat-history', JSON.stringify(messages))
}, { deep: true })
```

## 🎯 开发优先级

### **MVP (最小可行产品)**
1. ✅ 基础聊天界面
2. ✅ WebSocket连接
3. ✅ 发送/接收消息
4. ✅ 基础样式

### **核心功能**
1. ✅ 会话管理
2. ✅ 配置管理
3. ✅ Markdown渲染
4. ✅ 代码高亮

### **增强功能**
1. ✅ 任务管理
2. ✅ 文件上传
3. ✅ 高级设置
4. ✅ 导出功能

## 🚦 开始开发

### **第一步：项目初始化**
```bash
# 进入frontend目录
cd src/openharness/ui/web/frontend

# 使用Bun创建Vue项目
bun create vue@latest . --template vue-ts

# 安装依赖
bun install

# 安装UI库
bun add naive-ui
bun add -d @naive-ui/volar

# 安装工具库
bun add @vueuse/core
bun add ofetch

# 安装样式
bun add -d unocss
bun add -d @unocss/preset-icons

# 安装Markdown和代码高亮
bun add markdown-it highlight.js
bun add -d @types/markdown-it
```

这个规划为前端开发提供了清晰的路线图和技术基础。你觉得这个规划如何？有什么需要调整的地方吗？
