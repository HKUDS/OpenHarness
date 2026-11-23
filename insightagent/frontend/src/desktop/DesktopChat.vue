<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatSession } from '../chat/useChatSession'
import { renderMd } from '../chat/renderMd'
import AppIcon from '../components/AppIcon.vue'
import CapabilityCenter from './CapabilityCenter.vue'

const router = useRouter()

const {
  messages,
  input,
  sending,
  loading,
  files,
  uploading,
  scroller,
  fileInput,
  artifacts,
  selected,
  profileLabel,
  readyProfiles,
  toggle,
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
  fmtUsage,
} = useChatSession()

const modelOpen = ref(false)
const capOpen = ref('')
const drawerOpen = ref(false)
const thinkState = reactive({})
const newOutput = ref(false)

const hints = ['帮我总结这次会话的关键结论', '查看当前目录并给出项目结构', '把分析结果导出为 Markdown 文件']
const lastIndex = computed(() => messages.value.length - 1)
const artifactsCount = computed(() => (artifacts.value.outputs?.length || 0) + (artifacts.value.uploads?.length || 0))
const sysReadyProfiles = computed(() => readyProfiles.value.filter((p) => p.scope === 'system'))
const myReadyProfiles = computed(() => readyProfiles.value.filter((p) => p.scope !== 'system'))

watch(
  () => artifacts.value.outputs?.length,
  (n, o) => {
    if (n > (o || 0) && !drawerOpen.value) newOutput.value = true
  }
)

function isLive(i) {
  return sending.value && i === lastIndex.value
}

function thinkOpen(i) {
  if (thinkState[i] != null) return thinkState[i]
  return isLive(i)
}

function toggleThink(i) {
  thinkState[i] = !thinkOpen(i)
}

function thinkPreview(text) {
  return String(text || '').replace(/\s+/g, ' ').slice(0, 80)
}

function pickHint(h) {
  input.value = h
}

function pickModel(name) {
  selected.profile = name
  modelOpen.value = false
}

async function openDrawer() {
  drawerOpen.value = true
  newOutput.value = false
  await loadArtifacts()
}

function submit() {
  if (sending.value) return stop()
  modelOpen.value = false
  send()
}
</script>

<template>
  <div class="desk-console">
    <div class="console-main">
      <div ref="scroller" class="chat">
        <div class="chat-inner">
          <div v-if="loading" class="boot">正在载入会话…</div>

          <div v-else-if="!messages.length" class="empty">
            <span class="drop"><AppIcon name="sparkles" :size="26" :stroke="1.7" /></span>
            <div class="glyph">洞见</div>
            <p class="lead">把资料、问题或一整段思路交给它，让模型自己决定要调用什么能力。</p>
            <div class="hint-row">
              <button v-for="h in hints" :key="h" class="hint" @click="pickHint(h)">{{ h }}</button>
            </div>
          </div>

          <template v-for="(m, i) in messages" :key="i">
            <div v-if="m.role === 'user'" class="msg-user">
              <span class="who">YOU</span>
              <div class="bubble">{{ m.text }}</div>
            </div>

            <div v-else class="turn">
              <div v-if="m.thinking" class="think" :class="{ live: isLive(i), open: thinkOpen(i) }">
                <div class="think-head" @click="toggleThink(i)">
                  <span v-if="isLive(i)" class="pulse" />
                  <span class="lab">THINKING</span>
                  <span class="pre">{{ thinkPreview(m.thinking) }}</span>
                  <span class="chev">⌄</span>
                </div>
                <div v-show="thinkOpen(i)" class="think-body">{{ m.thinking }}</div>
              </div>

              <div v-if="m.tools && m.tools.length" class="tools">
                <span v-for="(t, k) in m.tools" :key="k" class="tool" :class="{ err: t.error }">
                  {{ t.name }}<i>{{ t.done ? (t.error ? '失败' : '完成') : '运行中' }}</i>
                </span>
              </div>

              <div class="msg-assistant">
                <span class="avatar">
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none">
                    <path
                      d="M3 13c3.2 0 3.2-2.2 6.4-2.2S12.6 13 15.8 13 19 10.8 21 10.8"
                      stroke="#2879ff"
                      stroke-width="1.6"
                      stroke-linecap="round"
                    />
                    <path
                      d="M3 17c3.2 0 3.2-2.2 6.4-2.2S12.6 17 15.8 17 19 14.8 21 14.8"
                      stroke="#8ab4ff"
                      stroke-width="1.6"
                      stroke-linecap="round"
                    />
                  </svg>
                </span>
                <div class="answer">
                  <div class="md" v-html="renderMd(m.text)" />
                  <span v-if="isLive(i)" class="caret" />
                  <div v-if="m.error" class="error-card">{{ m.error }}</div>
                  <div v-if="m.usage" class="usage">{{ fmtUsage(m.usage) }}</div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>

      <div class="composer">
        <div class="composer-inner">
          <textarea
            v-model="input"
            rows="1"
            placeholder="描述任务，或直接提问…（Enter 发送，Shift+Enter 换行）"
            @keydown="onKeydown"
          />

          <div v-if="files.length || uploading" class="attachments">
            <span v-for="f in files" :key="f.name" class="attach">
              <AppIcon name="file" :size="13" />
              <span class="an">{{ f.name }}</span>
              <span class="as">{{ sizeText(f.size || 0) }}</span>
              <button class="ax" @click="removeFile(f.name)">×</button>
            </span>
            <span v-if="uploading" class="attach"><span class="spin" /> 上传中…</span>
          </div>

          <div class="composer-foot">
            <div class="model-pick">
              <div v-if="modelOpen" class="mp-mask" @click="modelOpen = false" />
              <button class="model-sel" :class="{ open: modelOpen }" @click="modelOpen = !modelOpen">
                <span class="dot" />
                <span class="mn">{{ profileLabel }}</span>
                <span class="chev">⌄</span>
              </button>
              <div v-if="modelOpen" class="model-pop">
                <div class="mp-head">选择模型</div>
                <template v-if="sysReadyProfiles.length">
                  <div class="mp-group">系统内置</div>
                  <button
                    v-for="p in sysReadyProfiles"
                    :key="p.name"
                    class="mp-row"
                    :class="{ on: selected.profile === p.name }"
                    @click="pickModel(p.name)"
                  >
                    <span class="mp-name">{{ p.label || p.name }}</span>
                    <span class="mp-ck">✓</span>
                  </button>
                </template>
                <template v-if="myReadyProfiles.length">
                  <div class="mp-group">我的模型</div>
                  <button
                    v-for="p in myReadyProfiles"
                    :key="p.name"
                    class="mp-row"
                    :class="{ on: selected.profile === p.name }"
                    @click="pickModel(p.name)"
                  >
                    <span class="mp-name">{{ p.label || p.name }}</span>
                    <span class="mp-ck">✓</span>
                  </button>
                </template>
                <div v-if="!readyProfiles.length" class="mp-empty">
                  暂无可用模型，去「我的 → 系统内置模型 / 我的模型」添加 API Key
                </div>
              </div>
            </div>

            <button class="foot-btn" :class="{ has: selected.plugins.length }" @click="capOpen = 'plugins'">
              插件<b v-if="selected.plugins.length">{{ selected.plugins.length }}</b>
            </button>
            <button class="foot-btn" :class="{ has: selected.skills.length }" @click="capOpen = 'skills'">
              技能<b v-if="selected.skills.length">{{ selected.skills.length }}</b>
            </button>
            <button class="foot-btn" :class="{ has: selected.mcp.length }" @click="capOpen = 'mcp'">
              MCP<b v-if="selected.mcp.length">{{ selected.mcp.length }}</b>
            </button>
            <button class="foot-btn" :class="{ has: drawerOpen }" @click="openDrawer">
              产出<b v-if="artifactsCount">{{ artifactsCount }}</b>
              <span v-if="newOutput" class="new-dot" />
            </button>

            <button class="icon-foot" title="添加附件" @click="pickFiles"><AppIcon name="paperclip" :size="16" /></button>
            <button v-if="!sending" class="send" :disabled="!input.trim()" @click="submit">
              <AppIcon name="send" :size="16" :stroke="1.9" />
            </button>
            <button v-else class="send stop" title="停止生成" @click="submit"><span class="stop-sq" /></button>
          </div>

          <input ref="fileInput" type="file" multiple hidden @change="onFilesPicked" />
        </div>
      </div>
    </div>

    <aside class="drawer" :class="{ show: drawerOpen }">
      <header class="dw-head">
        <span class="dw-title">产出文件</span>
        <button class="dw-close" @click="drawerOpen = false">×</button>
      </header>
      <div class="dw-body">
        <div class="dw-group">OUTPUTS · {{ artifacts.outputs?.length || 0 }}</div>
        <div v-if="!artifacts.outputs?.length" class="dw-empty">本轮还没有生成文件</div>
        <div v-for="f in artifacts.outputs" :key="f.name" class="file-item">
          <span class="fname">{{ f.name }}</span>
          <span class="fsize">{{ sizeText(f.size || 0) }}</span>
          <a class="flink" :href="previewLink('outputs', f.name)" target="_blank" rel="noopener">预览</a>
          <a class="flink" :href="downloadLink('outputs', f.name)">下载</a>
        </div>

        <div class="dw-group">UPLOADS · {{ artifacts.uploads?.length || 0 }}</div>
        <div v-if="!artifacts.uploads?.length" class="dw-empty">还没有上传附件</div>
        <div v-for="f in artifacts.uploads" :key="f.name" class="file-item">
          <span class="fname">{{ f.name }}</span>
          <span class="fsize">{{ sizeText(f.size || 0) }}</span>
          <a class="flink" :href="previewLink('uploads', f.name)" target="_blank" rel="noopener">预览</a>
        </div>
      </div>
    </aside>

    <CapabilityCenter v-if="capOpen" :tab="capOpen" @close="capOpen = ''" @update:tab="capOpen = $event" />
  </div>
</template>

<style scoped>
.desk-console {
  flex: 1;
  min-width: 0;
  height: 100vh;
  display: flex;
  background: var(--bg);
}

.console-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* ── 消息区 ── */
.chat {
  flex: 1;
  overflow-y: auto;
  padding: 38px 0 10px;
}

.chat-inner {
  max-width: 800px;
  margin: 0 auto;
  padding: 0 40px;
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.boot {
  color: var(--aux);
  font-size: 12.5px;
  text-align: center;
  padding: 60px 0;
}

.msg-user {
  align-self: flex-end;
  max-width: 72%;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.who {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 2px;
  color: var(--aux);
}

.bubble {
  background: var(--brand);
  color: #fff;
  padding: 11px 15px;
  border-radius: 14px 14px 4px 14px;
  font-size: 13.5px;
  line-height: 1.72;
  white-space: pre-wrap;
  word-break: break-word;
  box-shadow: 0 6px 18px rgba(40, 121, 255, 0.18);
}

.turn {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.think {
  background: #fbfcfe;
  border: 0.5px solid #e7edf6;
  border-radius: 12px;
  overflow: hidden;
}

.think-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  cursor: pointer;
  user-select: none;
}

.lab {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 1.5px;
  color: #8a94a6;
  flex: none;
}

.pre {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: var(--aux);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chev {
  color: var(--aux);
  font-size: 11px;
  transition: transform 0.18s;
}

.think.open .chev {
  transform: rotate(180deg);
}

.think-body {
  padding: 10px 12px 12px;
  font-size: 11.5px;
  line-height: 1.75;
  color: var(--sub);
  white-space: pre-wrap;
  border-top: 0.5px solid #eef2f7;
}

.pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand);
  flex: none;
  animation: pulse-dot 1.2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.35;
    transform: scale(0.72);
  }
}

.tools {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tool {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--mono);
  font-size: 9.5px;
  padding: 3px 10px;
  border-radius: 99px;
  background: #f2f5f9;
  color: #5b6577;
}

.tool i {
  font-style: normal;
  color: var(--green);
}

.tool.err {
  background: var(--rose-weak);
}

.tool.err i {
  color: var(--rose);
}

.msg-assistant {
  display: flex;
  gap: 12px;
}

.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(150deg, #eef4ff, #dbe7ff);
  display: grid;
  place-items: center;
  flex: none;
  margin-top: 2px;
}

.answer {
  flex: 1;
  min-width: 0;
}

.md {
  font-size: 13.5px;
  line-height: 1.82;
  color: var(--body);
  word-break: break-word;
}

.md :deep(p) {
  margin: 0 0 10px;
}

.md :deep(p:last-child) {
  margin-bottom: 0;
}

.md :deep(h1),
.md :deep(h2),
.md :deep(h3) {
  font-family: var(--serif);
  color: var(--text);
  margin: 18px 0 8px;
  line-height: 1.4;
}

.md :deep(h1) {
  font-size: 18px;
}
.md :deep(h2) {
  font-size: 16px;
}
.md :deep(h3) {
  font-size: 14.5px;
}

.md :deep(ul),
.md :deep(ol) {
  margin: 0 0 10px;
  padding-left: 20px;
}

.md :deep(li) {
  margin: 3px 0;
}

.md :deep(code) {
  font-family: var(--mono);
  font-size: 12px;
  background: #f2f5f9;
  padding: 1px 5px;
  border-radius: 5px;
  color: #38507a;
}

.md :deep(pre) {
  background: #f7f9fc;
  border: 0.5px solid #e7edf6;
  border-radius: 10px;
  padding: 12px 14px;
  overflow-x: auto;
  margin: 0 0 12px;
}

.md :deep(pre code) {
  background: none;
  padding: 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: #37475e;
}

.md :deep(blockquote) {
  margin: 0 0 10px;
  padding: 4px 0 4px 12px;
  border-left: 2px solid #d7e3f7;
  color: var(--sub);
}

.md :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 12px;
  font-size: 12px;
}

.md :deep(th),
.md :deep(td) {
  border: 0.5px solid #e7edf6;
  padding: 6px 10px;
  text-align: left;
}

.md :deep(th) {
  background: #fafbfd;
  font-weight: 600;
}

.md :deep(a) {
  color: var(--brand);
  text-decoration: none;
}

.md :deep(hr) {
  border: none;
  border-top: 0.5px solid var(--hairline);
  margin: 14px 0;
}

.caret {
  display: inline-block;
  width: 6px;
  height: 13px;
  border-radius: 2px;
  background: var(--brand);
  vertical-align: -2px;
  margin-left: 2px;
  animation: blink 1s steps(1) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.error-card {
  margin-top: 10px;
  background: var(--rose-weak);
  border-left: 2px solid var(--rose);
  color: #b34a48;
  font-size: 11.5px;
  line-height: 1.7;
  padding: 8px 12px;
  border-radius: 0 8px 8px 0;
  white-space: pre-wrap;
}

.usage {
  margin-top: 10px;
  font-family: var(--mono);
  font-size: 9.5px;
  color: #b3bac6;
}

/* ── 空状态 ── */
.empty {
  padding: 62px 0 30px;
  text-align: center;
}

.drop {
  width: 52px;
  height: 52px;
  margin: 0 auto 20px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  background: var(--surface);
  color: var(--brand);
  box-shadow: var(--shadow-card);
}

.glyph {
  font-family: var(--serif);
  font-size: 30px;
  font-weight: 700;
  letter-spacing: 10px;
  color: var(--text);
  text-indent: 10px;
}

.lead {
  font-size: 14px;
  color: var(--aux);
  max-width: 440px;
  margin: 12px auto 22px;
  line-height: 1.8;
}

.hint-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.hint {
  padding: 8px 16px;
  border-radius: 99px;
  background: var(--surface);
  border: 0.5px solid var(--hairline);
  color: var(--sub);
  font-size: 13px;
  transition: 0.15s;
}

.hint:hover {
  border-color: #cfe0ff;
  color: var(--brand);
  background: #fbfdff;
}

/* ── 输入区 ── */
.composer {
  padding: 12px 24px 24px;
  background: linear-gradient(to bottom, transparent, var(--bg) 26%);
}

.composer-inner {
  max-width: none;
  margin: 0 auto;
  background: var(--surface);
  border: 0.5px solid var(--hairline);
  border-radius: 18px;
  box-shadow: var(--shadow-card);
  padding: 12px 14px 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.composer-inner:focus-within {
  border-color: #cfe0ff;
  box-shadow: 0 8px 26px rgba(40, 121, 255, 0.1);
}

.composer-inner textarea {
  width: 100%;
  border: none;
  background: transparent;
  resize: none;
  min-height: 52px;
  padding: 4px 4px 6px;
  max-height: 200px;
  font-size: 14px;
  line-height: 1.72;
  border-radius: 0;
}

.attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 2px 2px 6px;
}

.attach {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 8px;
  background: #f4f7fc;
  color: var(--sub);
  font-size: 10.5px;
  max-width: 240px;
}

.attach .an {
  font-family: var(--mono);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attach .as {
  color: var(--aux);
  flex: none;
}

.attach .ax {
  color: var(--aux);
  font-size: 12px;
  line-height: 1;
  flex: none;
}

.attach .ax:hover {
  color: var(--rose);
}

.composer-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 6px;
}

.model-pick {
  position: relative;
}

.mp-mask {
  position: fixed;
  inset: 0;
  z-index: 29;
}

.model-sel {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  background: var(--brand-weak);
  color: var(--brand);
  font-size: 11px;
  font-weight: 600;
  max-width: 210px;
}

.model-sel .dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--green);
  flex: none;
}

.model-sel .mn {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-sel.open .chev {
  transform: rotate(180deg);
}

.model-pop {
  position: absolute;
  bottom: 36px;
  left: 0;
  width: 246px;
  background: var(--surface);
  border-radius: 13px;
  box-shadow: 0 16px 44px rgba(20, 30, 50, 0.18);
  border: 0.5px solid var(--hairline);
  padding: 6px;
  z-index: 30;
  max-height: 300px;
  overflow-y: auto;
}

.mp-head {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 1.4px;
  color: var(--aux);
  padding: 6px 8px;
}

.mp-group {
  font-size: 10px;
  font-weight: 600;
  color: var(--aux);
  padding: 8px 10px 4px;
  letter-spacing: 0.5px;
}

.mp-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 9px;
  border-radius: 8px;
  font-size: 12.5px;
  color: var(--body);
  text-align: left;
}

.mp-row:hover {
  background: #fafbfd;
}

.mp-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mp-ck {
  color: var(--brand);
  font-size: 11px;
  opacity: 0;
}

.mp-row.on .mp-ck {
  opacity: 1;
}

.mp-row.on {
  background: var(--brand-weak);
  color: var(--brand);
  font-weight: 600;
}

.mp-empty {
  padding: 14px 10px;
  font-size: 11.5px;
  color: var(--aux);
  line-height: 1.7;
}

.foot-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  color: var(--sub);
  font-size: 11px;
  background: transparent;
  transition: 0.13s;
}

.foot-btn:hover {
  background: #f4f6f9;
  color: var(--text);
}

.foot-btn.has {
  color: var(--brand);
  background: var(--brand-weak);
}

.foot-btn b {
  font-family: var(--mono);
  font-size: 9.5px;
  font-weight: 700;
  min-width: 15px;
  height: 15px;
  border-radius: 99px;
  background: rgba(40, 121, 255, 0.14);
  display: inline-grid;
  place-items: center;
  padding: 0 4px;
}

.new-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--rose);
  margin-left: 1px;
}

.icon-foot {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  color: var(--sub);
  margin-left: auto;
}

.icon-foot:hover {
  background: #f4f6f9;
  color: var(--brand);
}

.send {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--brand);
  color: #fff;
  display: grid;
  place-items: center;
  box-shadow: var(--shadow-btn);
  flex: none;
  transition: transform 0.12s, background 0.12s;
}

.send:hover {
  background: var(--brand-deep);
}

.send:active {
  transform: scale(0.94);
}

.send[disabled] {
  opacity: 0.4;
  box-shadow: none;
  pointer-events: none;
}

.send.stop {
  background: #fff;
  border: 1px solid #e2e7ef;
  box-shadow: none;
}

.stop-sq {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: var(--text);
}

.spin {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 1.5px solid #c9d8f5;
  border-top-color: var(--brand);
  animation: spin 0.7s linear infinite;
  display: inline-block;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* ── 产出抽屉 ── */
.drawer {
  width: 0;
  overflow: hidden;
  background: var(--surface);
  border-left: 0.5px solid transparent;
  display: flex;
  flex-direction: column;
  transition: width 0.24s cubic-bezier(0.32, 0.72, 0.33, 1);
}

.drawer.show {
  width: 320px;
  border-left-color: var(--hairline);
}

.dw-head {
  display: flex;
  align-items: center;
  height: 54px;
  padding: 0 16px;
  border-bottom: 0.5px solid var(--hairline);
  flex: none;
  min-width: 320px;
}

.dw-title {
  flex: 1;
  font-family: var(--serif);
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text);
}

.dw-close {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  color: var(--sub);
  font-size: 15px;
}

.dw-close:hover {
  background: var(--bg);
}

.dw-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 14px 24px;
  min-width: 320px;
}

.dw-group {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 1.4px;
  color: var(--aux);
  margin: 10px 2px 9px;
}

.dw-empty {
  font-size: 13px;
  color: var(--aux);
  padding: 5px 2px 16px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 9px;
  background: #fafbfd;
  margin-bottom: 6px;
  font-size: 11px;
}

.fname {
  flex: 1;
  min-width: 0;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fsize {
  color: var(--aux);
  font-size: 9.5px;
  flex: none;
}

.flink {
  color: var(--brand);
  font-size: 10.5px;
  flex: none;
}
</style>
