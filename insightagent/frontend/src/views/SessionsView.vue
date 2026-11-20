<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { auth, toast } from '../store'
import AppIcon from '../components/AppIcon.vue'
import AppSheet from '../components/AppSheet.vue'

defineOptions({ name: 'SessionsView' })

const router = useRouter()
const sessions = ref([])
const loading = ref(true)
const err = ref('')
const pendingDelete = ref(null)

const totalMessages = computed(() => sessions.value.reduce((n, s) => n + (s.message_count || 0), 0))

async function load() {
  loading.value = true
  err.value = ''
  try {
    const data = await api.sessions()
    sessions.value = data.sessions || []
  } catch (e) {
    err.value = e.message
  } finally {
    loading.value = false
  }
}

function open(item) {
  router.push(`/chat/${encodeURIComponent(item.session_id)}`)
}

function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = Date.now()
  const diff = (now - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

function titleOf(item) {
  return (item.summary || '').trim() || '未命名会话'
}

async function confirmDelete() {
  const item = pendingDelete.value
  if (!item) return
  try {
    await api.deleteSession(item.session_id)
    sessions.value = sessions.value.filter((s) => s.session_id !== item.session_id)
    toast('会话已删除')
  } catch (e) {
    if (e.status !== 404) toast(e.message)
    else sessions.value = sessions.value.filter((s) => s.session_id !== item.session_id)
  } finally {
    pendingDelete.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="page page-sessions">
    <div class="page-head">
      <div>
        <h1 class="page-title">会话</h1>
        <p class="page-sub">{{ auth.user?.display_name || '' }} · 我的分析记录</p>
      </div>
      <button class="btn btn-primary btn-sm" @click="router.push('/chat')">
        <AppIcon name="plus" :size="15" /> 新建
      </button>
    </div>

    <div class="stat-split">
      <div>
        <div class="stat-num">{{ sessions.length }}</div>
        <div class="stat-label">会话数</div>
      </div>
      <div>
        <div class="stat-num">{{ totalMessages }}</div>
        <div class="stat-label">消息数</div>
      </div>
    </div>

    <p v-if="err" class="err">{{ err }}</p>

    <div v-if="loading" class="empty">正在加载…</div>
    <div v-else-if="!sessions.length" class="empty">
      <span class="big">书架还是空的</span>
      点击右上角「新建」，开始你的第一次数据分析
    </div>

    <div v-else class="shelf">
      <div v-for="s in sessions" :key="s.session_id" class="shelf-item" @click="open(s)">
        <div class="shelf-name">{{ titleOf(s) }}</div>
        <div class="shelf-meta">
          <span>{{ fmtTime(s.updated_at) }}</span>
          <button
            class="icon-btn"
            style="width: 24px; height: 24px; box-shadow: none; background: transparent"
            @click.stop="pendingDelete = s"
          >
            <AppIcon name="trash" :size="14" />
          </button>
        </div>
      </div>
    </div>

    <AppSheet v-if="pendingDelete" title="删除会话" icon="trash" @close="pendingDelete = null">
      <p class="hint" style="margin: 0 4px 16px">
        将永久删除「{{ titleOf(pendingDelete) }}」的会话记录与产出文件，且不可恢复。
      </p>
      <div style="display: flex; gap: 10px">
        <button class="btn btn-ghost" style="flex: 1" @click="pendingDelete = null">取消</button>
        <button class="btn btn-primary" style="flex: 1" @click="confirmDelete">删除</button>
      </div>
    </AppSheet>
  </div>
</template>
