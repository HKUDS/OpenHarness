<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth } from '../store'
import { caps, loadCaps, selected } from '../chat/selection'
import { fmtTime, loadSessions, removeSession, sessionList, titleOf } from '../chat/sessionsStore'
import AppIcon from '../components/AppIcon.vue'
import DesktopChat from './DesktopChat.vue'
import CapabilityCenter from './CapabilityCenter.vue'

const route = useRoute()
const router = useRouter()

const capOpen = ref('')
const online = ref(true)

const consoleMode = computed(() => route.name === 'chat' || route.name === 'sessions')
const activeId = computed(() => (route.name === 'chat' && route.params.id ? String(route.params.id) : ''))
const initial = computed(() => {
  const name = auth.user?.display_name || auth.user?.username || ''
  return name ? name.trim().charAt(0).toUpperCase() : '?'
})

const counts = computed(() => ({
  plugins: (caps.value.plugins || []).length,
  skills: (caps.value.skills || []).length,
  mcp: (caps.value.mcp_servers || []).filter((m) => m.ready).length,
}))

const serviceRows = computed(() => [
  { k: 'SERVICE', v: online.value ? '在线' : '离线', tone: online.value ? 'ok' : 'bad' },
  { k: 'MODEL', v: selected.profile || '默认', tone: '' },
  { k: 'MCP', v: String(counts.value.mcp), tone: '' },
  { k: 'SESSIONS', v: String(sessionList.value.length), tone: '' },
])

async function refresh() {
  try {
    await loadSessions()
    online.value = true
  } catch {
    online.value = false
  }
}

function newChat() {
  router.push('/chat')
}

function openSession(id) {
  router.push(`/chat/${id}`)
}

async function delSession(e, id) {
  e.stopPropagation()
  if (!window.confirm('删除这个会话？该会话的产出文件也会一并删除。')) return
  await removeSession(id)
  if (activeId.value === id) router.push('/chat')
}

watch(
  () => route.fullPath,
  () => {
    if (consoleMode.value) refresh()
    else loadSessions()
  }
)

onMounted(async () => {
  await Promise.all([loadCaps(), refresh()])
})
</script>

<template>
  <div class="desk">
    <aside class="rail">
      <div class="brand">
        <span class="brand-mark">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
            <path d="M3 13c3.2 0 3.2-2.2 6.4-2.2S12.6 13 15.8 13 19 10.8 21 10.8" stroke="#fff" stroke-width="1.7" stroke-linecap="round" />
            <path d="M3 17c3.2 0 3.2-2.2 6.4-2.2S12.6 17 15.8 17 19 14.8 21 14.8" stroke="rgba(255,255,255,.6)" stroke-width="1.7" stroke-linecap="round" />
          </svg>
        </span>
        <span class="brand-text">
          <span class="brand-name">Insight<em>Agent</em></span>
          <span class="brand-sub">DATA INSIGHT CONSOLE</span>
        </span>
      </div>

      <div class="sessions">
        <h2 class="side-head">
          会话
          <span class="cnt">{{ sessionList.length }}</span>
          <button class="sess-new" title="新建会话" aria-label="新建会话" @click="newChat">
            <AppIcon name="plus" :size="13" :stroke="2.1" />
          </button>
        </h2>
        <div v-if="!sessionList.length" class="sess-empty">还没有会话，点击右上角 ＋ 开始</div>
        <button
          v-for="s in sessionList"
          :key="s.session_id"
          class="sess"
          :class="{ on: activeId === s.session_id }"
          @click="openSession(s.session_id)"
        >
          <span class="sess-title">{{ titleOf(s) }}</span>
          <span class="sess-meta">
            {{ fmtTime(s.updated_at || s.created_at) }}
            <b v-if="s.message_count || s.turns">{{ s.message_count || s.turns }} 条</b>
          </span>
          <span class="sess-del" title="删除会话" @click="delSession($event, s.session_id)">×</span>
        </button>
      </div>

      <div class="plugin-box">
        <h2 class="side-head">能力</h2>
        <button class="cap-menu" data-tab="plugins" @click="capOpen = 'plugins'">
          <span class="cm-ico"><AppIcon name="plug" :size="14" :stroke="1.6" /></span>
          插件
          <span class="cm-cnt" :class="{ act: selected.plugins.length }">{{ counts.plugins }}</span>
          <span class="arr">›</span>
        </button>
        <button class="cap-menu" data-tab="skills" @click="capOpen = 'skills'">
          <span class="cm-ico"><AppIcon name="book" :size="14" :stroke="1.6" /></span>
          技能
          <span class="cm-cnt" :class="{ act: selected.skills.length }">{{ counts.skills }}</span>
          <span class="arr">›</span>
        </button>
        <button class="cap-menu" data-tab="mcp" @click="capOpen = 'mcp'">
          <span class="cm-ico"><AppIcon name="server" :size="14" :stroke="1.6" /></span>
          MCP 连接器
          <span class="cm-cnt" :class="{ act: selected.mcp.length }">{{ counts.mcp }}</span>
          <span class="arr">›</span>
        </button>
      </div>

      <div class="status">
        <div v-for="r in serviceRows" :key="r.k" class="st-row">
          <span class="st-k">{{ r.k }}</span>
          <span class="st-v" :class="r.tone">{{ r.v }}</span>
        </div>
      </div>

      <div class="account">
        <span class="acc-avatar">{{ initial }}</span>
        <span class="acc-main">
          <span class="acc-name">{{ auth.user?.display_name || auth.user?.username }}</span>
          <span class="acc-sub">@{{ auth.user?.username }}</span>
        </span>
        <router-link to="/settings" class="acc-btn" title="设置"><AppIcon name="user" :size="16" /></router-link>
      </div>
    </aside>

    <main class="main">
      <DesktopChat v-if="consoleMode" />
      <div v-else class="page-wrap">
        <router-view />
      </div>
    </main>

    <CapabilityCenter v-if="capOpen" :tab="capOpen" @close="capOpen = ''" @update:tab="capOpen = $event" />
  </div>
</template>

<style scoped>
.desk {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
}

/* ── 左侧导航 ── */
.rail {
  width: 252px;
  flex: none;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-right: 0.5px solid var(--hairline);
  padding: 16px 12px 12px;
  height: 100vh;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 6px 14px;
}

.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 11px;
  background: linear-gradient(140deg, #4c8dff, #2879ff 60%, #1b66e0);
  display: grid;
  place-items: center;
  flex: none;
  box-shadow: 0 6px 16px rgba(40, 121, 255, 0.28);
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.25;
}

.brand-name {
  font-family: var(--serif);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.3px;
  color: var(--text);
}

.brand-name em {
  font-style: normal;
  color: var(--brand);
}

.brand-sub {
  font-family: var(--mono);
  font-size: 7.5px;
  letter-spacing: 1.5px;
  color: var(--aux);
  margin-top: 2px;
}

.sess-new {
  order: 2;
  flex: none;
  width: 24px;
  height: 24px;
  margin-left: 2px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--brand-weak);
  color: var(--brand);
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
}

.sess-new svg {
  display: block;
}

.sess-new:hover {
  background: var(--brand);
  color: #fff;
  box-shadow: 0 3px 10px rgba(40, 121, 255, 0.28);
}

.side-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  padding: 0 4px 9px;
  margin: 0 0 8px;
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--text);
  line-height: 1.2;
}

.side-head::after {
  content: "";
  flex: 1;
  height: 0.5px;
  margin: 0 4px;
  order: 1;
  background: var(--hairline);
}

.side-head .cnt {
  flex: none;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
  padding: 1px 8px;
  border-radius: 99px;
  background: var(--brand-weak);
  color: var(--brand);
}

.side-head .cnt:empty {
  display: none;
}

.sessions {
  flex: 1;
  min-height: 60px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-bottom: 8px;
  margin-bottom: 4px;
}

.sess-empty {
  font-size: 11px;
  color: var(--aux);
  line-height: 1.7;
  padding: 10px 8px;
}

.sess {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border-radius: 9px;
  color: var(--body);
  transition: background 0.12s;
  flex: none;
}

.sess:hover {
  background: #f5f7fa;
}

.sess.on {
  background: var(--brand-weak);
}

.sess-title {
  font-size: 12.5px;
  line-height: 1.45;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.sess.on .sess-title {
  color: var(--brand);
  font-weight: 600;
}

.sess-meta {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--aux);
  display: flex;
  gap: 8px;
}

.sess-meta b {
  font-weight: 400;
}

.sess-del {
  position: absolute;
  right: 6px;
  top: 7px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 13px;
  color: var(--aux);
  opacity: 0;
  transition: 0.12s;
}

.sess:hover .sess-del {
  opacity: 1;
}

.sess-del:hover {
  background: var(--rose-weak);
  color: var(--rose);
}

.plugin-box {
  flex: none;
  border-top: 0.5px solid var(--hairline);
  padding-top: 13px;
  margin-top: 12px;
}

.cap-menu {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 7px 9px;
  margin-bottom: 5px;
  border-radius: 10px;
  background: var(--bg);
  font-size: 12.5px;
  color: var(--body);
  transition: all 0.15s;
  text-align: left;
}

.cap-menu:hover {
  background: var(--brand-weak);
  color: var(--brand);
}

.cm-ico {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  flex: none;
  background: var(--brand-weak);
  color: var(--brand);
}

.cap-menu[data-tab="skills"] .cm-ico {
  background: var(--green-weak);
  color: var(--green);
}

.cap-menu[data-tab="mcp"] .cm-ico {
  background: var(--purple-weak);
  color: var(--purple);
}

.cap-menu .cm-cnt {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 9.5px;
  padding: 1px 7px;
  border-radius: 99px;
  background: var(--surface);
  border: 0.5px solid var(--hairline);
  color: var(--aux);
}

.cap-menu .cm-cnt.act {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
}

.cap-menu .arr {
  color: #c8cdd4;
  font-size: 13px;
  line-height: 1;
}

.cap-menu:hover .arr {
  color: var(--brand);
}

.status {
  border-top: 0.5px solid var(--hairline);
  padding: 12px 6px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: none;
}

.st-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.st-k {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 1.3px;
  color: #b9c0cc;
}

.st-v {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--sub);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.st-v.ok {
  color: var(--green);
}

.st-v.bad {
  color: var(--rose);
}

.account {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 8px;
  border-radius: 10px;
  background: #f8fafc;
  flex: none;
}

.acc-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: linear-gradient(150deg, #6aa2ff, #2879ff);
  color: #fff;
  display: grid;
  place-items: center;
  font-family: var(--serif);
  font-size: 13px;
  font-weight: 700;
  flex: none;
}

.acc-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.3;
  flex: 1;
}

.acc-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.acc-sub {
  font-size: 9.5px;
  color: var(--aux);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.acc-btn {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  color: var(--sub);
  flex: none;
}

.acc-btn:hover {
  background: var(--brand-weak);
  color: var(--brand);
}

/* ── 主区 ── */
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.page-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
</style>
