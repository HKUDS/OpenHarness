import { nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, streamChat } from '../api'
import { toast } from '../store'
import { caps, loadCaps, profileLabel, readyProfiles, selected, toggle } from './selection'
import { loadSessions } from './sessionsStore'

// 移动端聊天页与桌面控制台共用的会话逻辑
export function useChatSession() {
  const route = useRoute()
  const router = useRouter()

  const sessionId = ref(route.params.id ? String(route.params.id) : '')
  const messages = ref([])
  const input = ref('')
  const sending = ref(false)
  const loading = ref(true)
  const headerTitle = ref('新对话')
  const files = ref([])
  const uploading = ref(false)
  const scroller = ref(null)
  const fileInput = ref(null)
  const artifacts = ref({ outputs: [], uploads: [] })
  const artifactsLoaded = ref(false)

  let ctrl = null

  function newSessionId() {
    return 's-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8)
  }

  function ensureSession() {
    if (!sessionId.value) sessionId.value = newSessionId()
    return sessionId.value
  }

  async function scrollBottom() {
    await nextTick()
    const el = scroller.value
    if (el) el.scrollTop = el.scrollHeight
  }

  async function loadHistory() {
    if (!sessionId.value) {
      loading.value = false
      return
    }
    try {
      const data = await api.transcript(sessionId.value)
      headerTitle.value = (data.summary || '').trim() || '会话回放'
      messages.value = (data.turns || []).flatMap((t) => {
        const out = [{ role: 'user', text: t.message }]
        out.push({
          role: 'assistant',
          text: t.answer || '',
          thinking: t.thinking || '',
          tools: (t.events || [])
            .filter((e) => e.type === 'tool_started' || e.type === 'tool_completed')
            .map((e) => ({ name: e.tool_name, done: e.type === 'tool_completed', error: e.is_error })),
          error: t.error || '',
          usage: t.usage,
        })
        return out
      })
      selected.plugins = data.plugins || []
    } catch (e) {
      if (e.status === 404) {
        toast('会话不存在，已切换为新对话')
        sessionId.value = ''
        router.replace('/chat')
      } else {
        toast(e.message)
      }
    } finally {
      loading.value = false
      scrollBottom()
    }
  }

  function fmtUsage(usage) {
    if (!usage) return ''
    const parts = []
    if (usage.input_tokens != null) parts.push(`输入 ${usage.input_tokens}`)
    if (usage.output_tokens != null) parts.push(`输出 ${usage.output_tokens}`)
    return parts.join(' · ')
  }

  async function send() {
    const text = input.value.trim()
    if (!text || sending.value) return
    ensureSession()
    messages.value.push({ role: 'user', text })
    const reply = reactive({ role: 'assistant', text: '', thinking: '', tools: [], error: '', skipped: [], usage: null })
    messages.value.push(reply)
    input.value = ''
    sending.value = true
    scrollBottom()

    ctrl = new AbortController()
    try {
      await streamChat(
        {
          message: text,
          session_id: sessionId.value,
          plugins: selected.plugins.length ? selected.plugins : undefined,
          mcp_servers: selected.mcp.length ? selected.mcp : undefined,
          skills: selected.skills.length ? selected.skills : undefined,
          files: files.value.length ? files.value.map((f) => f.name) : undefined,
          profile: selected.profile || undefined,
        },
        (ev) => {
          switch (ev.type) {
            case 'assistant_delta':
              reply.text += ev.text || ''
              scrollBottom()
              break
            case 'thinking_delta':
              reply.thinking += ev.text || ''
              break
            case 'tool_started':
              reply.tools.push({ name: ev.tool_name || 'tool', done: false })
              scrollBottom()
              break
            case 'tool_completed': {
              const t = reply.tools.find((x) => x.name === (ev.tool_name || 'tool') && !x.done)
              if (t) {
                t.done = true
                t.error = Boolean(ev.is_error)
              } else {
                reply.tools.push({ name: ev.tool_name || 'tool', done: true, error: Boolean(ev.is_error) })
              }
              break
            }
            case 'turn_complete':
              if (ev.text && ev.text.length >= reply.text.length) reply.text = ev.text
              reply.usage = ev.usage
              break
            case 'error':
              reply.error = ev.message || '发生未知错误'
              break
            case 'skipped':
              reply.skipped = ev.skipped || []
              break
            default:
              break
          }
        },
        ctrl.signal
      )
      if (!reply.text && !reply.error) reply.text = '（本轮没有产生文本回答）'
      files.value = []
    } catch (e) {
      if (e && e.name === 'AbortError') {
        if (!reply.text) reply.text = '（已停止生成）'
      } else {
        reply.error = e.message || '发送失败'
        toast(e.message)
      }
    } finally {
      ctrl = null
      sending.value = false
      scrollBottom()
      loadSessions()
      if (artifactsLoaded.value) loadArtifacts()
    }
  }

  function stop() {
    if (ctrl) ctrl.abort()
  }

  function onKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault()
      send()
    }
  }

  function pickFiles() {
    fileInput.value?.click()
  }

  async function onFilesPicked(e) {
    const list = Array.from(e.target.files || [])
    e.target.value = ''
    if (!list.length) return
    ensureSession()
    uploading.value = true
    try {
      for (const f of list) {
        if (f.size > 20 * 1024 * 1024) {
          toast(`${f.name} 超过 20MB`)
          continue
        }
        const res = await api.uploadFile(sessionId.value, f)
        files.value.push({ name: res.name, size: res.size })
      }
      if (artifactsLoaded.value) loadArtifacts()
    } catch (err) {
      toast(err.message)
    } finally {
      uploading.value = false
    }
  }

  async function removeFile(name) {
    files.value = files.value.filter((f) => f.name !== name)
    if (sessionId.value) {
      try {
        await api.deleteUpload(sessionId.value, name)
      } catch {
        /* 已不存在则忽略 */
      }
    }
  }

  async function loadArtifacts() {
    if (!sessionId.value) {
      artifacts.value = { outputs: [], uploads: [] }
      return artifacts.value
    }
    try {
      artifacts.value = await api.artifacts(sessionId.value)
      artifactsLoaded.value = true
      return artifacts.value
    } catch (e) {
      toast(e.message)
      return artifacts.value
    }
  }

  function previewLink(kind, name) {
    return api.previewUrl(sessionId.value, kind, name)
  }

  function downloadLink(kind, name) {
    return api.downloadUrl(sessionId.value, kind, name)
  }

  function sizeText(n) {
    if (n < 1024) return `${n} B`
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
    return `${(n / 1024 / 1024).toFixed(1)} MB`
  }

  watch(
    () => route.params.id,
    (id) => {
      if (id && id !== sessionId.value) {
        sessionId.value = String(id)
        messages.value = []
        loading.value = true
        artifactsLoaded.value = false
        loadHistory()
      } else if (!id) {
        sessionId.value = ''
        messages.value = []
        artifacts.value = { outputs: [], uploads: [] }
        artifactsLoaded.value = false
      }
    }
  )

  onMounted(async () => {
    await Promise.all([loadCaps(), loadHistory()])
    loading.value = false
  })

  return {
    sessionId,
    messages,
    input,
    sending,
    loading,
    headerTitle,
    caps,
    files,
    uploading,
    scroller,
    fileInput,
    artifacts,
    selected,
    readyProfiles,
    profileLabel,
    loadCaps,
    loadHistory,
    send,
    stop,
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
    scrollBottom,
  }
}
