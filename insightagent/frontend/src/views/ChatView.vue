<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from '../store'
import { useChatSession } from '../chat/useChatSession'
import AppIcon from '../components/AppIcon.vue'
import AppSheet from '../components/AppSheet.vue'

defineOptions({ name: 'ChatView' })

const router = useRouter()
const activeSheet = ref('') // plugins | mcp | skills | models | files

const {
  sessionId,
  messages,
  input,
  sending,
  loading,
  headerTitle,
  caps,
  files,
  scroller,
  fileInput,
  artifacts,
  selected,
  profileLabel,
  send,
  onKeydown,
  pickFiles,
  onFilesPicked,
  removeFile,
  loadArtifacts,
  previewLink,
  downloadLink,
  sizeText,
  toggle,
  fmtUsage,
} = useChatSession()

async function openFiles() {
  if (!sessionId.value) return toast('还没有产出文件')
  await loadArtifacts()
  activeSheet.value = 'files'
}
</script>

<template>
  <div class="chat-page">
    <div class="nav-head">
      <button class="icon-btn" @click="router.push('/sessions')">
        <AppIcon name="chevronLeft" :size="19" />
      </button>
      <div class="nav-title">{{ headerTitle }}</div>
      <button class="icon-btn" @click="openFiles" title="产出文件">
        <AppIcon name="file" :size="17" />
      </button>
    </div>

    <div ref="scroller" class="chat-scroll">
      <div v-if="loading" class="empty">正在加载会话…</div>
      <div v-else-if="!messages.length" class="empty">
        <span class="big">问点什么吧</span>
        选择模型与能力后直接提问，例如「统计最近 7 天的订单量并画出趋势」
      </div>

      <template v-for="(m, i) in messages" :key="i">
        <div v-if="m.role === 'user'" class="msg user">
          <div class="bubble">{{ m.text }}</div>
        </div>
        <div v-else class="msg assistant">
          <div v-if="m.thinking" class="thinking">{{ m.thinking }}</div>
          <div v-if="m.tools && m.tools.length" style="margin-bottom: 4px">
            <div v-for="(t, ti) in m.tools" :key="ti" class="tool-line" :class="{ running: !t.done }">
              <span class="dot" />
              <span>{{ t.name }} {{ t.done ? (t.error ? '失败' : '完成') : '执行中…' }}</span>
            </div>
          </div>
          <div v-if="m.text" class="bubble">{{ m.text }}</div>
          <div v-if="m.skipped && m.skipped.length" class="skipped">
            <div v-for="(s, si) in m.skipped" :key="si">
              {{ s.plugin || s.mcp || s.skill || s.name }}：{{ s.reason }}
            </div>
          </div>
          <div v-if="m.error" class="skipped" style="color: var(--rose); background: rgba(232,96,94,.08)">
            {{ m.error }}
          </div>
          <div v-if="m.usage" class="msg-meta">{{ fmtUsage(m.usage) }}</div>
        </div>
      </template>
    </div>

    <div v-if="files.length" class="picker-row">
      <span v-for="f in files" :key="f.name" class="chip on">
        <AppIcon name="file" :size="12" /> {{ f.name }}
        <button style="display: flex; margin-left: 2px" @click="removeFile(f.name)">
          <AppIcon name="close" :size="12" />
        </button>
      </span>
    </div>

    <div class="picker-row">
      <button class="chip" :class="{ on: selected.profile }" @click="activeSheet = 'models'">
        <AppIcon name="cpu" :size="13" /> {{ profileLabel }}
      </button>
      <button class="chip" :class="{ on: selected.plugins.length }" @click="activeSheet = 'plugins'">
        <AppIcon name="plug" :size="13" /> 插件 {{ selected.plugins.length || '' }}
      </button>
      <button class="chip" :class="{ on: selected.mcp.length }" @click="activeSheet = 'mcp'">
        <AppIcon name="server" :size="13" /> MCP {{ selected.mcp.length || '' }}
      </button>
      <button class="chip" :class="{ on: selected.skills.length }" @click="activeSheet = 'skills'">
        <AppIcon name="sparkles" :size="13" /> 技能 {{ selected.skills.length || '' }}
      </button>
    </div>

    <div class="composer">
      <button class="icon-btn" style="box-shadow: none; background: transparent" @click="pickFiles">
        <AppIcon name="paperclip" :size="20" />
      </button>
      <input ref="fileInput" type="file" multiple style="display: none" @change="onFilesPicked" />
      <textarea
        v-model="input"
        rows="1"
        placeholder="输入你的问题…"
        @keydown="onKeydown"
      />
      <button class="send-btn" :disabled="sending || !input.trim()" @click="send">
        <span v-if="sending" class="spin" />
        <AppIcon v-else name="send" :size="18" />
      </button>
    </div>

    <!-- 能力选择器 -->
    <AppSheet v-if="activeSheet === 'models'" title="选择模型服务" icon="cpu" @close="activeSheet = ''">
      <div v-if="!caps.profiles.items?.length" class="empty" style="padding: 20px">
        还没有可用的模型服务，请到「我的 → 模型服务」配置
      </div>
      <div v-else class="group-list">
        <button
          v-for="p in caps.profiles.items"
          :key="p.name"
          class="row"
          style="width: 100%; text-align: left"
          @click="((selected.profile = p.name), (activeSheet = ''))"
        >
          <div class="row-main">
            <div class="row-title">{{ p.label || p.name }}</div>
            <div class="row-sub">
              {{ p.model || '未指定模型' }} · {{ p.scope === 'user' ? '自定义' : '系统' }}
              <span v-if="!p.ready" style="color: var(--rose)"> · 缺少密钥</span>
            </div>
          </div>
          <div v-if="selected.profile === p.name" class="row-tail" style="color: var(--brand)">
            <AppIcon name="check" :size="18" />
          </div>
        </button>
      </div>
    </AppSheet>

    <AppSheet v-if="activeSheet === 'plugins'" title="选择插件" icon="plug" @close="activeSheet = ''">
      <div v-if="!caps.plugins?.length" class="empty" style="padding: 20px">暂无可用插件</div>
      <div v-else class="group-list">
        <button
          v-for="p in caps.plugins"
          :key="p.name"
          class="row"
          style="width: 100%; text-align: left"
          @click="toggle(selected.plugins, p.name)"
        >
          <div class="row-main">
            <div class="row-title">{{ p.name }}</div>
            <div class="row-sub">{{ p.description || '—' }}</div>
          </div>
          <div class="row-tail">
            <span class="tag" :class="p.scope === 'user' ? 'tag-purple' : 'tag-gray'">
              {{ p.scope === 'user' ? '自定义' : '内置' }}
            </span>
            <AppIcon v-if="selected.plugins.includes(p.name)" name="check" :size="18" style="color: var(--brand)" />
          </div>
        </button>
      </div>
    </AppSheet>

    <AppSheet v-if="activeSheet === 'mcp'" title="选择 MCP 服务" icon="server" @close="activeSheet = ''">
      <div v-if="!caps.mcp_servers?.length" class="empty" style="padding: 20px">
        暂无 MCP 服务，可在「我的 → MCP 服务」添加
      </div>
      <div v-else class="group-list">
        <button
          v-for="s in caps.mcp_servers"
          :key="s.name"
          class="row"
          style="width: 100%; text-align: left"
          :disabled="!s.ready"
          @click="toggle(selected.mcp, s.name)"
        >
          <div class="row-main">
            <div class="row-title">{{ s.name }}</div>
            <div class="row-sub">
              {{ s.ready ? `${s.tools?.length || 0} 个工具` : `不可用：${s.detail || s.state}` }}
            </div>
          </div>
          <div class="row-tail">
            <span class="tag" :class="s.ready ? 'tag-green' : 'tag-rose'">{{ s.ready ? '在线' : '离线' }}</span>
            <AppIcon v-if="selected.mcp.includes(s.name)" name="check" :size="18" style="color: var(--brand)" />
          </div>
        </button>
      </div>
    </AppSheet>

    <AppSheet v-if="activeSheet === 'skills'" title="选择技能" icon="sparkles" @close="activeSheet = ''">
      <div v-if="!caps.skills?.length" class="empty" style="padding: 20px">暂无可用技能</div>
      <div v-else class="group-list">
        <button
          v-for="s in caps.skills"
          :key="s.name"
          class="row"
          style="width: 100%; text-align: left"
          @click="toggle(selected.skills, s.name)"
        >
          <div class="row-main">
            <div class="row-title">{{ s.name }}</div>
            <div class="row-sub">{{ s.description || '—' }}</div>
          </div>
          <div class="row-tail">
            <span class="tag" :class="s.scope === 'user' ? 'tag-purple' : 'tag-gray'">
              {{ s.scope === 'user' ? '自定义' : '内置' }}
            </span>
            <AppIcon v-if="selected.skills.includes(s.name)" name="check" :size="18" style="color: var(--brand)" />
          </div>
        </button>
      </div>
    </AppSheet>

    <AppSheet v-if="activeSheet === 'files'" title="产出与附件" icon="file" @close="activeSheet = ''">
      <div class="sec-title" style="margin-top: 0">产出文件</div>
      <div v-if="!artifacts.outputs?.length" class="hint">暂无产出文件</div>
      <div v-else class="group-list">
        <div v-for="f in artifacts.outputs" :key="f.name" class="row">
          <div class="row-main">
            <div class="row-title">{{ f.name }}</div>
            <div class="row-sub">{{ sizeText(f.size) }}</div>
          </div>
          <div class="row-tail">
            <a :href="previewLink('outputs', f.name)" target="_blank" rel="noopener">预览</a>
            <a :href="downloadLink('outputs', f.name)">下载</a>
          </div>
        </div>
      </div>

      <div class="sec-title">上传附件</div>
      <div v-if="!artifacts.uploads?.length" class="hint">暂无附件</div>
      <div v-else class="group-list">
        <div v-for="f in artifacts.uploads" :key="f.name" class="row">
          <div class="row-main">
            <div class="row-title">{{ f.name }}</div>
            <div class="row-sub">{{ sizeText(f.size) }}</div>
          </div>
          <div class="row-tail">
            <a :href="previewLink('uploads', f.name)" target="_blank" rel="noopener">预览</a>
            <a :href="downloadLink('uploads', f.name)">下载</a>
          </div>
        </div>
      </div>
    </AppSheet>
  </div>
</template>
