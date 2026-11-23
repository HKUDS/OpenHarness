// REST + SSE 客户端：统一鉴权头、错误归一化、流式事件解析。
const TOKEN_KEY = 'insightagent.token'
const USER_KEY = 'insightagent.user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setAuth(token, user) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(path, { method = 'GET', body, headers = {}, isForm = false } = {}) {
  const opts = { method, headers: { ...headers } }
  const token = getToken()
  if (token) opts.headers['Authorization'] = `Bearer ${token}`
  if (body !== undefined) {
    if (isForm) {
      opts.body = body
    } else {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = JSON.stringify(body)
    }
  }
  const resp = await fetch(path, opts)
  if (resp.status === 401) {
    clearAuth()
    if (!location.hash.includes('/login')) location.hash = '#/login'
    throw new ApiError('未登录或登录已过期', 401)
  }
  const text = await resp.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!resp.ok) {
    const detail = (data && (data.detail || data.message)) || (typeof data === 'string' ? data : '') || `请求失败 (${resp.status})`
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), resp.status)
  }
  return data
}

export const api = {
  // 认证
  register: (payload) => request('/api/auth/register', { method: 'POST', body: payload }),
  login: (payload) => request('/api/auth/login', { method: 'POST', body: payload }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),
  changePassword: (payload) => request('/api/auth/password', { method: 'POST', body: payload }),
  updateProfile: (payload) => request('/api/auth/profile', { method: 'POST', body: payload }),

  // 会话
  sessions: () => request('/api/sessions'),
  transcript: (sid) => request(`/api/sessions/${encodeURIComponent(sid)}/transcript`),
  history: (sid) => request(`/api/sessions/${encodeURIComponent(sid)}/history`),
  deleteSession: (sid) => request(`/api/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' }),

  // 能力
  capabilities: () => request('/api/capabilities'),

  // 用户自定义配置
  userSettings: () => request('/api/user/settings'),
  saveProfile: (payload) => request('/api/user/profiles', { method: 'PUT', body: payload }),
  deleteProfile: (name) => request(`/api/user/profiles/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  setActiveProfile: (profile) => request('/api/user/active-profile', { method: 'PUT', body: { profile } }),
  userMcp: () => request('/api/user/mcp'),
  saveMcp: (payload) => request('/api/user/mcp', { method: 'PUT', body: payload }),
  deleteMcp: (name) => request(`/api/user/mcp/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  resetHome: () => request('/api/user/home/reset', { method: 'POST' }),

  // 附件 / 产出
  artifacts: (sid) => request(`/api/sessions/${encodeURIComponent(sid)}/artifacts`),
  uploadFile: (sid, file) => {
    const form = new FormData()
    form.append('file', file)
    return request(`/api/sessions/${encodeURIComponent(sid)}/uploads`, { method: 'POST', body: form, isForm: true })
  },
  deleteUpload: (sid, name) =>
    request(`/api/sessions/${encodeURIComponent(sid)}/uploads/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  downloadUrl: (sid, kind, name) =>
    `/api/sessions/${encodeURIComponent(sid)}/${kind}/${name.split('/').map(encodeURIComponent).join('/')}?token=${encodeURIComponent(getToken())}`,
  previewUrl: (sid, kind, name) =>
    `/api/sessions/${encodeURIComponent(sid)}/preview/${kind}/${name.split('/').map(encodeURIComponent).join('/')}?token=${encodeURIComponent(getToken())}`,
}

/**
 * 流式对话：POST /api/chat 返回 SSE，逐条回调 onEvent(payload)。
 * 返回 Promise，流结束（[DONE]）后 resolve。
 */
export async function streamChat(payload, onEvent, signal) {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ ...payload, stream: true }),
    signal,
  })
  if (resp.status === 401) {
    clearAuth()
    location.hash = '#/login'
    throw new ApiError('未登录或登录已过期', 401)
  }
  if (!resp.ok) {
    const text = await resp.text()
    let detail = text
    try {
      detail = JSON.parse(text).detail || text
    } catch {
      /* 保留原文 */
    }
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), resp.status)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6)
        if (raw === '[DONE]') return
        try {
          onEvent(JSON.parse(raw))
        } catch {
          /* 忽略非法帧 */
        }
      }
    }
  }
}
