<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, setAuth } from '../api'
import { auth, doLogout, toast } from '../store'
import AppIcon from '../components/AppIcon.vue'
import AppSheet from '../components/AppSheet.vue'

defineOptions({ name: 'SettingsView' })

const router = useRouter()

const sheet = ref('')
const loading = ref(true)
const settings = ref({ active_profile: null, profiles: { items: [], default: '' }, raw_user_profiles: {} })
const caps = ref({ mcp_servers: [] })
const sessionCount = ref(0)

const systemProfiles = computed(() =>
  (settings.value.profiles?.items || []).filter((p) => p.scope === 'system'),
)
const userProfiles = computed(() =>
  (settings.value.profiles?.items || []).filter((p) => p.scope === 'user'),
)
const availableProfiles = computed(() => [...systemProfiles.value, ...userProfiles.value])
const activeProfile = computed(() => settings.value.active_profile || settings.value.profiles?.default || '')

const avatarText = computed(() => {
  const name = auth.user?.display_name || auth.user?.username || '?'
  return name.trim().charAt(0).toUpperCase()
})

const createdText = computed(() => {
  const raw = auth.user?.created_at
  if (!raw) return ''
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} 加入`
})

async function load() {
  loading.value = true
  try {
    const [st, cp, ses] = await Promise.all([api.userSettings(), api.capabilities(), api.sessions()])
    settings.value = st
    caps.value = cp
    sessionCount.value = ses.sessions?.length || 0
  } catch (e) {
    toast(e.message)
  } finally {
    loading.value = false
  }
}

// ── 昵称 ──
const nameForm = reactive({ display_name: '' })
const nameErr = ref('')

function openName() {
  nameForm.display_name = auth.user?.display_name || ''
  nameErr.value = ''
  sheet.value = 'name'
}

async function saveName() {
  const value = nameForm.display_name.trim()
  if (!value) return (nameErr.value = '请输入昵称')
  try {
    const data = await api.updateProfile({ display_name: value })
    auth.user = data.user
    setAuth(null, data.user)
    toast('昵称已更新')
    sheet.value = ''
  } catch (e) {
    nameErr.value = e.message
  }
}

// ── 模型服务 ──
const pf = reactive({
  editing: false,
  name: '',
  label: '',
  api_format: 'openai',
  base_url: '',
  default_model: '',
  api_key: '',
  context_window_tokens: '',
  hasKey: false,
})
const pfErr = ref('')
const pfSaving = ref(false)

function openProfile(name) {
  pfErr.value = ''
  pfSaving.value = false
  const raw = name ? settings.value.raw_user_profiles?.[name] || {} : {}
  pf.editing = Boolean(name)
  pf.name = name || ''
  pf.label = raw.label || ''
  pf.api_format = raw.api_format || 'openai'
  pf.base_url = raw.base_url || ''
  pf.default_model = raw.default_model || ''
  pf.api_key = ''
  pf.context_window_tokens = raw.context_window_tokens ? String(raw.context_window_tokens) : ''
  pf.hasKey = Boolean((settings.value.profiles?.items || []).find((p) => p.name === name)?.has_api_key)
  sheet.value = 'profile'
}

async function saveProfile() {
  pfErr.value = ''
  const name = pf.name.trim()
  if (!name) return (pfErr.value = '请填写配置名称（英文标识，如 my-glm）')
  if (!pf.default_model.trim()) return (pfErr.value = '请填写默认模型')
  pfSaving.value = true
  try {
    await api.saveProfile({
      name,
      label: pf.label.trim() || name,
      provider: '',
      api_format: pf.api_format,
      base_url: pf.base_url.trim(),
      default_model: pf.default_model.trim(),
      api_key: pf.api_key ? pf.api_key : pf.editing ? null : '',
      context_window_tokens: pf.context_window_tokens ? Number(pf.context_window_tokens) : null,
    })
    toast('模型服务已保存')
    sheet.value = ''
    await load()
  } catch (e) {
    pfErr.value = e.message
  } finally {
    pfSaving.value = false
  }
}

async function useProfile(name) {
  const isActive = activeProfile.value === name
  try {
    await api.setActiveProfile(isActive ? '' : name)
    toast(isActive ? '已取消默认' : '已设为默认模型')
    await load()
  } catch (e) {
    toast(e.message)
  }
}

const pendingDelete = ref('')
function askDeleteProfile(name) {
  pendingDelete.value = name
  sheet.value = 'del-profile'
}

async function confirmDeleteProfile() {
  try {
    await api.deleteProfile(pendingDelete.value)
    toast('已删除')
    sheet.value = ''
    await load()
  } catch (e) {
    toast(e.message)
  }
}

// ── 修改密码 ──
const pw = reactive({ old_password: '', new_password: '', confirm: '' })
const pwErr = ref('')
const pwSaving = ref(false)

function openPassword() {
  pw.old_password = ''
  pw.new_password = ''
  pw.confirm = ''
  pwErr.value = ''
  sheet.value = 'password'
}

async function savePassword() {
  pwErr.value = ''
  if (!pw.old_password) return (pwErr.value = '请输入当前密码')
  if (pw.new_password.length < 6) return (pwErr.value = '新密码至少 6 位')
  if (pw.new_password !== pw.confirm) return (pwErr.value = '两次输入的新密码不一致')
  pwSaving.value = true
  try {
    await api.changePassword({ old_password: pw.old_password, new_password: pw.new_password })
    sheet.value = ''
    toast('密码已修改，请重新登录')
    await doLogout()
    router.replace('/login')
  } catch (e) {
    pwErr.value = e.message
  } finally {
    pwSaving.value = false
  }
}

// ── 重置 / 退出 ──
const resetting = ref(false)
async function confirmReset() {
  resetting.value = true
  try {
    await api.resetHome()
    toast('已恢复默认配置')
    sheet.value = ''
    await load()
  } catch (e) {
    toast(e.message)
  } finally {
    resetting.value = false
  }
}

async function confirmLogout() {
  sheet.value = ''
  await doLogout()
  router.replace('/login')
}

onMounted(load)
</script>

<template>
  <div class="page page-settings">
    <div class="me-head">
      <div class="avatar">{{ avatarText }}</div>
      <div class="me-name">{{ auth.user?.display_name || auth.user?.username }}</div>
      <div class="me-sub">
        @{{ auth.user?.username }}
        <template v-if="createdText"> · {{ createdText }}</template>
      </div>
      <button class="btn btn-weak btn-sm me-edit" @click="openName">修改昵称</button>
    </div>

    <div class="stat-split">
      <div>
        <div class="stat-num">{{ sessionCount }}</div>
        <div class="stat-label">会话</div>
      </div>
      <div>
        <div class="stat-num">{{ availableProfiles.length }}</div>
        <div class="stat-label">可用模型</div>
      </div>
      <div>
        <div class="stat-num">{{ caps.mcp_servers?.length || 0 }}</div>
        <div class="stat-label">MCP 服务</div>
      </div>
    </div>

    <div class="sec-title">系统内置模型</div>
    <div class="group-list">
      <div
        v-for="p in systemProfiles"
        :key="p.name"
        class="row"
        @click="useProfile(p.name)"
      >
        <div class="row-icon" style="background: var(--brand-weak); color: var(--brand)">
          <AppIcon name="cpu" :size="16" />
        </div>
        <div class="row-main">
          <div class="row-title">
            {{ p.label || p.name }}
            <span class="tag tag-gray" style="margin-left: 6px">内置</span>
            <span v-if="activeProfile === p.name" class="tag tag-blue" style="margin-left: 4px">默认</span>
          </div>
          <div class="row-sub">{{ p.model || '未指定模型' }} · {{ p.api_format }}</div>
        </div>
        <div class="row-tail">
          <span class="tag" :class="p.ready ? 'tag-green' : 'tag-orange'">{{ p.ready ? '可用' : '缺密钥' }}</span>
        </div>
      </div>
      <div v-if="!loading && !systemProfiles.length" class="row">
        <div class="row-main">
          <div class="row-sub">系统暂未开放内置模型，可在下方新增自己的模型服务</div>
        </div>
      </div>
    </div>

    <div class="sec-title">我的模型</div>
    <div class="group-list">
      <div
        v-for="p in userProfiles"
        :key="p.name"
        class="row"
        @click="useProfile(p.name)"
      >
        <div class="row-icon" style="background: var(--brand-weak); color: var(--brand)">
          <AppIcon name="cpu" :size="16" />
        </div>
        <div class="row-main">
          <div class="row-title">
            {{ p.label || p.name }}
            <span v-if="activeProfile === p.name" class="tag tag-blue" style="margin-left: 6px">默认</span>
          </div>
          <div class="row-sub">{{ p.model || '未指定模型' }} · {{ p.api_format }}</div>
        </div>
        <div class="row-tail">
          <span class="tag" :class="p.ready ? 'tag-green' : 'tag-orange'">{{ p.ready ? '可用' : '缺密钥' }}</span>
          <button
            class="icon-btn"
            style="width: 26px; height: 26px; box-shadow: none; background: transparent"
            @click.stop="openProfile(p.name)"
          >
            <AppIcon name="key" :size="14" />
          </button>
          <button
            class="icon-btn"
            style="width: 26px; height: 26px; box-shadow: none; background: transparent"
            @click.stop="askDeleteProfile(p.name)"
          >
            <AppIcon name="trash" :size="14" />
          </button>
        </div>
      </div>
      <div v-if="!loading && !userProfiles.length" class="row">
        <div class="row-main">
          <div class="row-sub">还没有自定义模型服务，可新增自己的 API Key 与接入地址</div>
        </div>
      </div>
      <div class="row" @click="openProfile('')">
        <div class="row-icon" style="background: rgba(7,193,96,.1); color: var(--green)">
          <AppIcon name="plus" :size="16" />
        </div>
        <div class="row-main">
          <div class="row-title" style="color: var(--brand)">新增模型服务</div>
          <div class="row-sub">OpenAI / Anthropic 兼容接口，仅本账号可用</div>
        </div>
        <div class="row-tail"><AppIcon name="chevronRight" :size="15" /></div>
      </div>
    </div>

    <div class="sec-title">账号</div>
    <div class="group-list">
      <div class="row" @click="openPassword">
        <div class="row-icon" style="background: rgba(123,108,255,.1); color: var(--purple)">
          <AppIcon name="lock" :size="16" />
        </div>
        <div class="row-main">
          <div class="row-title">修改密码</div>
          <div class="row-sub">修改后全部设备需重新登录</div>
        </div>
        <div class="row-tail"><AppIcon name="chevronRight" :size="15" /></div>
      </div>
      <div class="row" @click="router.push('/capabilities')">
        <div class="row-icon" style="background: var(--brand-weak); color: var(--brand)">
          <AppIcon name="plug" :size="16" />
        </div>
        <div class="row-main">
          <div class="row-title">能力管理</div>
          <div class="row-sub">插件 · MCP · 技能 · 模型</div>
        </div>
        <div class="row-tail"><AppIcon name="chevronRight" :size="15" /></div>
      </div>
      <div class="row" @click="sheet = 'reset'">
        <div class="row-icon" style="background: rgba(250,157,59,.12); color: #d9821d">
          <AppIcon name="refresh" :size="16" />
        </div>
        <div class="row-main">
          <div class="row-title">重置本账号配置</div>
          <div class="row-sub">恢复默认配置与凭据，会话数据保留</div>
        </div>
        <div class="row-tail"><AppIcon name="chevronRight" :size="15" /></div>
      </div>
      <div class="row" @click="sheet = 'logout'">
        <div class="row-icon" style="background: rgba(232,96,94,.1); color: var(--rose)">
          <AppIcon name="logout" :size="16" />
        </div>
        <div class="row-main">
          <div class="row-title" style="color: var(--rose)">退出登录</div>
        </div>
      </div>
    </div>

    <!-- 昵称 -->
    <AppSheet v-if="sheet === 'name'" title="修改昵称" icon="user" @close="sheet = ''">
      <div class="field">
        <label>昵称</label>
        <div class="field-box"><input v-model="nameForm.display_name" maxlength="32" placeholder="显示名称" /></div>
      </div>
      <p v-if="nameErr" class="err">{{ nameErr }}</p>
      <button class="btn btn-primary btn-block" style="margin-top: 8px" @click="saveName">保存</button>
    </AppSheet>

    <!-- 模型服务 -->
    <AppSheet
      v-if="sheet === 'profile'"
      :title="pf.editing ? '编辑模型服务' : '新增模型服务'"
      icon="cpu"
      @close="sheet = ''"
    >
      <div class="field">
        <label>配置名称（英文标识）</label>
        <div class="field-box">
          <input v-model="pf.name" :disabled="pf.editing" placeholder="例如：my-glm" />
        </div>
      </div>
      <div class="field">
        <label>显示名称</label>
        <div class="field-box"><input v-model="pf.label" placeholder="例如：我的 GLM-4.6" /></div>
      </div>
      <div class="field">
        <label>接口格式</label>
        <div class="chip-row">
          <button class="chip" :class="{ on: pf.api_format === 'openai' }" @click="pf.api_format = 'openai'">
            OpenAI 兼容
          </button>
          <button class="chip" :class="{ on: pf.api_format === 'anthropic' }" @click="pf.api_format = 'anthropic'">
            Anthropic 兼容
          </button>
        </div>
      </div>
      <div class="field">
        <label>接入地址 Base URL</label>
        <div class="field-box">
          <input v-model="pf.base_url" placeholder="https://api.example.com/v1" />
        </div>
      </div>
      <div class="field">
        <label>默认模型</label>
        <div class="field-box"><input v-model="pf.default_model" placeholder="例如：glm-4.6" /></div>
      </div>
      <div class="field">
        <label>API Key{{ pf.editing && pf.hasKey ? '（留空保持不变）' : '' }}</label>
        <div class="field-box"><input v-model="pf.api_key" type="password" placeholder="sk-..." /></div>
      </div>
      <div class="field">
        <label>上下文窗口（可选，tokens）</label>
        <div class="field-box">
          <input v-model="pf.context_window_tokens" inputmode="numeric" placeholder="例如：200000" />
        </div>
      </div>
      <p v-if="pfErr" class="err">{{ pfErr }}</p>
      <button class="btn btn-primary btn-block" style="margin-top: 8px" :disabled="pfSaving" @click="saveProfile">
        保存
      </button>
      <p class="hint">密钥仅写入当前账号的凭据文件，不会回传或展示。</p>
    </AppSheet>

    <!-- 删除模型服务 -->
    <AppSheet v-if="sheet === 'del-profile'" title="删除模型服务" icon="trash" @close="sheet = ''">
      <p class="hint" style="margin: 0 0 14px">
        确认删除「{{ pendingDelete }}」？该配置与密钥将被清除，进行中的会话需重新选择模型。
      </p>
      <button class="btn btn-block" style="background: var(--rose); color: #fff" @click="confirmDeleteProfile">
        确认删除
      </button>
    </AppSheet>

    <!-- 修改密码 -->
    <AppSheet v-if="sheet === 'password'" title="修改密码" icon="lock" @close="sheet = ''">
      <div class="field">
        <label>当前密码</label>
        <div class="field-box"><input v-model="pw.old_password" type="password" autocomplete="current-password" /></div>
      </div>
      <div class="field">
        <label>新密码（至少 6 位）</label>
        <div class="field-box"><input v-model="pw.new_password" type="password" autocomplete="new-password" /></div>
      </div>
      <div class="field">
        <label>确认新密码</label>
        <div class="field-box"><input v-model="pw.confirm" type="password" autocomplete="new-password" /></div>
      </div>
      <p v-if="pwErr" class="err">{{ pwErr }}</p>
      <button class="btn btn-primary btn-block" style="margin-top: 8px" :disabled="pwSaving" @click="savePassword">
        确认修改
      </button>
      <p class="hint">修改成功后所有登录会话将失效，需重新登录。</p>
    </AppSheet>

    <!-- 重置配置 -->
    <AppSheet v-if="sheet === 'reset'" title="重置本账号配置" icon="refresh" @close="sheet = ''">
      <p class="hint" style="margin: 0 0 14px">
        将恢复默认 settings 与凭据、清空自定义模型与 MCP 配置；已产生的会话数据不受影响。
      </p>
      <button class="btn btn-primary btn-block" :disabled="resetting" @click="confirmReset">确认重置</button>
    </AppSheet>

    <!-- 退出登录 -->
    <AppSheet v-if="sheet === 'logout'" title="退出登录" icon="logout" @close="sheet = ''">
      <p class="hint" style="margin: 0 0 14px">退出后需重新输入账号密码登录。</p>
      <button class="btn btn-block" style="background: var(--rose); color: #fff" @click="confirmLogout">
        退出登录
      </button>
    </AppSheet>
  </div>
</template>
