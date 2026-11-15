<script setup>
import { ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, LibraryBig, Save, Search, Settings2, ShieldCheck, Trash2, Users } from 'lucide-vue-next'
import { api, refreshSession, session } from './api'

const tab = ref('settings')
const settings = ref(null)
const accounts = ref([])
const apps = ref([])
const editing = ref(null)
const query = ref('')
const search = ref('')
const page = ref(1)
const hasMore = ref(false)
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const message = ref('')
const version = ref(0)
const tabs = { settings: '站点设置', users: '用户管理', apps: '软件管理' }

function switchTab(value) {
  tab.value = value
  query.value = ''
  search.value = ''
  page.value = 1
  message.value = ''
}

watch([tab, page, query, version, () => session.user?.is_admin], async (_, __, onCleanup) => {
  if (!session.user?.is_admin) return
  const abort = new AbortController()
  onCleanup(() => abort.abort())
  const current = tab.value
  editing.value = null
  loading.value = true
  error.value = ''
  try {
    if (current === 'settings') {
      settings.value = await api('/admin/settings', { signal: abort.signal })
    } else {
      const path = current === 'users' ? '/admin/users' : '/apps'
      const result = await api(path + '?' + new URLSearchParams({ q: query.value, page: page.value }), { signal: abort.signal })
      if (current === 'users') accounts.value = result.items
      else apps.value = result.items
      hasMore.value = result.has_more
    }
  } catch (err) {
    if (!abort.signal.aborted) error.value = err.message
  } finally {
    if (!abort.signal.aborted) loading.value = false
  }
}, { immediate: true })

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

function remove(path, name) {
  if (!window.confirm('删除「' + name + '」及其相关历史和关注记录？')) return
  return action(async () => {
    await api('/admin' + path, { method: 'DELETE' })
    version.value++
  }, '已删除。')
}
</script>

<template>
  <div v-if="!session.user?.is_admin" class="panel state-panel">
    <h1>管理后台</h1><p>需要管理员权限。</p><RouterLink v-if="!session.user" to="/login" class="btn btn-dark">登录</RouterLink>
  </div>
  <div v-else class="settings-layout">
    <div class="section-heading page-heading"><div><div class="section-icon"><ShieldCheck :size="20" /></div><div><h1>管理后台</h1><p>管理站点权限、账号和公共软件库。</p></div></div></div>
    <div class="filters" aria-label="管理类别"><button v-for="[key,label] in Object.entries(tabs)" :key="key" type="button" :aria-pressed="key === tab" :disabled="busy" @click="switchTab(key)">{{ label }}</button></div>
    <p v-if="loading" class="panel state-panel" role="status">正在加载…</p>
    <p v-if="error" class="feedback error" role="alert">{{ error }}</p>
    <p v-if="message" class="feedback success" role="status">{{ message }}</p>
    <section v-if="!loading && tab === 'settings' && settings" class="panel settings-panel">
      <div class="section-heading compact"><div><div class="section-icon"><Settings2 :size="19" /></div><div><h2>站点设置</h2></div></div></div>
      <form class="form-stack" @submit.prevent="action(async () => { settings = await api('/admin/settings', { method: 'PUT', body: settings }); await refreshSession() }, '站点设置已保存。')">
        <label class="check"><input v-model="settings.registration" type="checkbox"> 允许新用户注册</label>
        <label class="check"><input v-model="settings.anonymous" type="checkbox"> 允许访客浏览软件库和时间线</label>
        <label>检测间隔（秒）<input v-model.number="settings.interval" type="number" required min="60" max="3600"></label>
        <div><button class="btn btn-dark" :disabled="busy"><Save :size="17" /> 保存设置</button></div>
      </form>
    </section>
    <section v-if="tab !== 'settings'" class="panel settings-panel">
      <div class="section-heading compact"><div><div class="section-icon"><component :is="tab === 'users' ? Users : LibraryBig" :size="19" /></div><div><h2>{{ tabs[tab] }}</h2></div></div></div>
      <form class="search-form" role="search" @submit.prevent="query = search.trim(); page = 1">
        <div class="field-icon"><Search :size="17" /><input v-model="search" type="search" :aria-label="tab === 'users' ? '搜索邮箱' : '搜索软件'" :placeholder="tab === 'users' ? '搜索邮箱' : '搜索软件名称或邀请码'" maxlength="120"></div>
        <button class="btn btn-secondary">搜索</button>
      </form>
      <template v-if="!loading && tab === 'users'">
        <p v-if="!accounts.length" class="muted">未找到账号。</p>
        <ul v-else class="setting-list">
          <li v-for="user in accounts" :key="user.id">
            <div><strong>{{ user.email }}</strong><p>{{ user.is_admin ? '管理员' : '普通用户' }} · {{ user.active ? '正常' : '已停用' }} · {{ user.verified ? '邮箱已验证' : '邮箱待验证' }}</p></div>
            <button v-if="!user.is_admin" class="btn btn-secondary btn-small" :disabled="busy" @click="action(async () => { Object.assign(user, await api('/admin/users/' + user.id, { method: 'PATCH', body: { active: !user.active } })) }, '账号状态已更新。')">{{ user.active ? '停用' : '启用' }}</button>
          </li>
        </ul>
      </template>
      <template v-if="!loading && tab === 'apps'">
        <p v-if="!apps.length" class="muted">未找到软件。</p>
        <ul v-else class="setting-list">
          <li v-for="app in apps" :key="app.id" class="admin-app">
            <div><RouterLink :to="'/apps/' + app.id"><strong>{{ app.name }}</strong></RouterLink><p>{{ app.invites.length }} 个公开邀请</p></div>
            <div class="row-actions">
              <button type="button" class="btn btn-secondary btn-small" :disabled="busy" @click="action(async () => { editing = await api('/admin/apps/' + app.id) })">编辑</button>
              <button type="button" class="icon-button danger" aria-label="删除软件" :disabled="busy" @click="remove('/apps/' + app.id, app.name)"><Trash2 :size="17" /></button>
            </div>
            <form v-if="editing?.id === app.id" class="form-stack nested-form" @submit.prevent="action(async () => {
              const { id, name, aliases, description } = editing
              Object.assign(app, await api('/admin/apps/' + id, { method: 'PATCH', body: { name, aliases, description } }))
              editing = null
            }, '软件资料已保存。')">
              <label>软件名称<input v-model="editing.name" required maxlength="180"></label>
              <label>搜索别名<input v-model="editing.aliases" maxlength="300"></label>
              <label>介绍<textarea v-model="editing.description" maxlength="4000" rows="3"></textarea></label>
              <div class="invite-chips">
                <button v-for="invite in app.invites" :key="invite.code" type="button" class="btn btn-secondary btn-small" :disabled="busy" @click="remove('/invites/' + invite.code, invite.code)"><Trash2 :size="15" /> {{ invite.code }}</button>
              </div>
              <div class="form-actions"><button type="button" class="btn btn-secondary" @click="editing = null">取消</button><button class="btn btn-dark" :disabled="busy">保存软件资料</button></div>
            </form>
          </li>
        </ul>
      </template>
      <div v-if="page > 1 || hasMore" class="pagination"><button class="btn btn-secondary btn-small" :disabled="page <= 1 || loading" @click="page--"><ChevronLeft :size="16" /> 上一页</button><span>第 {{ page }} 页</span><button class="btn btn-secondary btn-small" :disabled="!hasMore || loading" @click="page++">下一页 <ChevronRight :size="16" /></button></div>
    </section>
  </div>
</template>
