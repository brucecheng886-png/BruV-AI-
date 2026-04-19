import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue') },
  { path: '/', redirect: '/chat' },
  { path: '/chat', component: () => import('../views/ChatView.vue'), meta: { requiresAuth: true } },
  { path: '/docs', component: () => import('../views/DocsView.vue'), meta: { requiresAuth: true } },
  { path: '/ontology', component: () => import('../views/OntologyView.vue'), meta: { requiresAuth: true } },
  { path: '/plugins', component: () => import('../views/PluginsView.vue'), meta: { requiresAuth: true } },
  { path: '/protein', component: () => import('../views/ProteinGraphView.vue'), meta: { requiresAuth: true } },
  { path: '/settings', component: () => import('../views/SettingsView.vue'), meta: { requiresAuth: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth) {
    if (!auth.token) {
      return '/login'
    }
    // 驗證 token 是否仍然有效（僅在頁面切換時，非每次 API 呼叫）
    if (!router._tokenVerified) {
      try {
        const resp = await fetch('/api/auth/me', {
          headers: { 'Authorization': `Bearer ${auth.token}` }
        })
        if (!resp.ok) {
          auth.logout()
          return '/login'
        }
        router._tokenVerified = true
      } catch {
        auth.logout()
        return '/login'
      }
    }
  }
})

export default router
