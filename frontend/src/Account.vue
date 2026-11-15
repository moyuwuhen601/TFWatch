<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Bell, KeyRound, LogOut, Mail, Plus, Send, Settings2, Trash2 } from 'lucide-vue-next'
import { api, refreshSession, session } from './api'

const router = useRouter()
const kinds = { email: '电子邮件', telegram: 'Telegram', ntfy: 'ntfy', webhook: 'Webhook' }
const channels = ref([])
const editing = ref(null)
const replaceConfig = ref(false)
const busy = ref(false)
const message = ref('')
const error = ref('')
const currentPassword = ref('')
const newPassword = ref('')
const notifyMode = ref('open')
const user = computed(() => session.user)

watch(() => user.value?.id, async id => {
  editing.value = null
  channels.value = []
  if (id) {
    notifyMode.value = user.value.notify_mode
    try {
      const values = await api('/channels')
      if (id === user.value?.id) channels.value = values
    } catch (err) {
      error.value = err.message
    }
  }
}, { immediate: true })

function start(channel = null) {
  editing.value = { id: channel?.id, kind: channel?.kind || 'webhook',
    label: channel?.label || '', enabled: channel?.enabled ?? true,
    url: '', token: '', bot_token: '', chat_id: '', topic: '' }
  replaceConfig.value = !channel
  message.value = ''
  error.value = ''
}

async function action(run, success = '') {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await run()
    message.value = success
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

function saveChannel() {
  const item = editing.value
  const body = { label: item.label, enabled: item.enabled }
  const fields = { email: [], telegram: ['bot_token', 'chat_id'], ntfy: ['url', 'topic', 'token'], webhook: ['url', 'token'] }
  if (replaceConfig.value || !item.id) body.config = Object.fromEntries(fields[item.kind].map(key => [key, item[key].trim()]))
  if (!item.id) body.kind = item.kind
  return action(async () => {
    const saved = await api('/channels' + (item.id ? '/' + item.id : ''), { method: item.id ? 'PATCH' : 'POST', body })
    channels.value = [...channels.value.filter(channel => channel.id !== saved.id), saved].sort((a, b) => a.id - b.id)
    editing.value = null
  }, '通知渠道已保存。')
}

function removeChannel(channel) {
  if (!window.confirm('删除通知渠道「' + channel.label + '」？')) return
  return action(async () => {
    await api('/channels/' + channel.id, { method: 'DELETE' })
    channels.value = channels.value.filter(item => item.id !== channel.id)
    if (editing.value?.id === channel.id) editing.value = null
  }, '通知渠道已删除。')
}
</script>

<template>
  <section v-if="!user" class="panel state-panel"><h1>账号设置</h1><p>登录后管理账号与通知渠道。</p><RouterLink to="/login" class="btn btn-dark">登录</RouterLink></section>
  <div v-else class="settings-layout">
    <div class="section-heading page-heading"><div><div class="section-icon"><Settings2 :size="20" /></div><div><h1>账号设置</h1><p>{{ user.email }}</p></div></div>
      <button class="btn btn-secondary btn-small" :disabled="busy" @click="action(async () => { await api('/auth/logout', { method: 'POST' }); await refreshSession(); await router.push('/') })"><LogOut :size="16" /> 退出登录</button>
    </div>
    <p v-if="message" class="feedback success" role="status">{{ message }}</p>
    <p v-if="error" class="feedback error" role="alert">{{ error }}</p>
    <section class="panel settings-panel">
      <div class="section-heading compact"><div><div class="section-icon"><Bell :size="19" /></div><div><h2>通知渠道</h2><p>选择接收测试资格提醒的方式。</p></div></div>
        <button class="btn btn-dark btn-small" :disabled="busy" @click="start()"><Plus :size="17" /> 添加渠道</button>
      </div>
      <p v-if="!channels.length && !editing" class="muted">暂无通知渠道。</p>
      <ul v-if="channels.length" class="setting-list">
        <li v-for="channel in channels" :key="channel.id">
          <div><strong>{{ channel.label }}</strong><p>{{ kinds[channel.kind] }} · {{ channel.enabled ? '已启用' : '已停用' }}</p></div>
          <div class="row-actions">
            <button type="button" class="btn btn-secondary btn-small" :disabled="busy" @click="action(() => api('/channels/' + channel.id + '/test', { method: 'POST' }), '测试通知已发送。')"><Send :size="15" /> 测试</button>
            <button type="button" class="btn btn-secondary btn-small" :disabled="busy" @click="start(channel)">编辑</button>
            <button type="button" class="icon-button danger" aria-label="删除渠道" :disabled="busy" @click="removeChannel(channel)"><Trash2 :size="17" /></button>
          </div>
        </li>
      </ul>
      <form v-if="editing" class="form-stack nested-form" @submit.prevent="saveChannel">
        <h3>{{ editing.id ? '编辑渠道' : '添加渠道' }}</h3>
        <label v-if="!editing.id">渠道类型<select v-model="editing.kind"><option v-for="[key,label] in Object.entries(kinds)" :key="key" :value="key">{{ label }}</option></select></label>
        <label>渠道名称<input v-model="editing.label" required maxlength="60" placeholder="例如：个人提醒"></label>
        <label class="check"><input v-model="editing.enabled" type="checkbox"> 启用渠道</label>
        <p v-if="editing.kind === 'email'" class="muted">{{ user.verified ? '发送到 ' + user.email : '请先在「邮箱验证」完成验证。' }}</p>
        <label v-if="editing.id && editing.kind !== 'email'" class="check"><input v-model="replaceConfig" type="checkbox"> 更新渠道地址或凭据</label>
        <template v-if="replaceConfig">
          <div v-if="editing.kind === 'telegram'" class="form-columns">
            <label>Bot Token<input v-model="editing.bot_token" type="password" autocomplete="off" required></label>
            <label>Chat ID<input v-model="editing.chat_id" maxlength="32" required></label>
          </div>
          <template v-if="['ntfy', 'webhook'].includes(editing.kind)">
            <label>{{ editing.kind === 'ntfy' ? 'ntfy 服务地址' : 'Webhook 地址' }}<input v-model="editing.url" type="url" maxlength="1500" placeholder="https://…" required></label>
            <label v-if="editing.kind === 'ntfy'">主题<input v-model="editing.topic" maxlength="64" required></label>
            <label>Bearer Token <span class="muted normal">（选填）</span><input v-model="editing.token" type="password" autocomplete="off" maxlength="512"></label>
          </template>
        </template>
        <div class="form-actions">
          <button type="button" class="btn btn-secondary" :disabled="busy" @click="editing = null">取消</button>
          <button class="btn btn-dark" :disabled="busy || (editing.kind === 'email' && !user.verified)">保存渠道</button>
        </div>
      </form>
    </section>
    <section class="panel settings-panel">
      <div class="section-heading compact"><div><div class="section-icon"><Settings2 :size="19" /></div><div><h2>通知触发条件</h2><p>适用于你的全部关注。</p></div></div></div>
      <form class="form-stack" @submit.prevent="action(async () => { session.user = await api('/account', { method: 'PATCH', body: { notify_mode: notifyMode } }) }, '通知偏好已保存。')">
        <label class="check"><input v-model="notifyMode" type="radio" value="open"> 仅在检测到开放时提醒</label>
        <label class="check"><input v-model="notifyMode" type="radio" value="changes"> 在开放、满员或关闭状态变化时提醒</label>
        <div><button class="btn btn-secondary btn-small" :disabled="busy || notifyMode === user.notify_mode">保存偏好</button></div>
      </form>
    </section>
    <section class="panel settings-panel">
      <div class="section-heading compact"><div><div class="section-icon"><Mail :size="19" /></div><div><h2>邮箱验证</h2><p>{{ user.verified ? '邮箱已验证' : session.mail_available ? '验证后可使用邮件通知和密码重置。' : '此站点尚未配置邮件服务。' }}</p></div></div>
        <button v-if="!user.verified && session.mail_available" class="btn btn-secondary btn-small" :disabled="busy" @click="action(() => api('/auth/verify-request', { method: 'POST' }), '验证邮件已发送。')">发送验证邮件</button>
      </div>
    </section>
    <section class="panel settings-panel">
      <div class="section-heading compact"><div><div class="section-icon"><KeyRound :size="19" /></div><div><h2>修改密码</h2></div></div></div>
      <form class="form-stack" @submit.prevent="action(async () => {
        await api('/account/password', { method: 'POST', body: { current_password: currentPassword, password: newPassword } })
        currentPassword = ''; newPassword = ''
      }, '密码已更新。')">
        <div class="form-columns">
          <label>当前密码<input v-model="currentPassword" type="password" autocomplete="current-password" required maxlength="128"></label>
          <label>新密码<input v-model="newPassword" type="password" autocomplete="new-password" required minlength="10" maxlength="128"></label>
        </div>
        <div><button class="btn btn-secondary btn-small" :disabled="busy">更新密码</button></div>
      </form>
    </section>
  </div>
</template>
