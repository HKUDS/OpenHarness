import { computed, reactive, ref } from 'vue'
import { api } from '../api'

// 桌面控制台共享的能力目录与选择状态（侧边栏能力中心、输入区共用）
export const caps = ref({ plugins: [], mcp_servers: [], skills: [], profiles: { items: [], default: '' } })
export const selected = reactive({ plugins: [], mcp: [], skills: [], profile: '' })
const loading = ref(false)
let loaded = false

export const readyProfiles = computed(() => (caps.value.profiles?.items || []).filter((p) => p.ready))

export const profileLabel = computed(() => {
  const p = (caps.value.profiles?.items || []).find((x) => x.name === selected.profile)
  return p ? p.label || p.name : '默认模型'
})

export function toggle(list, name) {
  const i = list.indexOf(name)
  if (i >= 0) list.splice(i, 1)
  else list.push(name)
}

export async function loadCaps(force = false) {
  if (loading.value) return
  if (loaded && !force) return
  loading.value = true
  try {
    const data = await api.capabilities()
    caps.value = data
    const items = data.profiles?.items || []
    if (selected.profile && !items.some((p) => p.name === selected.profile && p.ready)) selected.profile = ''
    if (!selected.profile) {
      const def = data.profiles?.default
      const pick = items.find((p) => p.name === def && p.ready) || items.find((p) => p.ready)
      selected.profile = pick ? pick.name : ''
    }
    selected.plugins = selected.plugins.filter((n) => (data.plugins || []).some((p) => p.name === n))
    selected.mcp = selected.mcp.filter((n) => (data.mcp_servers || []).some((p) => p.name === n && p.ready))
    selected.skills = selected.skills.filter((n) => (data.skills || []).some((p) => p.name === n))
    loaded = true
  } finally {
    loading.value = false
  }
}
