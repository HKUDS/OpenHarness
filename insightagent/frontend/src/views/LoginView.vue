<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { doLogin, doRegister, toast } from '../store'
import AppIcon from '../components/AppIcon.vue'

const router = useRouter()
const mode = ref('login') // login | register
const form = reactive({ username: '', password: '', confirm: '', display_name: '' })
const err = ref('')
const loading = ref(false)

function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  err.value = ''
}

async function submit() {
  err.value = ''
  if (!form.username.trim()) return (err.value = '请输入用户名')
  if (!form.password) return (err.value = '请输入密码')
  if (mode.value === 'register') {
    if (form.password.length < 6) return (err.value = '密码至少 6 位')
    if (form.password !== form.confirm) return (err.value = '两次输入的密码不一致')
  }
  loading.value = true
  try {
    if (mode.value === 'login') {
      const user = await doLogin(form.username.trim(), form.password)
      toast(`欢迎回来，${user.display_name}`)
    } else {
      const user = await doRegister(form.username.trim(), form.password, form.display_name.trim())
      toast(`注册成功，${user.display_name}`)
    }
    router.replace('/sessions')
  } catch (e) {
    err.value = e.message || '操作失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth">
    <div class="auth-card">
      <div class="auth-logo">
        <AppIcon name="sparkles" :size="30" :stroke="1.8" />
      </div>
      <h1 class="auth-title">{{ mode === 'login' ? '登录 InsightAgent' : '创建账号' }}</h1>
      <p class="auth-sub">
        {{ mode === 'login' ? '你的会话、模型与能力配置彼此独立' : '注册后即拥有独立的数据空间' }}
      </p>

      <form @submit.prevent="submit">
        <div class="field">
          <label>用户名</label>
          <div class="field-box">
            <input v-model="form.username" autocomplete="username" placeholder="2-32 位字母/数字/中文" />
          </div>
        </div>

        <div v-if="mode === 'register'" class="field">
          <label>昵称（可选）</label>
          <div class="field-box">
            <input v-model="form.display_name" placeholder="用于展示的名字" />
          </div>
        </div>

        <div class="field">
          <label>密码</label>
          <div class="field-box">
            <input
              v-model="form.password"
              type="password"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              placeholder="至少 6 位"
            />
          </div>
        </div>

        <div v-if="mode === 'register'" class="field">
          <label>确认密码</label>
          <div class="field-box">
            <input v-model="form.confirm" type="password" autocomplete="new-password" placeholder="再次输入密码" />
          </div>
        </div>

        <p v-if="err" class="err">{{ err }}</p>

        <button class="btn btn-primary btn-block" style="margin-top: 18px" :disabled="loading" type="submit">
          <span v-if="loading" class="spin" />
          <template v-else>{{ mode === 'login' ? '登录' : '注册并登录' }}</template>
        </button>
      </form>

      <div class="auth-switch">
        <template v-if="mode === 'login'">
          还没有账号？<b @click="switchMode">立即注册</b>
        </template>
        <template v-else>
          已有账号？<b @click="switchMode">去登录</b>
        </template>
      </div>
    </div>
  </div>
</template>
