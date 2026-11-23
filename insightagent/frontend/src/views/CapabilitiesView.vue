<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { auth, toast } from '../store'
import AppIcon from '../components/AppIcon.vue'
import AppSheet from '../components/AppSheet.vue'

defineOptions({ name: 'CapabilitiesView' })

const caps = ref({ plugins: [], mcp_servers: [], skills: [], profiles: { items: [], default: '' } })
const loading = ref(true)
const activeTab = ref('plugins')
const sheet = ref('')

const tabs = [
  { key: 'plugins', label: '插件' },
  { key: 'mcp', label: 'MCP' },
  { key: 'skills', label: '技能' },
  { key: 'models', label: '模型' },
]

const mcpForm = reactive({ name: '', url: '' })
const mcpErr = ref('')
const saving = ref(false)

const counts = computed(() => ({
  plugins: caps.value.plugins?.length || 0,
  mcp: caps.value.mcp_servers?.length || 0,
  skills: caps.value.skills?.length || 0,
  models: caps.value.profiles?.items?.length || 0,
}))

async function load() {
  loading.value = true
  try {
    caps.value = await api.capabilities()
  } catch (e) {
    toast(e.message)
  } finally {
    loading.value = false
  }
}

async function saveMcp() {
  mcpErr.value = ''
  if (!mcpForm.name.trim() || !mcpForm.url.trim()) return (mcpErr.value = '请填写名称与地址')
  saving.value = true
  try {
    await api.saveMcp({ name: mcpForm.name.trim(), url: mcpForm.url.trim() })
    toast('MCP 服务已保存')
    sheet.value = ''
    mcpForm.name = ''
    mcpForm.url = ''
    await load()
  } catch (e) {
    mcpErr.value = e.message
  } finally {
    saving.value = false
  }
}

async function removeMcp(name) {
  try {
    await api.deleteMcp(name)
    toast('已删除')
    await load()
  } catch (e) {
    toast(e.message)
  }
}

function openAddMcp() {
  mcpForm.name = ''
  mcpForm.url = ''
  mcpErr.value = ''
  sheet.value = 'add-mcp'
}

onMounted(load)
</script>

<template>
  <div class="page page-caps">
    <div class="page-head">
      <div>
        <h1 class="page-title">能力</h1>
        <p class="page-sub">插件 · MCP · 技能 · 模型，按账号隔离</p>
      </div>
      <button class="icon-btn" @click="load">
        <AppIcon name="refresh" :size="16" />
      </button>
    </div>

    <div class="chip-row">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="chip"
        :class="{ on: activeTab === t.key }"
        @click="activeTab = t.key"
      >
        {{ t.label }} {{ counts[t.key] }}
      </button>
    </div>

    <div v-if="loading" class="empty">正在探测能力…</div>

    <!-- 插件 -->
    <template v-else-if="activeTab === 'plugins'">
      <div v-if="!caps.plugins.length" class="empty">暂无插件</div>
      <div v-else class="group-list">
        <div v-for="p in caps.plugins" :key="p.name" class="row">
          <div class="row-icon" style="background: var(--brand-weak); color: var(--brand)">
            <AppIcon name="plug" :size="16" />
          </div>
          <div class="row-main">
            <div class="row-title">{{ p.name }}</div>
            <div class="row-sub">{{ p.description || (p.ready ? '已就绪' : p.reason) }}</div>
          </div>
          <div class="row-tail">
            <span class="tag" :class="p.scope === 'user' ? 'tag-purple' : 'tag-gray'">
              {{ p.scope === 'user' ? '自定义' : '内置' }}
            </span>
            <span class="tag" :class="p.ready ? 'tag-green' : 'tag-orange'">
              {{ p.ready ? '就绪' : '未就绪' }}
            </span>
          </div>
        </div>
      </div>
    </template>

    <!-- MCP -->
    <template v-else-if="activeTab === 'mcp'">
      <button class="btn btn-weak btn-block btn-sm" style="margin-bottom: 12px" @click="openAddMcp">
        <AppIcon name="plus" :size="14" /> 添加自定义 MCP 服务
      </button>
      <div v-if="!caps.mcp_servers.length" class="empty">暂无 MCP 服务</div>
      <div v-else class="group-list">
        <div v-for="s in caps.mcp_servers" :key="s.name" class="row">
          <div class="row-icon" :style="s.ready
            ? 'background: rgba(7,193,96,.1); color: var(--green)'
            : 'background: rgba(232,96,94,.1); color: var(--rose)'">
            <AppIcon name="server" :size="16" />
          </div>
          <div class="row-main">
            <div class="row-title">{{ s.name }}</div>
            <div class="row-sub">{{ s.ready ? `${s.tools?.length || 0} 个工具 · ${s.transport}` : s.detail || s.state }}</div>
          </div>
          <div class="row-tail">
            <span class="tag" :class="s.scope === 'user' ? 'tag-purple' : 'tag-gray'">
              {{ s.scope === 'user' ? '自定义' : '内置' }}
            </span>
            <button
              v-if="s.scope === 'user'"
              class="icon-btn"
              style="width: 26px; height: 26px; box-shadow: none; background: transparent"
              @click="removeMcp(s.name)"
            >
              <AppIcon name="trash" :size="14" />
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- 技能 -->
    <template v-else-if="activeTab === 'skills'">
      <div v-if="!caps.skills.length" class="empty">暂无技能</div>
      <div v-else class="group-list">
        <div v-for="s in caps.skills" :key="s.name" class="row">
          <div class="row-icon" style="background: rgba(123,108,255,.1); color: var(--purple)">
            <AppIcon name="sparkles" :size="16" />
          </div>
          <div class="row-main">
            <div class="row-title">{{ s.name }}</div>
            <div class="row-sub">{{ s.description || '—' }}</div>
          </div>
          <div class="row-tail">
            <span class="tag" :class="s.scope === 'user' ? 'tag-purple' : 'tag-gray'">
              {{ s.scope === 'user' ? '自定义' : '内置' }}
            </span>
          </div>
        </div>
      </div>
    </template>

    <!-- 模型 -->
    <template v-else>
      <div v-if="!caps.profiles.items.length" class="empty">暂无模型服务</div>
      <div v-else class="group-list">
        <div v-for="p in caps.profiles.items" :key="p.name" class="row">
          <div class="row-icon" style="background: var(--brand-weak); color: var(--brand)">
            <AppIcon name="cpu" :size="16" />
          </div>
          <div class="row-main">
            <div class="row-title">
              {{ p.label || p.name }}
              <span v-if="caps.profiles.default === p.name" class="tag tag-blue" style="margin-left: 6px">默认</span>
            </div>
            <div class="row-sub">{{ p.model || '未指定模型' }} · {{ p.provider }}</div>
          </div>
          <div class="row-tail">
            <span class="tag" :class="p.scope === 'user' ? 'tag-purple' : 'tag-gray'">
              {{ p.scope === 'user' ? '自定义' : '内置' }}
            </span>
            <span class="tag" :class="p.ready ? 'tag-green' : 'tag-rose'">{{ p.ready ? '可用' : '缺密钥' }}</span>
          </div>
        </div>
      </div>
      <p class="hint">在「我的 → 模型服务」中新增或修改自己的模型配置与密钥。</p>
    </template>

    <AppSheet v-if="sheet === 'add-mcp'" title="添加 MCP 服务" icon="server" @close="sheet = ''">
      <div class="field">
        <label>名称</label>
        <div class="field-box"><input v-model="mcpForm.name" placeholder="例如：企业内部检索" /></div>
      </div>
      <div class="field">
        <label>服务地址（HTTP）</label>
        <div class="field-box"><input v-model="mcpForm.url" placeholder="http://127.0.0.1:8101/mcp" /></div>
      </div>
      <p v-if="mcpErr" class="err">{{ mcpErr }}</p>
      <button class="btn btn-primary btn-block" style="margin-top: 8px" :disabled="saving" @click="saveMcp">
        保存
      </button>
      <p class="hint">保存后会立即尝试连接探测；仅对当前账号 {{ auth.user?.display_name }} 生效。</p>
    </AppSheet>
  </div>
</template>
