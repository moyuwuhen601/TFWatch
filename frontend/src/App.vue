<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowUpRight, Bell, CircleUserRound, LibraryBig, Radio, ShieldCheck } from 'lucide-vue-next'
import { refreshSession, session } from './api'

const router = useRouter()
onMounted(refreshSession)

router.afterEach((to, from) => {
  if (to.path !== from.path) requestAnimationFrame(() => document.getElementById('main')?.focus({ preventScroll: true }))
})
</script>

<template>
  <a href="#main" class="skip-link">跳转到内容</a>
  <header class="topbar">
    <div class="container header-inner">
      <RouterLink to="/" class="brand" aria-label="TFWatch 首页">
        <span class="brand-mark"><Radio :size="22" :stroke-width="2.5" /></span>
        <span>TF<span class="brand-accent">Watch</span></span>
      </RouterLink>
      <nav class="primary-nav" aria-label="主导航">
        <RouterLink to="/" class="nav-link" :class="{ current: $route.path === '/' || $route.path.startsWith('/apps/') }"><LibraryBig :size="17" /> 软件库</RouterLink>
        <RouterLink v-if="session.user" to="/following" class="nav-link"><Bell :size="17" /> 我的关注</RouterLink>
        <RouterLink v-if="session.user?.is_admin" to="/admin" class="nav-link"><ShieldCheck :size="17" /> 管理后台</RouterLink>
      </nav>
      <div v-if="session.ready && !session.error" class="header-actions">
        <RouterLink v-if="session.user" to="/account" class="btn btn-secondary btn-small"><CircleUserRound :size="16" /> 账号设置</RouterLink>
        <template v-else>
          <RouterLink to="/login" class="btn btn-plain btn-small">登录</RouterLink>
          <RouterLink v-if="session.registration" to="/register" class="btn btn-dark btn-small">注册 <ArrowUpRight :size="15" /></RouterLink>
        </template>
      </div>
    </div>
  </header>
  <main id="main" tabindex="-1" class="container page-shell">
    <div v-if="!session.ready" class="panel state-panel" role="status">正在连接 TFWatch…</div>
    <div v-else-if="session.error" class="panel state-panel" role="alert">
      <h1>暂时无法加载站点</h1>
      <p>{{ session.error }}</p>
      <button type="button" class="btn btn-secondary" @click="refreshSession">重试</button>
    </div>
    <RouterView v-else />
  </main>
  <footer class="footer">
    <div class="container footer-inner">
      <span><Radio :size="15" /> <strong>TFWatch</strong> <span class="footer-divider"></span> TestFlight 资格监控</span>
      <a v-if="session.source_url" :href="session.source_url" target="_blank" rel="noopener noreferrer">项目源码 <ArrowUpRight :size="14" /></a>
    </div>
  </footer>
</template>

