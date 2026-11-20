<script setup>
import { computed } from 'vue'
import { caps, selected, toggle } from '../chat/selection'
import AppIcon from '../components/AppIcon.vue'

const props = defineProps({ tab: { type: String, default: 'plugins' } })
const emit = defineEmits(['close', 'update:tab'])

const tabs = [
  { key: 'plugins', label: '插件' },
  { key: 'skills', label: '技能' },
  { key: 'mcp', label: 'MCP' },
]

const items = computed(() => {
  if (props.tab === 'plugins') {
    return (caps.value.plugins || []).map((p) => ({
      name: p.name,
      desc: p.description || '—',
      scope: p.scope,
      state: 'ok',
      stateText: '可用',
      on: selected.plugins.includes(p.name),
    }))
  }
  if (props.tab === 'skills') {
    return (caps.value.skills || []).map((s) => ({
      name: s.name,
      desc: s.description || '—',
      scope: s.scope,
      state: 'ok',
      stateText: '可用',
      on: selected.skills.includes(s.name),
    }))
  }
  return (caps.value.mcp_servers || []).map((s) => ({
    name: s.name,
    desc: s.ready ? `${s.tools?.length || 0} 个工具` : `不可用：${s.detail || s.state || '未连接'}`,
    scope: s.scope,
    state: s.ready ? 'ok' : 'bad',
    stateText: s.ready ? '在线' : '离线',
    on: selected.mcp.includes(s.name),
    disabled: !s.ready,
  }))
})

const chosenList = computed(() => {
  if (props.tab === 'plugins') return selected.plugins
  if (props.tab === 'skills') return selected.skills
  return selected.mcp
})

const emptyText = computed(() => {
  if (props.tab === 'plugins') return '暂无可用插件'
  if (props.tab === 'skills') return '暂无可用技能'
  return '暂无 MCP 服务，可在「我的 → MCP 服务」添加'
})

function pick(item) {
  if (item.disabled) return
  toggle(chosenList.value, item.name)
}
</script>

<template>
  <div class="mask" @click="emit('close')" />
  <section class="cap-panel">
    <header class="cap-head">
      <div class="cap-title">
        <span class="cap-mark"><AppIcon name="sparkles" :size="16" :stroke="1.8" /></span>
        能力中心
      </div>
      <button class="cap-close" @click="emit('close')">×</button>
    </header>

    <nav class="cap-tabs">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="cap-tab"
        :class="{ on: tab === t.key }"
        @click="emit('update:tab', t.key)"
      >
        {{ t.label }}
      </button>
    </nav>

    <div class="cap-body">
      <div v-if="!items.length" class="cm-empty">{{ emptyText }}</div>
      <div
        v-for="item in items"
        :key="item.name"
        class="cm-row"
        :class="{ on: item.on, off: item.disabled }"
        @click="pick(item)"
      >
        <span class="ckb" />
        <span class="cm-main">
          <span class="nm">{{ item.name }}</span>
          <span class="d">{{ item.desc }}</span>
        </span>
        <span class="st" :class="item.state">{{ item.stateText }}</span>
        <span class="scope" :class="{ user: item.scope === 'user' }">{{ item.scope === 'user' ? '自定义' : '内置' }}</span>
      </div>
    </div>

    <footer class="cap-foot">
      <span class="sum">已选 {{ chosenList.length }} 项</span>
      <button class="cp-done" @click="emit('close')">完成</button>
    </footer>
  </section>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(20, 24, 32, 0.34);
  backdrop-filter: blur(4px);
  z-index: 120;
  animation: fade 0.18s ease;
}

.cap-panel {
  position: fixed;
  z-index: 121;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 560px;
  max-width: calc(100vw - 48px);
  max-height: 76vh;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-radius: 18px;
  overflow: hidden;
  box-shadow: 0 24px 70px rgba(20, 30, 50, 0.26);
  animation: cap-in 0.22s cubic-bezier(0.32, 0.72, 0.33, 1);
}

@keyframes cap-in {
  from {
    opacity: 0;
    transform: translate(-50%, -48%) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
}

.cap-head {
  display: flex;
  align-items: center;
  padding: 16px 20px 12px;
}

.cap-title {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: 1;
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
}

.cap-mark {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  background: var(--brand-weak);
  color: var(--brand);
}

.cap-close {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg);
  color: var(--sub);
  font-size: 16px;
  line-height: 1;
}

.cap-close:hover {
  background: var(--rose-weak);
  color: var(--rose);
}

.cap-tabs {
  display: flex;
  gap: 4px;
  padding: 0 18px 10px;
  border-bottom: 0.5px solid var(--hairline);
}

.cap-tab {
  height: 30px;
  padding: 0 14px;
  border-radius: 99px;
  font-size: 12.5px;
  color: var(--sub);
}

.cap-tab:hover {
  background: var(--bg);
}

.cap-tab.on {
  background: var(--brand-weak);
  color: var(--brand);
  font-weight: 600;
}

.cap-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 10px;
}

.cm-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
}

.cm-row:hover {
  background: #fafbfd;
}

.cm-row.off {
  opacity: 0.55;
  cursor: not-allowed;
}

.ckb {
  width: 18px;
  height: 18px;
  border-radius: 6px;
  border: 1px solid #d9dee5;
  background: var(--surface);
  flex: none;
  display: grid;
  place-items: center;
  font-size: 10px;
  color: #fff;
  font-weight: 700;
  transition: all 0.15s;
}

.cm-row.on .ckb {
  background: var(--brand);
  border-color: var(--brand);
}

.cm-row.on .ckb::after {
  content: "✓";
}

.cm-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.nm {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--text);
  word-break: break-all;
}

.d {
  font-size: 10.5px;
  color: var(--aux);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.st {
  font-family: var(--mono);
  font-size: 9px;
  padding: 2px 9px;
  border-radius: 99px;
  flex: none;
}

.st.ok {
  background: var(--green-weak);
  color: var(--green);
}

.st.bad {
  background: var(--rose-weak);
  color: var(--rose);
}

.scope {
  font-size: 9px;
  padding: 2px 7px;
  border-radius: 99px;
  background: #f2f3f5;
  color: var(--aux);
  flex: none;
}

.scope.user {
  background: var(--purple-weak);
  color: var(--purple);
}

.cm-empty {
  padding: 40px 0;
  text-align: center;
  color: var(--aux);
  font-size: 12.5px;
}

.cap-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px;
  border-top: 0.5px solid var(--hairline);
  background: #fafbfd;
}

.sum {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--sub);
}

.cp-done {
  margin-left: auto;
  padding: 8px 26px;
  border-radius: 11px;
  background: var(--brand);
  color: #fff;
  font-size: 12.5px;
  font-weight: 600;
  box-shadow: var(--shadow-btn);
}

.cp-done:hover {
  background: var(--brand-deep);
}
</style>
