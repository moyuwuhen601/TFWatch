import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Catalog from './Catalog.vue'
import Detail from './Detail.vue'
import Auth from './Auth.vue'
import Account from './Account.vue'
import Admin from './Admin.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, saved) {
    if (saved) return saved
    if (to.path !== from.path) return { top: 0 }
  },
  routes: [
    { path: '/', component: Catalog },
    { path: '/following', component: Catalog, props: { following: true } },
    { path: '/apps/:id(\\d+)', component: Detail, props: true },
    ...['login', 'register', 'forgot-password', 'reset-password', 'verify-email'].map(mode => ({
      path: '/' + mode, component: Auth, props: { mode },
    })),
    { path: '/account', component: Account },
    { path: '/admin', component: Admin },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

createApp(App).use(router).mount('#app')
