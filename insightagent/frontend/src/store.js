import { reactive, ref } from 'vue'
import { api, clearAuth, getUser, setAuth } from './api'

// ── 全局 Toast（深色胶囊） ──
export const toasts = reactive([])
let toastSeq = 0
export function toast(message, { icon = true, duration = 2200 } = {}) {
  const id = ++toastSeq
  toasts.push({ id, message, icon })
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id)
    if (i >= 0) toasts.splice(i, 1)
  }, duration)
}

// ── 认证状态 ──
export const auth = reactive({
  user: getUser(),
  ready: false,
})

export const isAuthed = ref(Boolean(getUser()))

export async function refreshMe() {
  try {
    const data = await api.me()
    auth.user = data.user
    isAuthed.value = true
    setAuth(null, data.user)
  } catch (err) {
    if (err.status === 401) {
      auth.user = null
      isAuthed.value = false
    }
  } finally {
    auth.ready = true
  }
}

export async function doLogin(username, password) {
  const data = await api.login({ username, password })
  setAuth(data.token, data.user)
  auth.user = data.user
  isAuthed.value = true
  auth.ready = true
  return data.user
}

export async function doRegister(username, password, displayName) {
  const data = await api.register({ username, password, display_name: displayName || '' })
  setAuth(data.token, data.user)
  auth.user = data.user
  isAuthed.value = true
  auth.ready = true
  return data.user
}

export async function doLogout() {
  try {
    await api.logout()
  } catch {
    /* 已失效也照常清理本地状态 */
  }
  clearAuth()
  auth.user = null
  isAuthed.value = false
}
