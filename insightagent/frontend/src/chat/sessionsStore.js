import { ref } from 'vue'
import { api } from '../api'

// 桌面侧边栏与聊天区共享的会话列表
export const sessionList = ref([])
export const sessionsLoading = ref(false)
export const sessionsError = ref('')

export async function loadSessions() {
  sessionsLoading.value = true
  sessionsError.value = ''
  try {
    const data = await api.sessions()
    sessionList.value = data.sessions || []
  } catch (e) {
    sessionsError.value = e.message
  } finally {
    sessionsLoading.value = false
  }
}

export async function removeSession(id) {
  await api.deleteSession(id)
  sessionList.value = sessionList.value.filter((s) => s.session_id !== id)
}

export function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 时前`
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

export function titleOf(item) {
  return (item.summary || '').trim() || '未命名会话'
}
