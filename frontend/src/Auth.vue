<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, LockKeyhole, Mail } from 'lucide-vue-next'
import { api, refreshSession, session } from './api'

const props = defineProps({ mode: { type: String, required: true } })
const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
const result = ref('')
const token = computed(() => new URLSearchParams(route.hash.slice(1)).get('token') || '')
const needsEmail = computed(() => ['login', 'register', 'forgot-password'].includes(props.mode))
const needsPassword = computed(() => ['login', 'register', 'reset-password'].includes(props.mode))
const titles = {
  login: '登录 TFWatch', register: '注册 TFWatch', 'forgot-password': '找回密码',
  'reset-password': '设置新密码', 'verify-email': '验证邮箱',
}
const unavailable = computed(() => props.mode === 'register' && !session.registration
  ? '此站点已关闭注册。'
  : ['reset-password', 'verify-email'].includes(props.mode) && !token.value && !result.value
    ? '链接无效或不完整。' : '')

watch(() => props.mode, () => {
  password.value = ''
  error.value = ''
  result.value = ''
})

async function submit() {
  busy.value = true
  error.value = ''
  const body = {}
  const mode = props.mode
  if (needsEmail.value) body.email = email.value.trim()
  if (needsPassword.value) body.password = password.value
  if (token.value) body.token = token.value
  try {
    const action = mode === 'forgot-password' ? 'reset-request' : mode
    await api('/auth/' + action, { method: 'POST', body })
    password.value = ''
    if (mode === 'login' || mode === 'register') {
      await refreshSession()
      const target = route.query.next
      const safe = typeof target === 'string' && (/^\/apps\/\d+(?:\?|$)/.test(target) || target === '/following')
      await router.replace(safe ? target : '/')
    } else if (mode === 'forgot-password') {
      result.value = '如果该邮箱已注册并完成验证，稍后会收到密码重置链接。'
    } else {
      await refreshSession()
      result.value = mode === 'verify-email' ? '邮箱已验证。' : '密码已更新，请重新登录。'
      await router.replace({ path: route.path, hash: '' })
    }
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="panel auth-panel">
    <div class="section-icon"><component :is="mode.includes('email') ? Mail : LockKeyhole" :size="22" /></div>
    <h1>{{ titles[mode] }}</h1>
    <p v-if="mode === 'register'">添加公开邀请，关注测试名额并接收提醒。</p>
    <p v-if="mode === 'forgot-password'">重置链接将发送到已验证的邮箱。</p>
    <p v-if="unavailable" class="feedback error" role="alert">{{ unavailable }}</p>
    <template v-else-if="result">
      <p class="feedback success" role="status">{{ result }}</p>
      <RouterLink :to="session.user ? '/account' : '/login'" class="btn btn-dark">继续 <ArrowRight :size="17" /></RouterLink>
    </template>
    <form v-else class="form-stack" @submit.prevent="submit">
      <label v-if="needsEmail">邮箱<input v-model="email" type="email" autocomplete="email" maxlength="254" required placeholder="name@example.com"></label>
      <label v-if="needsPassword">{{ mode === 'reset-password' ? '新密码' : '密码' }}
        <input v-model="password" type="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" :minlength="mode === 'login' ? undefined : 10" maxlength="128" required>
        <span v-if="mode !== 'login'" class="muted normal">至少 10 个字符</span>
      </label>
      <p v-if="error" role="alert" class="feedback error">{{ error }}</p>
      <button class="btn btn-dark" :disabled="busy">{{ busy ? '正在处理…' : mode === 'forgot-password' ? '发送重置链接' : mode === 'reset-password' ? '更新密码' : mode === 'verify-email' ? '确认验证' : mode === 'register' ? '创建账号' : '登录' }} <ArrowRight :size="17" /></button>
    </form>
    <div class="auth-links">
      <RouterLink v-if="mode !== 'login'" to="/login">返回登录</RouterLink>
      <template v-else>
        <RouterLink v-if="session.registration" to="/register">注册账号</RouterLink>
        <RouterLink v-if="session.mail_available" to="/forgot-password">忘记密码？</RouterLink>
      </template>
    </div>
  </div>
</template>
