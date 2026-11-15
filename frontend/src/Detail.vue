<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowUpRight, Bell, BellOff, Link, Plus } from 'lucide-vue-next'
import { api, session } from './api'
import { dateLabel, states } from './format'
import AppIcon from './AppIcon.vue'
import InviteForm from './InviteForm.vue'
import StatusPill from './StatusPill.vue'
import Timeline from './Timeline.vue'

const props = defineProps({ id: { type: String, required: true } })
const route = useRoute()
const router = useRouter()
const app = ref(null)
const error = ref('')
const actionError = ref('')
const loading = ref(true)
const showAdd = ref(false)
const followBusy = ref(false)
const reload = ref(0)
const current = computed(() => app.value?.invites.find(invite => invite.code === route.query.invite) || app.value?.invites[0])

watch([() => props.id, () => session.user?.id, reload], async (_, __, onCleanup) => {
  const abort = new AbortController()
  onCleanup(() => abort.abort())
  loading.value = true
  showAdd.value = false
  app.value = null
  error.value = ''
  try {
    app.value = await api('/apps/' + props.id, { signal: abort.signal })
  } catch (err) {
    if (!abort.signal.aborted) error.value = err.message
  } finally {
    if (!abort.signal.aborted) loading.value = false
  }
}, { immediate: true })

watch(current, () => { actionError.value = '' })

watch([() => current.value?.code, () => current.value?.checked_at], ([code, checkedAt], _, onCleanup) => {
  if (!code || checkedAt != null) return

  const abort = new AbortController()
  const id = props.id
  const started = Date.now()
  let timer
  onCleanup(() => {
    abort.abort()
    clearTimeout(timer)
  })

  async function refresh() {
    try {
      const updated = await api('/apps/' + id, { signal: abort.signal })
      if (abort.signal.aborted || props.id !== id || current.value?.code !== code) return
      const invite = updated.invites.find(item => item.code === code)
      if (!invite) return
      if (invite.checked_at != null) {
        app.value.name = updated.name
        app.value.icon = updated.icon
        current.value.status = invite.status
        current.value.checked_at = invite.checked_at
        return
      }
    } catch (err) {
      if (abort.signal.aborted || [401, 403, 404].includes(err.status)) return
    }
    timer = setTimeout(refresh, Date.now() - started < 30000 ? 1000 : 5000)
  }

  timer = setTimeout(refresh, 1000)
})

async function toggleFollow() {
  if (!session.user) {
    await router.push({ path: '/login', query: { next: route.fullPath } })
    return
  }
  const invite = current.value
  const checkedAt = invite.checked_at
  followBusy.value = true
  actionError.value = ''
  try {
    const result = await api('/invites/' + invite.code + '/follow', { method: invite.followed ? 'DELETE' : 'PUT' })
    invite.followed = !!result
    if (result && invite.checked_at === checkedAt) invite.status = result.status
  } catch (err) {
    actionError.value = err.message
  } finally {
    followBusy.value = false
  }
}

function added() {
  showAdd.value = false
  reload.value++
}
</script>

<template>
  <RouterLink to="/" class="back-link"><ArrowLeft :size="17" /> 返回软件库</RouterLink>
  <div v-if="loading" class="panel state-panel" role="status">正在加载软件…</div>
  <div v-else-if="error" class="panel state-panel" role="alert">
    <h1>{{ error }}</h1><RouterLink v-if="!session.user" to="/login" class="btn btn-dark">登录</RouterLink>
  </div>
  <template v-else-if="app">
    <section class="panel detail-header">
      <div class="detail-title"><AppIcon :icon="app.icon" :name="app.name" /><div><h1>{{ app.name }}</h1><p>{{ app.description || 'TestFlight · ' + app.invites.length + ' 个公开邀请' }}</p></div></div>
      <div v-if="current" class="detail-actions">
        <button type="button" class="btn btn-secondary" :disabled="followBusy" @click="toggleFollow">
          <component :is="current.followed ? BellOff : Bell" :size="17" /> {{ current.followed ? '取消关注' : '关注此邀请' }}
        </button>
        <a :href="current.url" target="_blank" rel="noopener noreferrer" class="btn btn-dark">前往 TestFlight <ArrowUpRight :size="17" /></a>
      </div>
    </section>
    <section class="panel invites-panel">
      <div class="section-heading compact">
        <div><div class="section-icon"><Link :size="19" /></div><div><h2>公开邀请</h2><p v-if="current" aria-live="polite">{{ current.checked_at == null ? '正在等待首次检测' : '最近检测 · ' + dateLabel(current.checked_at) }}</p></div></div>
        <button v-if="session.user" type="button" class="btn btn-secondary btn-small" :aria-expanded="showAdd" @click="showAdd = !showAdd"><Plus :size="17" /> 添加邀请</button>
      </div>
      <InviteForm v-if="showAdd" :app-id="app.id" @cancel="showAdd = false" @submitted="added" />
      <div class="invite-chips">
        <RouterLink v-for="invite in app.invites" :key="invite.code" :to="{ query: { invite: invite.code } }" :class="{ selected: current?.code === invite.code }" :aria-label="invite.code + ' · ' + (invite.checked_at == null ? '待检测' : states[invite.status])" :aria-current="current?.code === invite.code ? 'true' : undefined">
          <code>{{ invite.code }}</code><StatusPill :status="invite.status" :pending="invite.checked_at == null" /><Bell v-if="invite.followed" :size="15" aria-label="已关注" />
        </RouterLink>
      </div>
      <p v-if="actionError" class="feedback error" role="alert">{{ actionError }}</p>
    </section>
    <Timeline v-if="current" :code="current.code" :checked-at="current.checked_at" />
  </template>
</template>

