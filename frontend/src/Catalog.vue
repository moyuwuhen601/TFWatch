<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, ArrowRight, ArrowUpRight, Bell, ChevronLeft, ChevronRight, LibraryBig, Plus, Search, X } from 'lucide-vue-next'
import { api, session } from './api'
import { dateLabel, states } from './format'
import AppIcon from './AppIcon.vue'
import InviteForm from './InviteForm.vue'
import StatusPill from './StatusPill.vue'

const props = defineProps({ following: Boolean })
const route = useRoute()
const router = useRouter()
const search = ref('')
const items = ref([])
const hasMore = ref(false)
const page = computed(() => Math.max(1, Math.min(100000, Number.parseInt(route.query.page, 10) || 1)))
const filter = computed(() => Object.hasOwn(states, route.query.status) ? route.query.status : '')
const loading = ref(false)
const error = ref('')
const showForm = ref(false)
const canBrowse = computed(() => props.following ? !!session.user : !!session.user || session.anonymous)

function apply(changes) {
  const query = { ...route.query, page: undefined, ...changes }
  return router.replace({ query })
}

watch(() => route.query.q, value => { search.value = typeof value === 'string' ? value : '' }, { immediate: true })
watch([() => props.following, () => route.query.q, filter, page, canBrowse, () => session.user?.id], async (_, __, onCleanup) => {
  showForm.value = false
  items.value = []
  error.value = ''
  hasMore.value = false
  if (!canBrowse.value) return
  const abort = new AbortController()
  onCleanup(() => abort.abort())
  loading.value = true
  const params = new URLSearchParams({ page: page.value })
  if (typeof route.query.q === 'string') params.set('q', route.query.q)
  if (filter.value) params.set('status', filter.value)
  if (props.following) params.set('followed', 'true')
  try {
    const data = await api('/apps?' + params, { signal: abort.signal })
    items.value = data.items
    hasMore.value = data.has_more
  } catch (err) {
    if (!abort.signal.aborted) error.value = err.message
  } finally {
    if (!abort.signal.aborted) loading.value = false
  }
}, { immediate: true })

function checkedAt(app) {
  const stamps = app.invites.map(invite => invite.checked_at).filter(stamp => stamp != null)
  return stamps.length ? dateLabel(Math.max(...stamps)) : '等待首次检测'
}
</script>

<template>
  <section v-if="!following" class="hero" aria-labelledby="hero-title">
    <div class="hero-copy">
      <div class="hero-kicker"><span></span> Apple TestFlight</div>
      <h1 id="hero-title">追踪测试名额<span>。</span></h1>
      <p>浏览 TestFlight 测试项目，查看开放记录，<br class="wide-only">在测试名额开放时收到提醒。</p>
      <a v-if="canBrowse" href="#library" class="hero-link">浏览软件库 <ArrowDown :size="15" /></a>
      <RouterLink v-else to="/login" class="hero-link">登录后浏览 <ArrowRight :size="15" /></RouterLink>
    </div>
    <div class="hero-graphic" aria-hidden="true">
      <div class="radar">
        <i class="radar-ring ring-1"></i><i class="radar-ring ring-2"></i><i class="radar-ring ring-3"></i>
        <i class="radar-sweep"></i><i class="radar-axis axis-h"></i><i class="radar-axis axis-v"></i>
        <i class="radar-center"></i><i class="radar-point point-a"></i><i class="radar-point point-b"></i><i class="radar-point point-c"></i>
      </div>
    </div>
  </section>
  <section v-if="canBrowse" id="library" class="library">
    <div class="section-heading">
      <div>
        <div class="section-icon"><component :is="following ? Bell : LibraryBig" :size="19" /></div>
        <div>
          <component :is="following ? 'h1' : 'h2'">{{ following ? '我的关注' : '软件库' }}</component>
          <p>{{ following ? '查看你正在关注的 TestFlight 邀请。' : '搜索已收录的 TestFlight 邀请。' }}</p>
        </div>
      </div>
      <button v-if="session.user && !following" type="button" class="btn btn-dark" :aria-expanded="showForm" @click="showForm = !showForm"><Plus :size="18" /> 添加邀请</button>
    </div>
    <div v-if="showForm" class="panel inline-form">
      <h3>添加公开邀请</h3>
      <InviteForm @cancel="showForm = false" @submitted="showForm = false" />
    </div>
    <div class="library-toolbar">
      <form class="search-form" role="search" @submit.prevent="apply({ q: search.trim() || undefined })">
        <div class="field-icon search-field"><Search :size="19" /><input v-model="search" type="search" maxlength="120" aria-label="搜索软件名称或邀请码" placeholder="搜索软件名称或邀请码">
          <button v-if="search" class="icon-button" type="button" aria-label="清除搜索" @click="search = ''; apply({ q: undefined })"><X :size="16" /></button>
        </div>
        <button class="btn btn-secondary">搜索</button>
      </form>
      <div class="filters" aria-label="按状态筛选">
        <button v-for="[value, label] in [['', '全部'], ...Object.entries(states)]" :key="value" type="button" :aria-pressed="filter === value" @click="apply({ status: value || undefined })"><span v-if="value" :class="'filter-dot dot-' + value"></span>{{ label }}</button>
      </div>
    </div>
    <div v-if="loading" class="panel state-panel" role="status">正在加载软件…</div>
    <div v-else-if="error" class="panel state-panel" role="alert">{{ error }}</div>
    <div v-else-if="!items.length" class="panel state-panel empty-catalog">
      <span class="empty-icon"><component :is="route.query.q ? Search : following ? Bell : LibraryBig" :size="28" :stroke-width="1.7" /></span>
      <h3>{{ route.query.q || filter ? '没有匹配的软件' : following ? '还没有关注的邀请' : '软件库里还没有邀请' }}</h3>
      <p v-if="route.query.q || filter">试试其他关键词，或清除筛选条件。</p>
      <p v-else-if="following">打开软件详情，即可关注感兴趣的邀请。</p>
      <p v-else>提交公开邀请后，TFWatch 会自动检查名额。</p>
      <button v-if="route.query.q || filter" type="button" class="btn btn-secondary" @click="apply({ q: undefined, status: undefined })">清除筛选</button>
      <RouterLink v-else-if="following" to="/" class="btn btn-secondary">浏览软件库 <ArrowRight :size="16" /></RouterLink>
      <button v-else-if="session.user" class="btn btn-secondary" @click="showForm = true"><Plus :size="16" /> 添加邀请</button>
      <RouterLink v-else to="/login" class="btn btn-secondary">登录后添加 <ArrowRight :size="16" /></RouterLink>
    </div>
    <div v-else class="catalog-grid">
      <RouterLink v-for="app in items" :key="app.id" class="panel app-card" :to="{ path: '/apps/' + app.id, query: following ? { invite: app.invites.find(inv => inv.followed)?.code } : {} }">
        <div class="app-card-top"><AppIcon :icon="app.icon" :name="app.name" /><StatusPill :status="app.status" :pending="app.invites.every(inv => inv.checked_at == null)" /></div>
        <h3>{{ app.name }}</h3>
        <p v-if="app.description" class="card-description">{{ app.description }}</p>
        <p v-else>{{ app.invites.length }} 个公开邀请<span v-if="app.invites.some(inv => inv.followed)"> · 已关注</span></p>
        <div class="app-card-bottom"><span>{{ checkedAt(app) }}</span><ArrowUpRight :size="18" /></div>
      </RouterLink>
    </div>
    <div v-if="page > 1 || hasMore" class="pagination">
      <button type="button" class="btn btn-secondary btn-small" :disabled="page <= 1 || loading" @click="apply({ page: page - 1 === 1 ? undefined : page - 1 })"><ChevronLeft :size="16" /> 上一页</button>
      <span>第 {{ page }} 页</span>
      <button type="button" class="btn btn-secondary btn-small" :disabled="!hasMore || loading" @click="apply({ page: page + 1 })">下一页 <ChevronRight :size="16" /></button>
    </div>
  </section>
  <div v-else-if="following" class="panel state-panel">
    <h1>我的关注</h1><p>登录后查看你的关注列表。</p><RouterLink to="/login" class="btn btn-dark">登录</RouterLink>
  </div>
</template>

